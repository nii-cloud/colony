import simplejson as json
from urlparse import urlparse, urlunparse
from eventlet.green.httplib import HTTPConnection, HTTPResponse, HTTPSConnection
from webob import Request, Response
from webob.exc import HTTPException, HTTPAccepted, HTTPBadRequest, \
    HTTPConflict, HTTPCreated, HTTPForbidden, HTTPMethodNotAllowed, \
    HTTPMovedPermanently, HTTPNoContent, HTTPNotFound, \
    HTTPServiceUnavailable, HTTPUnauthorized, HTTPGatewayTimeout, \
    HTTPBadGateway,  HTTPRequestEntityTooLarge, HTTPServerError, HTTPPreconditionFailed
from swift.common.utils import get_logger
from eventlet import TimeoutError
from eventlet.timeout import Timeout
from swift.common.exceptions import ConnectionTimeout
from dispatcher.common.location import Location
import os
import sys
import re

"""
Setting

[pipeline:main]
pipeline = keystone_proxy dispatcher

[filter:keystone_proxy]
use = egg:dispatcher#keystone_proxy
keystone_proxy_common_path = /ks
keystone_proxy_auth_path = auth
keystone_proxy_admin_path = admin
relay_rule = /etc/dispatcher/ks_server0.txt, remote:/etc/dispatcher/ks_server1.txt, both:(hoge)/etc/dispatcher/ks_server0.txt (gere)/etc/dispatcher/ks_server1.txt
dispatcher_base_url = http://172.30.112.168:10000
keystone_auth_port = 5000
keystone_admin_port = 35357
conn_timeout = 0.5
timeout = 300


URL Pattern
 http://dispatcher:10000/ks/auth/v2.0
 http://dispatcher:10000/ks/admin/v2.0
 http://dispatcher:10000/ks/remote/auth/v2.0
 http://dispatcher:10000/ks/remote/admin/v2.0
 http://dispatcher:10000/ks/merge/auth/v2.0
 http://dispatcher:10000/ks/merge/admin/v2.0

 curl -v -H 'X-Auth-User: tester' -H 'X-Auth-Key: testing' http://172.30.112.168:10000/ks/auth/v1.0
 curl -v -H 'Content-Type: application/json' -X POST -d '{"auth":{"passwordCredentials": {"username":"tester","password":"testing"}}}' http://172.30.112.168:10000/ks/auth/v2.0/tokens
 curl -v -H 'Content-Type: application/json' -X POST -d '{"auth":{"token": {"id": "8bac4be7-2473-45a1-9fda-06976c57b518"}}}' http://172.30.112.168:10000/ks/auth/v2.0/tokens
"""

class KeystoneProxy(object):
    """ """
    def __init__(self, app, conf):
        """ """
        self.app = app
        self.conf = conf
        self.keystone_proxy_common_path = conf.get('keystone_proxy_common_path', '/ks')
        self.keystone_proxy_auth_path = conf.get('keystone_proxy_auth_path', 'auth')
        self.keystone_proxy_admin_path = conf.get('keystone_proxy_admin_path', 'admin')
        self.relay_rule = conf.get('relay_rule')
        self.dispatcher_base_url = conf.get('dispatcher_base_url')
        if not self.dispatcher_base_url:
            raise ValueError
        self.region_name = conf.get('region_name')
        if not self.region_name:
            raise ValueError
        self.keystone_auth_port = conf.get('keystone_auth_port', 5000)
        self.keystone_admin_port = conf.get('keystone_admin_port', 35357)
        self.conn_timeout = float(conf.get('conn_timeout', 0.5))
        self.timeout = int(conf.get('timeout', 300))
        self.req_version_str = 'v[12]\.0'
        self.merge_str = '__@@__'
        try:
            self.loc = Location(self.relay_rule)
        except:
            raise ValueError, 'KeyStone Proxy relay rule is invalid.'

    def __call__(self, env, start_response):
        """
        """
        req = Request(env)
        if not self.is_keystone_proxy_path(req):
            return self.app(env, start_response)
        (loc_prefix, api_type) = self.location_api_check(req)
        ks_port = self.keystone_auth_port \
            if api_type == self.keystone_proxy_auth_path \
            else self.keystone_admin_port
        resps = self.request_to_ks(req, self.loc.swift_of(loc_prefix), ks_port)
        if self.loc.is_merged(loc_prefix):
            (body, header) = self.ks_merge_response(resps, loc_prefix)
            res = Response(status='200 OK')
            res.headerlist = header
            res.body = body
            return res(env, start_response)
        resp = resps[0]
        start_response('%s %s' % (resp.status, resp.reason),  resp.getheaders())
        return resp.read()

    def is_keystone_proxy_path(self, req):
        """ 
        check a path which keystone_proxy controls.
        """
        if req.path.startswith(self.keystone_proxy_common_path):
            return True
        return False

    def location_api_check(self, req):
        """ check '/ks/***Location***/***API***/v2.0'
        """
        try:
            loc_prefix = req.path.split('/')[2].strip()
            api_type = req.path.split('/')[3].strip()
        except:
            pass
        if re.match(self.req_version_str, api_type):
            api_type = loc_prefix
            return ('', api_type)
        return (loc_prefix, api_type)

    def request_to_ks(self, req, servers, port):
        """ Routing multiple keystone servers.
        """
        succ_resps = []
        fail_resps = []
        auth_tokens = self._split_auth_token(req, servers)
        bodies = self._split_body(req, servers)
        for site, token, body in zip(servers, auth_tokens, bodies):
            for node in site:
                parsed = urlparse(self._combinate_ks_url(node, port, req))
                connector = HTTPSConnection if parsed.scheme == 'https' else HTTPConnection 
                try:
                    with ConnectionTimeout(self.conn_timeout):
                        (host, port) = parsed.netloc.split(':')
                        headers = req.headers
                        if req.headers.has_key('Host'):
                            headers['Host'] = host + ':' + port
                        if token:
                            headers['X-Auth-Token'] = token
                        if req.headers.has_key('Content-Length'):
                            del headers['Content-Length']
                        conn = connector(host, port)
                        conn.request(req.method, parsed.path, body, headers)
                        with Timeout(self.timeout):
                            resp = conn.getresponse()
                            if resp.status >= 200 and resp.status <= 300:
                                succ_resps.append(resp)
                                break
                            else:
                                fail_resps.append(resp)
                except ValueError, err:
                    fail_resps.append(HTTPPreconditionFailed())
                except (Exception, TimeoutError), err:
                    fail_resps.append(HTTPServiceUnavailable())
        if len(succ_resps) != 0:
            return succ_resps
        return fail_resps

    def ks_merge_response(self, resps, loc_prefix):
        """ Merge JSON and HTTP headers from multiple KS servers.
        """
        headers = []
        bodies = []
        for resp in resps:
            headers.append(resp.getheaders())
            if int(resp.getheader('content-length', 0)):
                bodies.append(resp.read())
        header = self._merge_header(headers, loc_prefix)
        body = ''
        if len(bodies) != 0:
            body = self._merge_body(bodies, loc_prefix)
        return (body, header)

    def _combinate_ks_url(self, server, port, req):
        """ Combinate the original KS URL.
        """
        s_url = urlparse(server)
        r_url = urlparse(req.url)
        m = re.search(self.req_version_str, r_url.path)
        version_str = m.string[m.start():m.end()]
        path_ls = r_url.path.split(version_str)
        path = "/" + version_str + path_ls[1]
        return urlunparse((s_url.scheme, 
                           s_url.netloc.split(':')[0] + ':' + str(port),
                           path,
                           r_url.params,
                           r_url.query,
                           r_url.fragment))
        
    def _merge_header(self, headers, loc_prefix):
        """ Merge HTTP headers from multiple KS servers.
        """
        mheader = []
        auth_tokens = []
        storage_urls = []
        for header in headers:
            for name, value in header:
                if name == 'x-auth-token':
                    auth_tokens.append(value)
                    continue
                if name == 'x-storage-url':
                    storage_urls.append(value)
                    continue
                if name == 'content-length':
                    continue
                if name not in [n for n, v in mheader]:
                    mheader.append((name, value))    
        if len(auth_tokens) != 0:
            mheader.append(('x-auth-token',
                           self._merge_auth_token(auth_tokens)))
        if len(storage_urls) != 0:
            mheader.append(('x-storage-url',
                           self._merge_url(storage_urls, loc_prefix)))
        return mheader

    def _merge_body(self, bodies, loc_prefix):
        """ Merge JSON from multiple KS servers.
        """
        body = ''
        access = []
        misc = []
        for body in bodies:
            try:
                auth_info = json.loads(body)
            except:
                misc.append(body)
            if auth_info.has_key('access'):
                access.append(auth_info)
        if len(access) != 0:
            body = json.dumps(self._merge_body_access(access, loc_prefix))
        return body
    
    def _merge_auth_token(self, auth_tokens):
        """ Merge auth_token.
        """
        return self.merge_str.join(auth_tokens)

    def _merge_url(self, urls, loc_prefix):
        """ Make an endpoint URL for this middleware.
        """
        paths = [urlparse(u).path for u in urls]
        if not paths:
            path = '/'
        if not filter(lambda a: paths[0] != a, paths):
            path = paths[0]
        else:
            path = '/'
        if loc_prefix:
            path = '/' + loc_prefix + path
        p_burl = urlparse(self.dispatcher_base_url)
        return urlunparse((p_burl.scheme, 
                           p_burl.netloc,
                           path,
                           None, None, None))

    def _merge_body_access(self, access, loc_prefix):
        """ Merge 'access' JSON response from KS.
        """
        name = ''
        auth_tokens = []
        swift_publicURLs = []
        swift_adminURLs = []
        swift_internalURLs = []
        try:
            for a_info in access:
                name = a_info['access']['user']['name']
                auth_tokens.append(a_info['access']['token']['id'])
                for i in range(len(a_info['access']['serviceCatalog'])):
                    if a_info['access']['serviceCatalog'][i]['name'] == 'swift':
                        for j in range(len(a_info['access']['serviceCatalog'][i]['endpoints'])):
                            if a_info['access']['serviceCatalog'][i]['endpoints'][j]['region'] == self.region_name:
                                swift_publicURLs.append(a_info['access']['serviceCatalog'][i]['endpoints'][j]['publicURL'])
                                swift_adminURLs.append(a_info['access']['serviceCatalog'][i]['endpoints'][j]['adminURL'])
                                swift_internalURLs.append(a_info['access']['serviceCatalog'][i]['endpoints'][j]['internalURL'])
        except KeyError, err:
            raise
        maccess = access[0]
        maccess['access']['token']['id'] = self._merge_auth_token(auth_tokens)
        for i in range(len(maccess['access']['serviceCatalog'])):
            if maccess['access']['serviceCatalog'][i]['name'] == 'swift':
                for j in range(len(maccess['access']['serviceCatalog'][i]['endpoints'])):
                    if maccess['access']['serviceCatalog'][i]['endpoints'][j]['region'] == self.region_name:
                        maccess['access']['serviceCatalog'][i]['endpoints'][j]['publicURL'] = \
                            self._merge_url(swift_publicURLs, loc_prefix)
                        maccess['access']['serviceCatalog'][i]['endpoints'][j]['adminURL'] = \
                            self._merge_url(swift_adminURLs, loc_prefix)
                        maccess['access']['serviceCatalog'][i]['endpoints'][j]['internalURL'] = \
                            self._merge_url(swift_internalURLs, loc_prefix)
        return maccess

    def _split_auth_token(self, req, servers):
        """ Split a merged (or not) auth_token string 
            into numbers of KS servers.
        """
        if req.headers.has_key('X-Auth-Token'):
            auth_token = req.headers['X-Auth-Token']
            if auth_token.find(self.merge_str) >= 0:
                return auth_token.split(self.merge_str)
            else:
                return [auth_token for i in servers]
        else:
            return [None for i in servers]

    def _split_body(self, req, servers):
        """ Split a merged (or not) request body
            into numbers of KS servers.
        """
        if req.headers.has_key('Content-Length') and \
                req.headers['Content-Length'] != 0:
            doc = req.body
            try:
                auth = json.loads(doc)
                auth_token = auth['auth']['token']['id']
                if auth_token.find(self.merge_str) >= 0:
                    docs = []
                    for token in auth_token.split(self.merge_str):
                        s_auth = auth
                        s_auth['auth']['token']['id'] = token
                        docs.append(json.dumps(s_auth))
                    return docs
            except (KeyError, ValueError), err:
                return [doc for i in servers]
        return [None for i in servers]


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def keystone_proxy_filter(app):
        return KeystoneProxy(app, conf)

    return keystone_proxy_filter
