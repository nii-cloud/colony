import os
import sys
try:
    import unittest2 as unittest
except (ImportError):
    import unittest
from keystone.middleware.auth_token_for_colony import filter_factory
from eventlet import sleep, spawn, TimeoutError, util, wsgi, listen
from swift.common.utils import normalize_timestamp, NullLogger
from webob import Request, Response
import json
from urlparse import urlparse
from contextlib import contextmanager
import httplib
from time import time

class TmpLogger():
    def write(self, *args):
        with open('/tmp/test.log', 'a') as f:
            f.write(*args)

def setUp(self):
    global keystone0_lis, keystone0_srv, keystone0_spa
    nl = NullLogger()
    keystone0_lis = listen(('localhost', 15000))
    keystone0_srv = DummySrv('http://127.0.0.1:15000')
    keystone0_spa = spawn(wsgi.server, keystone0_lis, keystone0_srv, nl)
    
def tearDown(self):
    keystone0_spa.kill()

class FakeMemcache(object):

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=0):
        self.store[key] = value
        return True

    def incr(self, key, timeout=0):
        self.store[key] = self.store.setdefault(key, 0) + 1
        return self.store[key]

    @contextmanager
    def soft_lock(self, key, timeout=0, retries=5):
        yield True

    def delete(self, key):
        try:
            del self.store[key]
        except Exception:
            pass
        return True


class DummyApp(object):
    """ """
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        status = '200 OK'
        start_response(status, [('content-type', 'text/plain')])        
        return ''

class DummySrv(object):
    """
    BUG: unit tests can't access this dummy keystone. WHY?
    workaround -> use a real keystone server.
    """
    def __init__(self, base_url):
        self.base_url = base_url
        self.body = access_token0

    def __call__(self, env, start_response):
        self.env = env
        req = Request(env)
        if req.path == '/v2.0/tokens' and req.method == 'POST':
            # req_body = json.loads(req.body)
            # if req_body['auth']['passwordCredentials']['username'] == 'dummy':
            body = json.dumps(self.body)
            status = '200 OK'
        else:
            body = 'no auth token request'
            status = '404 Not Found'
        start_response(status, [('content-type', 'application/json')])
        return body


class TestController(unittest.TestCase):
    def setUp(self):
        app = DummyApp()
        conf = {'keystone_url': 'http://127.0.0.1:15000',
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        self.kauth = filter_factory(conf)(app)

    def tearDown(self):
        pass

    def test_get_claims(self):
        env = {'HTTP_X_AUTH_TOKEN': 't'}
        self.assertEqual(self.kauth._get_claims(env), 't')
        env = {'HTTP_X_STORAGE_TOKEN': 't2'}
        self.assertEqual(self.kauth._get_claims(env), 't2')

    def test_decorate_request(self):
        env = {}
        proxy_headers = env.copy()
        val = 'test'
        self.kauth._decorate_request('X_USER', val, env, proxy_headers)
        self.assertEqual(env['HTTP_X_USER'], 'test')
        self.assertEqual(proxy_headers['X_USER'], 'test')

    #@unittest.skip
    def test_validate_claims_each_user(self):
        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        kauth = filter_factory(conf)(app)
        auth_user = ('test', 'tester', 'testing')
        headers, body = kauth._validate_claims_each_user(auth_user)
        self.assertTrue(headers.has_key('X-Auth-Token'))
        self.assertTrue(headers.has_key('X-Storage-Token'))
        self.assertTrue(headers.has_key('X-Storage-Url'))
        self.assertEqual(json.loads(body), 
                         {'storage': 
                          {'default': 'locals', 
                           'locals': 'http://172.30.112.168:8080/v1.0/AUTH_test'}})
        auth_user = ('dummy', 'dummy', 'dummy')
        self.assertEqual(kauth._validate_claims_each_user(auth_user), None)

    #@unittest.skip
    def test_authreq_to_keystone(self):
        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        kauth = filter_factory(conf)(app)
        access = kauth._authreq_to_keystone('tester', 'testing')
        #self.assertEqual(access, access_token0)
        self.assertTrue(access['access']['token']['id'])

    def test_get_auth_user(self):
        env = {'HTTP_X_AUTH_USER': 'test:tester', 
               'HTTP_X_AUTH_KEY': 'testing', 
               'HTTP_X_STORAGE_USER': 'test:tester', 
               'HTTP_X_STORAGE_PASS': 'testing'}
        self.assertEqual(self.kauth._get_auth_user(env), ('test', 'tester', 'testing'))
        env = {'HTTP_X_STORAGE_USER': 'test:tester', 
               'HTTP_X_STORAGE_PASS': 'testing'}
        self.assertEqual(self.kauth._get_auth_user(env), ('test', 'tester', 'testing'))

    def test_get_swift_info(self):
        self.assertEqual(self.kauth._get_swift_info(access_token0, 'RegionOne'),
                         ('7af4f2ba-96e2-481f-87cc-85eb030c8b52', 
                          'test', 
                          'tester', 
                          ['Member'], 
                          'http://172.30.112.168:8080/v1.0/AUTH_test'))
        self.assertEqual(self.kauth._get_swift_info({'dummy': {}}, 'RegionOne'), None)

    #@unittest.skip
    def test_accession_by_auth_token(self):
        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        kauth = filter_factory(conf)(app)
        env = {'swift.cache': FakeMemcache()}
        # auth_token = 't'
        # self.assertEqual(kauth._accession_by_auth_token(env, auth_token), 
        #                  ('test', 'tester', ['Member'], 'http://172.30.112.168:8080/v1.0/AUTH_test'))
        auth_token = '999888777666'
        self.assertEqual(kauth._accession_by_auth_token(env, auth_token), 
                         ('admin', 'admin', ['Admin'], 'http://172.30.112.168:8080/v1.0/AUTH_admin'))

        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '0',
                'across_account': 'no'}
        kauth = filter_factory(conf)(app)
        memcache = FakeMemcache()
        env = {'swift.cache': memcache,
               'SERVER_INFO': 'http://127.0.0.1',
               'SCRIPT_NAME': '', 
               'REQUEST_METHOD': 'GET', 
               'PATH_INFO': '/auth/v1.0', 
               'SERVER_PROTOCOL': 'HTTP/1.0', 
               'SERVER_NAME': '127.0.0.1', 
               'wsgi.url_scheme': 'http', 
               'SERVER_PORT': '8080', 
               'HTTP_HOST': '127.0.0.1:8080'}
        auth_token = '999888777666'
        memcache.set('auth/999888777666',
                     (time() + 10000,
                      'admin', 'admin', 'Admin',
                      'http://172.30.112.168:8080/v1.0/AUTH_admin'),
                     timeout=conf['memcache_expire'])
        self.assertEqual(kauth._accession_by_auth_token(env, auth_token), None)

        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400',
                'across_account': 'no'}
        kauth = filter_factory(conf)(app)
        env = {'swift.cache': FakeMemcache(),
               'SERVER_INFO': 'http://127.0.0.1',
               'SCRIPT_NAME': '', 
               'REQUEST_METHOD': 'GET', 
               'PATH_INFO': '/auth/v1.0', 
               'SERVER_PROTOCOL': 'HTTP/1.0', 
               'SERVER_NAME': '127.0.0.1', 
               'wsgi.url_scheme': 'http', 
               'SERVER_PORT': '8080', 
               'HTTP_HOST': '127.0.0.1:8080'}
        auth_token = '999888777666'
        self.assertEqual(kauth._accession_by_auth_token(env, auth_token), None)

    def test_valid_account_owner(self):
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test')
        self.assertTrue(self.kauth.valid_account_owner(req, 'test'))

    def test_authorize_colony(self):
        # url check
        req = Request.blank('http://127.0.0.1:8080/')
        self.assertEqual(self.kauth.authorize_colony(req).status, '404 Not Found')

        # if no account, return 401
        req = Request.blank('http://127.0.0.1:8080/v1.0')
        self.assertEqual(self.kauth.authorize_colony(req).status, '401 Unauthorized')

        # any user can GET account
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test', method='GET')
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # any user can HEAD account
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test', method='HEAD')
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # any user can PUT container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01', method='PUT')
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # any user can POST container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01', method='POST')
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # any user can DELETE container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01', method='DELETE')
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl include .rlisting, it can GET container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = '.r:*,.rlistings'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl, it can GET obj
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01/test01.txt')
        req.acl = '.r:*'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl with .rlisting, it can't GET container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = '.r:*'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req).status, '403 Forbidden')

        # if no REMOTE_USER, return 401
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01/test01.txt')
        self.assertEqual(self.kauth.authorize_colony(req).status, '401 Unauthorized')

        # acl include currect account, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl include wrong account, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req).status, '403 Forbidden')

        # acl include correct account and user, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl include wrong user, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test:tester2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req).status, '403 Forbidden')

        # acl include correct one in accounts, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test,test2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl include correct one in users, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2:tester2,test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # acl include correct one in accounts, users, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2,test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # if acl is blank, all OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.remote_user = 'test:tester,test,'
        req.acl = ''
        self.assertEqual(self.kauth.authorize_colony(req), None)

        # if req has no acl attribute, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize_colony(req).status, '403 Forbidden')


    def test_authorize(self):
        # url check
        req = Request.blank('http://127.0.0.1:8080/')
        self.assertEqual(self.kauth.authorize(req).status, '404 Not Found')

        # if no account, return 401
        req = Request.blank('http://127.0.0.1:8080/v1.0')
        self.assertEqual(self.kauth.authorize(req).status, '401 Unauthorized')

        # admin
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test')
        req.method = 'GET'
        req.remote_user = 'test:tester,test,AUTH_test'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl include .rlisting, it can GET container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = '.r:*,.rlistings'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl, it can GET obj
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01/test01.txt')
        req.acl = '.r:*'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl with .rlisting, it can't GET container
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = '.r:*'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req).status, '403 Forbidden')

        # if no REMOTE_USER, return 401
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01/test01.txt')
        req.acl = 'test'
        self.assertEqual(self.kauth.authorize(req).status, '401 Unauthorized')

        # acl include currect account, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl include wrong account, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req).status, '403 Forbidden')

        # acl include correct account and user, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl include wrong user, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test:tester2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req).status, '403 Forbidden')

        # acl include correct one in accounts, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test,test2'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl include correct one in users, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2:tester2,test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # acl include correct one in accounts, users, OK
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.acl = 'test2,test:tester'
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req), None)

        # if req has no acl attribute, NG
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST01')
        req.remote_user = 'test:tester,test,'
        self.assertEqual(self.kauth.authorize(req).status, '403 Forbidden')


    def test_denied_response(self):
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test')
        req.remote_user='test:tester,test,'
        resp = self.kauth.denied_response(req)
        self.assertEqual(resp.status, '403 Forbidden')
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test')
        resp = self.kauth.denied_response(req)
        self.assertEqual(resp.status, '401 Unauthorized')

    #@unittest.skip
    def test_get_auth_token(self):
        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        kauth = filter_factory(conf)(app)
        resp = Request.blank('/auth/v1.0',
                             headers={'X-Auth-User': 'test:tester',
                                      'X-Auth-Key': 'testing'}).get_response(kauth)
        self.assertEqual(json.loads(resp.body), 
                         {'storage': 
                          {'default': 'locals', 
                           'locals': 'http://172.30.112.168:8080/v1.0/AUTH_test'}})
        resp = Request.blank('/auth/v1.0',
                             headers={'X-Auth-User': 'test:tester',
                                      'X-Auth-Key': 'dummy'}).get_response(kauth)
        self.assertEqual(resp.status, '401 Unauthorized')
        resp = Request.blank('/auth/v1.0',
                             headers={}).get_response(kauth)
        self.assertEqual(resp.status, '401 Unauthorized')

    #@unittest.skip
    def test_connect_swift(self):
        app = DummyApp()
        conf = {'keystone_url': keystone_url,
                'region_name': 'RegionOne',
                'admin_role': 'Admin',
                'memcache_expire': '86400'}
        kauth = filter_factory(conf)(app)
        resp = Request.blank('/v1.0/AUTH_test',
                             headers={'X-Auth-Token': '999888777666'},
                             environ={'swift.cache': FakeMemcache()}).get_response(kauth)
        self.assertEqual(resp.status, '200 OK')
        self.assertEqual(app.env['PATH_INFO'], '/v1.0/AUTH_test')
        self.assertEqual(app.env['REMOTE_USER'], 'admin:admin,admin,')

        resp = Request.blank('/v1.0/AUTH_test',
                             headers={'X-Auth-Token': 'XXXXXXXXXXXX'},
                             environ={'swift.cache': FakeMemcache()}).get_response(kauth)
        self.assertEqual(resp.status, '401 Unauthorized')



# test data
keystone_url = 'http://172.30.112.168:5000'
#keystone_url = 'http://127.0.0.1:15000'
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

if __name__ == '__main__':
    unittest.main()

