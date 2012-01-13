import os
import sys
try:
    import unittest2 as unittest
except (ImportError):
    import unittest
from dispatcher.server import Dispatcher as server
from dispatcher.common.middleware.keystone_merge import filter_factory
from eventlet import sleep, spawn, TimeoutError, util, wsgi, listen
from swift.common.utils import normalize_timestamp, NullLogger
from webob import Request, Response
import json
from urlparse import urlparse
import types

class TmpLogger():
    def write(self, *args):
        with open('/tmp/test.log', 'a') as f:
            f.write(*args)

def setUp(self):
    global _servers, keystone0_lis, keystone1_lis, keystone0_srv, keystone1_srv, keystone0_spa, keystone1_spa
    nl = NullLogger()
    keystone0_lis = listen(('localhost', 5001))
    keystone1_lis = listen(('localhost', 15001))
    keystone0_srv = DummySrv('http://127.0.0.1:5001')
    keystone1_srv = DummySrv('http://127.0.0.1:15001')
    keystone0_spa = spawn(wsgi.server, keystone0_lis, keystone0_srv, nl)
    keystone1_spa = spawn(wsgi.server, keystone1_lis, keystone1_srv, nl)
    _servers = (keystone0_spa, keystone1_spa)
    
def tearDown(self):
    for s in _servers:
        s.kill()


class DummyApp(object):
    """ """
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        status = '200 OK'
        start_response(status, [('content-type', 'application/json')])
        return '{"data": "None"}'

class DummySrv(object):
    def __init__(self, base_url):
        self.base_url = base_url
        self.body = access_token0 if base_url == 'http://127.0.0.1:5001' else access_token1

    def __call__(self, env, start_response):
        self.env = env
        req = Request(env)
        if req.path == '/v2.0/tokens':
            body = json.dumps(self.body)
        else:
            body = 'no auth token request'
        status = '200 OK'
        start_response(status, [('content-type', 'application/json')])
        return body

class TestController(unittest.TestCase):
    def setUp(self):
        conf = {'keystone_relay_path': '/both/v2.0',
                'keystone_relay_token_paths': '/both/v2.0/tokens /both/v2.0/token_by',
                'keystone_one_url': 'http://192.168.2.100:5001',
                'keystone_other_url': 'http://192.168.2.200:5001',
                'dispatcher_base_url': 'http://192.168.2.1:10000',
                'region_name': 'RegionOne'}
        self.k = filter_factory(conf)(DummyApp())

    def tearDown(self):
        pass

    def test_is_keystone_req(self):
        """ is_keystone_req """
        req = Request.blank('http://192.168.2.1:10000/both/v2.0')
        self.assertTrue(self.k.is_keystone_req(req))
        req = Request.blank('http://192.168.2.1:10000/v2.0')
        self.assertFalse(self.k.is_keystone_req(req))

    def test_is_keystone_auth_token_req(self):
        """ is_keystone_auth_token_req """
        req = Request.blank('http://192.168.2.1:10000/both/v2.0/tokens')
        req.method = 'POST'
        req.content_type = 'application/json'
        self.assertTrue(self.k.is_keystone_auth_token_req(req))
        req = Request.blank('http://192.168.2.1:10000/both/v2.0/dummy_tokens')
        self.assertFalse(self.k.is_keystone_auth_token_req(req))

    def test_merged_request_token_split(self):
        """ merged_request_token_split """
        auth_token0 = {'auth' : {'token': {'id': '488e1870-3c98-4ac9-bce4-631547b305f5__@@__7af4f2ba-96e2-481f-87cc-85eb030c8b52'}}}
        self.assertEqual(self.k._merged_request_token_split(auth_token0), 
                         [{'auth' : {'token': {'id': '488e1870-3c98-4ac9-bce4-631547b305f5'}, 
                                     'tenantId': ''}},
                          {'auth' : {'token': {'id': '7af4f2ba-96e2-481f-87cc-85eb030c8b52'}, 
                                     'tenantId': ''}}])
                         
    def test_access_info_merge(self):
        """ access_info_merge """
        self.assertEqual(self.k._access_info_merge([access_token0, access_token1]),
                         {'access': {'token': {'expires': '2012-01-09T19:11:27.058939', 
                                               'id': '7af4f2ba-96e2-481f-87cc-85eb030c8b52__@@__0acae2a7-aea7-4c83-8b0d-13c2e74fe67b', 
                                               'tenant': {'id': '2', 'name': 'test'}}, 
                                     'serviceCatalog': 
                                     [{'endpoints': [{'name': 'swift', 
                                                      'adminURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test', 
                                                      'region': 'RegionOne', 
                                                      'type': 'object-store', 
                                                      'internalURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test', 
                                                      'publicURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test'}]}], 
                                     'user': {'id': '3', 'roles': [{'id': '2', 'name': 'Member'}], 'name': 'tester'}}})

    def test_get_bodies(self):
        resp0 = Response(status='200 OK', body='{"num": "one"}')
        resp1 = Response(status='200 OK', body='{"num": "two"}')
        bodies = self.k._get_bodies([resp0, resp1])
        self.assertTrue(isinstance(bodies, types.GeneratorType))

    def test_token_merge(self):
        """ token_merge """
        self.assertEqual(self.k._token_merge([access_token0['access']['token'],
                                              access_token1['access']['token']]) ,
                         {'expires': '2012-01-09T19:11:27.058939', 
                          'id': '7af4f2ba-96e2-481f-87cc-85eb030c8b52__@@__0acae2a7-aea7-4c83-8b0d-13c2e74fe67b', 
                          'tenant': {'id': '2', 'name': 'test'}})

    def test_swift_catalog_merge(self):
        """ swift_catalog_merge """
        catalogs = [access_token0['access']['serviceCatalog'],
                    access_token1['access']['serviceCatalog']]
        swift_cats = []
        for cat in catalogs:
            for c in cat:
                if c['name'] == 'swift':
                    swift_cats.append(c)
        self.assertEqual(self.k._swift_catalog_merge(swift_cats, 
                                                     self.k.dispatcher_base_url, 
                                                     self.k.merge_location_path, 
                                                     self.k.region_name),
                         {'endpoints': [{'name': 'swift', 
                                         'adminURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test', 
                                         'region': 'RegionOne', 
                                         'type': 'object-store', 
                                         'internalURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test', 
                                         'publicURL': 'http://192.168.2.1:10000/both/v1.0/AUTH_test'}]})

    def test_get_merged_common_path(self):
        """ get_merged_common_path """
        urls = ['http://192.168.2.0:8080/v2.0/tokens', 
                'http://172.16.2.0:8080/v2.0/tokens']
        self.assertEqual(self.k._get_merged_common_path(urls), '/v2.0/tokens')
        urls = ['http://192.168.2.0:8080/v2.0/tokens', 
                'http://172.16.2.0:8080/v2.0/dummy']
        self.assertEqual(self.k._get_merged_common_path(urls), None)


    def test_merge_headers(self):
        """ merge_headers """
        resp0 = Response(status='200 OK')
        resp0.headers['Content-Type'] = 'text/plain'
        resp1 = Response(status='200 OK')
        resp0.headers['Content-Type'] = 'text/plain'

    def test_split_netloc(self):
        """ test_split_netloc """
        self.assertEqual(self.k._split_netloc(urlparse('http://192.168.2.1:8080/')), 
                         ('192.168.2.1', '8080'))
        self.assertEqual(self.k._split_netloc(urlparse('http://192.168.2.1/')),
                         ('192.168.2.1', '80'))
        self.assertEqual(self.k._split_netloc(urlparse('https://192.168.2.1/')),
                         ('192.168.2.1', '443'))

    def test_pass_through(self):
        """ relay to keystone, not auth request """
        app = DummyApp()
        conf = {'keystone_relay_path': '/both/v2.0',
                'keystone_relay_token_paths': '/both/v2.0/tokens /both/v2.0/token_by',
                'keystone_one_url': 'http://127.0.0.1:5001',
                'keystone_other_url': 'http://127.0.0.1:15001',
                'dispatcher_base_url': 'http://127.0.0.1:10000',
                'region_name': 'RegionOne'}
        k = filter_factory(conf)(app)
        resp = Request.blank('/auth/v1.0', headers={'X-Auth-Token': 't'}).get_response(k)
        self.assertEqual(json.loads(resp.body), {'data': 'None'})
        resp = Request.blank('/both/v2.0/dummy_tokens', headers={'X-Auth-Token': 't'}).get_response(k)
        self.assertEqual(keystone0_srv.env['PATH_INFO'], '/v2.0/dummy_tokens')

    def test_auth_token(self):    
        """ relay to keystone, auth request """
        app = DummyApp()
        result = {'access': {'token': 
                             {'expires': '2012-01-09T19:11:27.058939', 
                              'id': '7af4f2ba-96e2-481f-87cc-85eb030c8b52__@@__0acae2a7-aea7-4c83-8b0d-13c2e74fe67b', 
                              'tenant': {'id': '2', 'name': 'test'}}, 
                             'serviceCatalog': 
                             [{'endpoints': 
                               [{'name': 'swift', 
                                 'adminURL': 'http://127.0.0.1:10000/both/v1.0/AUTH_test', 
                                 'region': 'RegionOne', 
                                 'type': 'object-store', 
                                 'internalURL': 'http://127.0.0.1:10000/both/v1.0/AUTH_test', 
                                 'publicURL': 'http://127.0.0.1:10000/both/v1.0/AUTH_test'}]}], 
                             'user': {'id': '3', 'roles': [{'id': '2', 'name': 'Member'}], 
                                      'name': 'tester'}}}
        conf = {'keystone_relay_path': '/both/v2.0',
                'keystone_relay_token_paths': '/both/v2.0/tokens /both/v2.0/token_by',
                'keystone_one_url': 'http://127.0.0.1:5001',
                'keystone_other_url': 'http://127.0.0.1:15001',
                'dispatcher_base_url': 'http://127.0.0.1:10000',
                'region_name': 'RegionOne'}
        k = filter_factory(conf)(app)
        resp = Request.blank('/both/v2.0/tokens',
                             method='POST',
                             headers={'Content-Type': 'application/json'},
                             body=json.dumps({'auth': {'passwordCredentials': 
                                                       {'username': 'tester', 'password': 'testing'}, 
                                                       'tenantId': ''}})).get_response(k)
        self.assertEqual(json.loads(resp.body), result)
        resp = Request.blank('/both/v2.0/tokens',
                             method='POST',
                             headers={'Content-Type': 'application/json'},
                             body=json.dumps({'auth': {'token': {'id': 't__@@__v'}, 'tenantId': ''}})).get_response(k)
        self.assertEqual(json.loads(resp.body), result)
        resp = Request.blank('/both/v2.0/tokens',
                             method='POST',
                             headers={'Content-Type': 'application/json'},
                             body=json.dumps({'auth': {'token': {'id': 't'}, 'tenantId': ''}})).get_response(k)
        self.assertEqual(json.loads(resp.body), {'data': 'None'})



# test data
access_token0 = {'access': 
                 {'token': {'expires': '2012-01-09T19:11:27.058939', 
                            'id': '7af4f2ba-96e2-481f-87cc-85eb030c8b52', 
                            'tenant': {'id': '2', 'name': 'test'}}, 
                  'serviceCatalog': [{'endpoints': [{'adminURL': 'http://172.30.112.168:8080/v1.0/AUTH_test', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8080/v1.0/AUTH_test', 
                                                     'publicURL': 'http://172.30.112.168:8080/v1.0/AUTH_test'}], 
                                      'type': 'object-store', 'name': 'swift'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:8774/v1.1/test', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8774/v1.1/test', 
                                                     'publicURL': 'http://172.30.112.168:8774/v1.1/test'}], 
                                              'type': 'compute', 'name': 'nova'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:8774/v1.0', 
                                                             'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8774/v1.0', 
                                                     'publicURL': 'http://172.30.112.168:8774/v1.0/'}], 
                                      'type': 'compute', 'name': 'nova_compat'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:9292/v1.1/test', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:9292/v1.1/test', 
                                                     'publicURL': 'http://172.30.112.168:9292/v1.1/test'}], 
                                      'type': 'image', 'name': 'glance'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:5001/v2.0', 
                                                     'region': 'RegionOne', 
                                                             'internalURL': 'http://172.30.112.168:5000/v2.0', 
                                                     'publicURL': 'http://172.30.112.168:5000/v2.0'}], 
                                      'type': 'identity', 'name': 'identity'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:8081/v2.0', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8080/v2.0', 
                                                     'publicURL': 'http://172.30.112.168:8080/v2.0'}], 
                                      'type': 'identity', 'name': 'keystone'}], 
                  'user': {'id': '3', 'roles': [{'id': '2', 'name': 'Member'}], 'name': 'tester'}}}

access_token1 = {'access': 
                 {'token': {'expires': '2012-01-09T19:11:27.058939', 
                            'id': '0acae2a7-aea7-4c83-8b0d-13c2e74fe67b',
                            'tenant': {'id': '2', 'name': 'test'}}, 
                  'serviceCatalog': [{'endpoints': [{'adminURL': 'http://172.30.112.168:8080/v1.0/AUTH_test', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8080/v1.0/AUTH_test', 
                                                     'publicURL': 'http://172.30.112.168:8080/v1.0/AUTH_test'}], 
                                      'type': 'object-store', 'name': 'swift'}, 
                                             {'endpoints': [{'adminURL': 'http://172.30.112.168:8774/v1.1/test', 
                                                             'region': 'RegionOne', 
                                                             'internalURL': 'http://172.30.112.168:8774/v1.1/test', 
                                                             'publicURL': 'http://172.30.112.168:8774/v1.1/test'}], 
                                              'type': 'compute', 'name': 'nova'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:8774/v1.0', 
                                                             'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8774/v1.0', 
                                                     'publicURL': 'http://172.30.112.168:8774/v1.0/'}], 
                                      'type': 'compute', 'name': 'nova_compat'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:9292/v1.1/test', 
                                                             'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:9292/v1.1/test', 
                                                     'publicURL': 'http://172.30.112.168:9292/v1.1/test'}], 
                                      'type': 'image', 'name': 'glance'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:5001/v2.0', 
                                                     'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:5000/v2.0', 
                                                     'publicURL': 'http://172.30.112.168:5000/v2.0'}], 
                                      'type': 'identity', 'name': 'identity'}, 
                                     {'endpoints': [{'adminURL': 'http://172.30.112.168:8081/v2.0', 
                                                             'region': 'RegionOne', 
                                                     'internalURL': 'http://172.30.112.168:8080/v2.0', 
                                                     'publicURL': 'http://172.30.112.168:8080/v2.0'}], 
                                      'type': 'identity', 'name': 'keystone'}], 
                  'user': {'id': '3', 'roles': [{'id': '2', 'name': 'Member'}], 'name': 'tester'}}}
        

