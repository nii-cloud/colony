try:
    import simplejson as json
except ImportError:
    import json
from urlparse import urlparse, urlunparse
from eventlet.green.httplib import HTTPConnection, HTTPResponse, HTTPSConnection
from webob import Request, Response
from swift.common.utils import get_logger
from eventlet.timeout import Timeout
from swift.common.exceptions import ConnectionTimeout
import os
import sys

"""
Setting

[pipeline:main]
pipeline = keystone_merge dispatcher

[filter:keystone_merge]
use = egg:dispatcher#keystone_merge
keystone_relay_path = /both/v2.0
keystone_relay_token_paths = /both/v2.0/tokens /both/v2.0/hogehoge
keystone_one_url = http://192.0.2.100:5001
keystone_other_url = http://192.0.2.200:5001
dispatcher_base_url = http://192.0.2.1:10000
region_name = RegionOne

"""

class KeystoneMerge(object):
    """ """
    def __init__(self, app, conf):
        """ """
        self.app = app
        self.conf = conf
        self.logger = get_logger(conf, log_route='keystone_merge')
        self.keystone_relay_path = conf.get('keystone_relay_path','/both/v2.0')
        self.keystone_relay_token_paths = conf.get('keystone_relay_token_paths').split()
        self.keystone_one_url = conf.get('keystone_one_url')
        self.keystone_other_url = conf.get('keystone_other_url')
        self.dispatcher_base_url = conf.get('dispatcher_base_url')
        self.region_name = conf.get('region_name', 'RegionOne')
        self.merge_str = '__@@__'
        self.merge_location_path = self.keystone_relay_path.split('/')[1]
        self.logger.info('keystone_merge loaded')

    def __call__(self, env, start_response):
        """ """
        req = Request(env)
        real_path = '/' + '/'.join(req.path.split('/')[2:])
        if not self.is_keystone_req(req):
            self.logger.info('pass through')
            return self.app(env, start_response)
        if self.is_keystone_auth_token_req(req):
            self.logger.info('return auth response that merged one and other')
            mbody, mheaders = self.relay_keystone_auth_req(req, real_path)             
            if mbody:
                merged_resp = Response(request=req, 
                                       body=mbody, 
                                       headers=mheaders)
                start_response(merged_resp.status, merged_resp.headerlist)
                return json.dumps(merged_resp.body)
            else:
                return self.app(env, start_response)
        self.logger.info('normal keystone request to one')
        result = self.relay_keystone_ordinary_req(req)
        resp = Response(status='%s %s' % (result.status, result.reason));
        resp.headerlist = result.getheaders()
        resp.body = result.read()
        start_response(resp.status, resp.headerlist)
        return resp.body

    def is_keystone_req(self, req):
        """ 
        check a path which keystone_merge controls.
        """
        if req.path.startswith(self.keystone_relay_path):
            return True
        return False

    def is_keystone_auth_token_req(self, req):
        """ 
        check path is controled by keystone_merge. 
        ex: '/v2.0/tokens'
        """
        for path in self.keystone_relay_token_paths:
            if req.path == path and req.method == 'POST' \
                    and req.content_type == 'application/json':
                return True
        return False


    def relay_keystone_ordinary_req(self, req):
        """
        relay requests (not 'Authenticate for Service API and the other') to keystone_one_url.
        """
        path_ls = req.path.split('/')
        rewrite_path = '/%s' % '/'.join(path_ls[2:])
        tokens = req.headers['x-auth-token']
        one_token = tokens.split(self.merge_str)[0]
        req.headers['x-auth-token'] = one_token
        return self._request_to_keystone(req.method, self.keystone_one_url, 
                                         rewrite_path, req.headers, req.body)


    def relay_keystone_auth_req(self, req, path):
        """ 
        relay auth request by Creds to each keystone, and merge response. 
        """
        request = json.loads(req.body)
        creds = request['auth'] if request.has_key('auth') else request
        if creds.has_key('token') and path == '/v2.0/tokens':
            # for recomfirming auth token
            merged_token = creds['token']['id']
            if merged_token.find(self.merge_str) == -1:
                return None, None
            requests = self._merged_request_token_split(request)
            for url,request in zip([self.keystone_one_url, self.keystone_other_url], requests):
                resp = self._request_to_keystone('POST', url, path, 
                                                 req.headers, json.dumps(request))
                resps.append(resp)
        else:
            resps = [self._request_to_keystone('POST', url, path, 
                                               req.headers, req.body)
                     for url in [self.keystone_one_url, self.keystone_other_url]]
        bodies = self._get_bodies(resps)
        return self._access_info_merge(bodies), self._merge_headers(resps)

    def _merged_request_token_split(self, request):
        requests = []
        merged_token = request['auth']['token']['id']
        tokens = merged_token.split(self.merge_str)
        for token in tokens:
            each_request = {'auth': {'token': {'id': token}, "tenantId": ""}}
            requests.append(each_request)
        return requests

    def _access_info_merge(self, bodies):
        """ """
        tokens = []
        users = []
        catalogs = []
        swift_cats = []
        for body in bodies:
            tokens.append(body['access']['token'])
            users.append(body['access']['user'])
            catalogs.append(body['access']['serviceCatalog'])
        for cat in catalogs:
            for c in cat:
                if c['name'] == 'swift':
                    swift_cats.append(c)
        token = self._token_merge(tokens)
        swift_catalog = self._swift_catalog_merge(swift_cats, 
                                                  self.dispatcher_base_url, 
                                                  self.merge_location_path, 
                                                  self.region_name)
        return {'access': {'token': token, 
                           'serviceCatalog': [swift_catalog], 
                           'user': users[0]}}

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

    def _swift_catalog_merge(self, swift_cats, dispatcher_base_url, 
                             merge_location_path, region_name):
        adminURLs = []
        internalURLs = []
        publicURLs = []
        for cat in swift_cats:
            for region in cat['endpoints']:
                if region['region'] == region_name:
                    adminURLs.append(region['adminURL'])
                    internalURLs.append(region['internalURL'])
                    publicURLs.append(region['publicURL'])
        adminURL = '%s/%s%s' % (dispatcher_base_url, merge_location_path, 
                                 self._get_merged_common_path(adminURLs))
        internalURL = '%s/%s%s' % (dispatcher_base_url, merge_location_path, 
                                 self._get_merged_common_path(internalURLs))
        publicURL = '%s/%s%s' % (dispatcher_base_url, merge_location_path, 
                                 self._get_merged_common_path(publicURLs))
        return {'endpoints': [{'adminURL': adminURL,
                               'internalURL': internalURL,
                               'publicURL': publicURL,
                               'region': region_name, 
                               'type': 'object-store', 
                               'name': 'swift'}]}

    def _get_merged_common_path(self, urls):
        paths = [urlparse(u).path for u in urls]
        if not filter(lambda a: paths[0] != a, paths):
            return paths[0]
        return None

    def _merge_headers(self, resps):
        mheaders = {}
        headers = []
        for hs in [r.getheaders() for r in resps]:
            headers = headers + hs
        for h, v in headers:
            if h != 'content-length' and h != 'date':
                mheaders[h] = v
        return mheaders

    def _split_netloc(self, parsed_url):
        if parsed_url.netloc.find(':') > 0:
            host, port = parsed_url.netloc.split(':')
        else:
            host = parsed_url.netloc
            port = None
        if not port:
            if parsed_url.scheme == 'http':
                port = '80'
            elif parsed_url.scheme == 'https':
                port = '443'
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
