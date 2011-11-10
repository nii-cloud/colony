try:
    import simplejson as json
except ImportError:
    import json
from base64 import urlsafe_b64encode, urlsafe_b64decode
from urlparse import urlparse, urlunparse
from eventlet.green.httplib import HTTPConnection, HTTPResponse, HTTPSConnection
from webob import Request, Response
from webob.exc import HTTPException, HTTPAccepted, HTTPBadRequest, HTTPConflict, \
    HTTPCreated, HTTPForbidden, HTTPMethodNotAllowed, HTTPMovedPermanently, \
    HTTPNoContent, HTTPNotFound, HTTPServiceUnavailable, HTTPUnauthorized, \
    HTTPGatewayTimeout, HTTPBadGateway,  HTTPRequestEntityTooLarge, HTTPServerError
from urllib import quote, unquote
import urllib2
from swift.common.utils import cache_from_env, get_logger, TRUE_VALUES
from eventlet.timeout import Timeout
from swift.common.exceptions import ConnectionTimeout, ChunkReadTimeout, ChunkWriteTimeout
import os
import sys

class KeystoneMerge(object):
    """ """
    def __init__(self, app, conf):
        self.app = app
        self.conf = conf
        self.logger = get_logger(conf, log_route='keystone_merge')
        self.sp = conf.get('keystone_merge')
        self.keystone_relay_path = '/both/v2.0'
        self.keystone_relay_token_path = '/both/v2.0/tokens'
        self.logger.warn('keystone_merge loaded')
        self.keystone_urls = ['http://172.30.112.168:5000', 'http://172.30.112.170:5000']
        self.keystone_academic_url = 'http://172.30.112.168:5000'
        self.keystone_intercloud_url = 'http://172.30.112.170:5000'
        self.dispatcher_url = 'http://127.0.0.1:10000'
        self.merge_location_path = 'both'
        self.region_name = 'RegionOne'
        self.merge_str = '__@@__'


    def __call__(self, env, start_response):
        """ """
        req = Request(env)
        if self.is_keystone_req(env):
            if self.is_keystone_auth_req(env):
                merged_body, headers = self.relay_keystone_auth_req(env)
                if merged_body:
                    merged_resp = Response(request=req, body=merged_body, headers=headers)
                    start_response(merged_resp.status, merged_resp.headerlist)
                    return json.dumps(merged_resp.body)
                else:
                    return self.app(env, start_response)
            else:
                result = self.relay_keystone_req(env)
                resp = Response(status='%s %s' % (result.status, result.reason));
                resp.headerlist = result.getheaders()
                resp.body = result.read()
                #print resp.body
                start_response(resp.status, resp.headerlist)
                return resp.body
        else:
            return self.app(env, start_response)

    def is_keystone_req(self, env):
        """ """
        path = env['PATH_INFO']
        if path.startswith(self.keystone_relay_path):
            return True
        else:
            return False

    def is_keystone_auth_req(self, env):
        """ """
        path = env['PATH_INFO']
        method = env['REQUEST_METHOD']
        content_type = env['CONTENT_TYPE']
        if path == self.keystone_relay_token_path and method == 'POST' and content_type == 'application/json':
            return True
        else:
            return False

    def relay_keystone_req(self, env):
        method = env['REQUEST_METHOD']
        path = env['PATH_INFO']
        body = env['wsgi.input'].read()
        path_ls = path.split('/')
        rewrite_path = '/%s' % '/'.join(path_ls[2:])
        token = env['HTTP_X_AUTH_TOKEN']
        academic_token = token.split(self.merge_str)[0]
        return self._request_to_keystone(method, self.keystone_academic_url, rewrite_path, {'X-Auth-Token': academic_token}, body)

    def relay_keystone_auth_req(self, env):
        """ """
        body = env['wsgi.input'].read()
        request = json.loads(body)
        _dummy_request = request['auth']
        resps = []
        if _dummy_request.has_key('passwordCredentials'):
            resps = [self._request_to_keystone('POST', url, '/v2.0/tokens', {'content-type': 'application/json'}, body) for url in [self.keystone_academic_url, self.keystone_intercloud_url]]
        elif _dummy_request.has_key('token'):
            merged_token = request['auth']['token']['id']
            if merged_token.find(self.merge_str) != -1:
                requests = self.merged_request_token_split(request)
                for url,request in zip([self.keystone_academic_url, self.keystone_intercloud_url], requests):
                    resp = self._request_to_keystone('POST', url, '/v2.0/tokens', {'content-type': 'application/json'}, json.dumps(request))
                    resps.append(resp)
            else:
                return None, None
        else:
            return None, None
        bodies = self._get_bodies(resps)
        return self.access_info_merge(bodies), {}

    def merged_request_token_split(self, request):
        requests = []
        merged_token = request['auth']['token']['id']
        tokens = merged_token.split(self.merge_str)
        for token in tokens:
            each_request = {'auth': {'token': {'id': token}, "tenantId": "1"}}
            requests.append(each_request)
        return requests

    def access_info_merge(self, bodies):
        """ """
        tokens = []
        users = []
        catalogs = []
        swift_cats = []
        for body in bodies:
            #print body
            tokens.append(body['access']['token'])
            users.append(body['access']['user'])
            catalogs.append(body['access']['serviceCatalog'])
        for cat in catalogs:
            for c in cat:
                if c['name'] == 'swift':
                    swift_cats.append(c)
        token = self._token_merge(tokens)
        swift_catalog = self._swift_catalog_merge(swift_cats, self.dispatcher_url, self.merge_location_path, self.region_name)
        return {'access': {'token': token, 'serviceCatalog': [swift_catalog], 'user': users[0]}}

    def _get_bodies(self, resps):
        for resp in resps:
            if resp.status == 200:
                yield json.loads(resp.read())

    def _token_merge(self, tokens):
        expires = None
        tkn_id = None
        tenant = tokens[0]['tenant']
        for token in tokens:
            if not expires or expires < token['expires']:
                expires =  token['expires']
        tkn_id = self.merge_str.join([token['id'] for token in tokens])
        return {'expires': expires, 'id': tkn_id, 'tenant': tenant}

    def _swift_catalog_merge(self, swift_cats, dispatcher_url, merge_location_path, region_name):
        adminURLs = []
        internalURLs = []
        publicURLs = []
        for cat in swift_cats:
            for region in cat['endpoints']:
                if region['region'] == region_name:
                    adminURLs.append(region['adminURL'])
                    internalURLs.append(region['internalURL'])
                    publicURLs.append(region['publicURL'])
        adminURL = '%s/%s/%s' % (dispatcher_url, merge_location_path, urlsafe_b64encode(self.merge_str.join(adminURLs)))
        internalURL = '%s/%s/%s' % (dispatcher_url, merge_location_path, urlsafe_b64encode(self.merge_str.join(internalURLs)))
        publicURL = '%s/%s/%s' % (dispatcher_url, merge_location_path, urlsafe_b64encode(self.merge_str.join(publicURLs)))
        return {'endpoints': [{'adminURL': adminURL,
                               'internalURL': internalURL,
                               'publicURL': publicURL,
                               'region': region_name, 'type': 'object-store', 'name': 'swift'}]}

    def _split_netloc(self, parsed_url):
        host, port = parsed_url.netloc.split(':')
        if not port:
            if parsed_url.scheme == 'http':
                port = 80
            elif parsed_url.scheme == 'https':
                port = 443
            else:
                return None, None
        return host, port

    def _request_to_keystone(self, method, url, path, headers, body):
        """ """
        parsed = urlparse(url)
        connector = HTTPSConnection if parsed.scheme == 'https' else HTTPConnection 
        host, port = self._split_netloc(parsed)
        with ConnectionTimeout(300):
            conn = connector(host, port)
            conn.request(method, path, body, headers)
            with Timeout(300):
                return conn.getresponse()


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def keystone_merge_filter(app):
        return KeystoneMerge(app, conf)

    return keystone_merge_filter
