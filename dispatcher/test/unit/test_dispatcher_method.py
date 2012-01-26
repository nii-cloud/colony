import os
import sys
try:
    import unittest2 as unittest
except (ImportError):
    import unittest
from dispatcher.server import Dispatcher as server
from dispatcher.common.location import Location
from eventlet import sleep, spawn, TimeoutError, util, wsgi, listen
from swift.common.utils import normalize_timestamp, NullLogger
from test import get_config
from webob import Request, Response
from webtest import TestApp
from urllib import quote, unquote, urlencode
from urlparse import urlparse, parse_qs
import json
import md5

def setUp(self):
    pass

def tearDown(self):
    pass

class TestController(unittest.TestCase):
    def setUp(self):
        self.app = TestApp(server(get_config()))

    def tearDown(self):
        pass

    # utils
    def test_check_error_resp(self):
        """ check_error_resp """
        resp0 = Response(status='401 Unauthorized')
        resp1 = Response(status='404 Not Found')
        resp2 = Response(status='200 OK')
        resp3 = Response(status='500 Server Error')
        resps = [resp0, resp1, resp2]
        resp = self.app.app.check_error_resp(resps)
        self.assertEqual(resp.status, '404 Not Found')
        resps.append(resp3)
        resp = self.app.app.check_error_resp(resps)
        self.assertEqual(resp.status, '500 Server Error')

    def test_location_check(self):
        """ location_check """
        req = Request.blank('/v1.0/AUTH_test')
        self.assertEqual(self.app.app.location_check(req), None)
        req = Request.blank('/auth/v1.0')
        self.assertEqual(self.app.app.location_check(req), None)
        req = Request.blank('/local/v1.0/AUTH_test')
        self.assertEqual(self.app.app.location_check(req), 'local')

    def test_get_real_path(self):
        """ get_real_path """
        req = Request.blank('/v1.0/AUTH_test')        
        self.assertEqual(self.app.app._get_real_path(req), ['v1.0', 'AUTH_test'])
        req = Request.blank('/local/v1.0/AUTH_test')        
        self.assertEqual(self.app.app._get_real_path(req), ['v1.0', 'AUTH_test'])

    def test_auth_check(self):
        """ auth_check """
        req = Request.blank('/v1.0/AUTH_test')
        self.assertFalse(self.app.app._auth_check(req))
        req.headers['x-auth-token'] = 'dummy'
        req.headers['x-storage-token'] = 'dummy'
        self.assertTrue(self.app.app._auth_check(req))

    def test_get_merged_path(self):
        """ get_merged_path """
        req = Request.blank('/both/v1.0/AUTH_test/hoge:TEST0/test0.txt')
        self.assertEqual(self.app.app._get_merged_path(req), ('AUTH_test', 'hoge', 'TEST0', 'test0.txt'))
        req = Request.blank('/both/v1.0/AUTH_test/hoge:TEST0')
        self.assertEqual(self.app.app._get_merged_path(req), ('AUTH_test', 'hoge', 'TEST0', None))
        req = Request.blank('/both/v1.0/AUTH_test/hoge%3ATEST0/test0.txt')
        self.assertEqual(self.app.app._get_merged_path(req), ('AUTH_test', 'hoge', 'TEST0', 'test0.txt'))
        req = Request.blank('/both/v1.0/AUTH_test/hoge%3ATEST0')
        self.assertEqual(self.app.app._get_merged_path(req), ('AUTH_test', 'hoge', 'TEST0', None))
        req = Request.blank('/both/v1.0/AUTH_test')
        self.assertEqual(self.app.app._get_merged_path(req), ('AUTH_test', None, None, None))
        req = Request.blank('/both')
        self.assertEqual(self.app.app._get_merged_path(req), (None, None, None, None))

    def test_get_container_prefix(self):
        """ get_container_prefix """
        container = 'hoge:TEST0'
        self.assertEqual(self.app.app._get_container_prefix(container), 'hoge')
        container = 'TEST0'
        self.assertEqual(self.app.app._get_container_prefix(container), None)

    def test_get_copy_from(self):
        """ get_copy_from """
        req = Request.blank('/both/v1.0/AUTH_test/gere:TEST0/copied_test0.txt')
        req.headers['x-copy-from'] = '/hoge:TEST0/test0.txt'
        self.assertEqual(self.app.app._get_copy_from(req), ('hoge', 'TEST0', 'test0.txt'))

    def test_merge_headers(self):
        """ merge_headers """
        resp0 = Response()
        resp0.headers['x-storage-url'] = 'http://192.168.2.0:8080/v1.0/AUTH_test'
        resp0.headers['x-auth-token'] = 'dummy0'
        resp0.headers['x-account-bytes-used'] = '1024'
        resp0.headers['x-account-container-count'] = '10'
        resp0.headers['x-account-object-count'] = '5'
        resp1 = Response()
        resp1.headers['x-storage-url'] = 'http://172.16.2.0:8080/v1.0/AUTH_test'
        resp1.headers['x-auth-token'] = 'dummy1'
        resp1.headers['x-account-bytes-used'] = '1024'
        resp1.headers['x-account-container-count'] = '10'
        resp1.headers['x-account-object-count'] = '5'
        resps = [resp0, resp1]
        self.assertEqual(self.app.app._merge_headers(resps, 'both'), 
                         [('x-storage-url', 'http://127.0.0.1:10000/both/v1.0/AUTH_test'), 
                          ('x-auth-token', 'dummy0__@@__dummy1'), 
                          ('x-storage-token', 'dummy0__@@__dummy1'), 
                          ('x-account-bytes-used', '2048'), 
                          ('x-account-container-count', '20'), 
                          ('x-account-object-count', '10'), 
                          ('Content-Length', '0'), 
                          ('Content-Type', 'text/html; charset=UTF-8')] )

    def test_get_merged_common_path(self):
        """ get_merged_common_path """
        urls = ['http://192.168.2.0:8080/v1.0/AUTH_test', 
                'http://172.16.2.0:8080/v1.0/AUTH_test']
        self.assertEqual(self.app.app._get_merged_common_path(urls), '/v1.0/AUTH_test')


    def test_get_merged_storage_url(self):
        """ get_merged_storage_url """
        urls = ['http://192.168.2.0:8080/v1.0/AUTH_test', 
                'http://172.16.2.0:8080/v1.0/AUTH_test']
        self.assertEqual(self.app.app._get_merged_storage_url(urls, 'both'), 
                         'http://127.0.0.1:10000/both/v1.0/AUTH_test')

    def test_has_header(self):
        """ has_header """
        resp0 = Response()
        resp0.headers['x-account-byte-used'] = '100'
        resp1 = Response()
        resps = [resp0, resp1]
        self.assertTrue(self.app.app._has_header('x-account-byte-used', resps))
        self.assertFalse(self.app.app._has_header('x-account-container-count', resps))

    def test_merge_storage_url_body(self):
        """ merge_storage_url_body """
        bodies = ['{"storage": {"default": "locals", "locals": "http://192.168.2.0:8080/v1.0/AUTH_test"}}',
                  '{"storage": {"default": "locals", "locals": "http://172.16.2.0:8080/v1.0/AUTH_test"}}']
        self.assertEqual(self.app.app._merge_storage_url_body(bodies, 'both'), 
                         '{"storage": {"default": "locals", "locals": "http://127.0.0.1:10000/both/v1.0/AUTH_test"}}')

    def test_get_each_tokens(self):
        """ get_each_tokens """
        req = Request.blank('/v1.0/AUTH_test')
        req.headers['x-auth-token'] = 'dummy0'
        req.headers['x-storage-token'] = 'dummy0'
        self.assertFalse(self.app.app._get_each_tokens(req), None)
        req.headers['x-auth-token'] = 'dummy0__@@__dummy1'
        req.headers['x-storage-token'] = 'dummy0__@@__dummy1'
        self.assertEqual(self.app.app._get_each_tokens(req), ['dummy0','dummy1'])

    def test_get_servers_subscript_by_prefix(self):
        """ get_servers_subscript_by_prefix """
        self.assertEqual(self.app.app._get_servers_subscript_by_prefix('both', 'hoge'), 0)
        self.assertEqual(self.app.app._get_servers_subscript_by_prefix('both', 'gere'), 1)

    def test_combinate_url(self):
        """ combinate_url """
        req = Request.blank('http://127.0.0.1:10000/both/v1.0/AUTH_test/hoge:TEST0/test0.txt?hoge=hoge')
        query = parse_qs(urlparse(req.url).query)
        self.assertEqual(self.app.app._combinate_url(req, 'http://192.168.2.1:8080', '/v1.0/AUTH_test', query),
                         'http://192.168.2.1:8080/v1.0/AUTH_test?hoge=hoge')

    def test_rewrite_object_manifest_header(self):
        """ rewrite_object_manifest_header """
        headers = [('x-auth-token', 'dummy0__@@__dummy1'), 
                   ('x-storage-token', 'dummy0__@@__dummy1'), 
                   ('x-object-manifest', 'TEST0/test0.txt/1325822579.097868/254/'),
                   ('Content-Length', '0'), 
                   ('Content-Type', 'text/html; charset=UTF-8')]
        rewrite_h = self.app.app._rewrite_object_manifest_header(headers, 'hoge')
        object_manifest = None
        for h, v in rewrite_h:
            if h == 'x-object-manifest':
                object_manifest = v
        self.assertEqual(object_manifest, 'hoge:TEST0/test0.txt/1325822579.097868/254/')

    def test_rewrite_storage_url_header(self):
        """ rewrite_storage_url_header """
        headers = [('x-auth-token', 'dummy0'), 
                   ('x-storage-token', 'dummy0'), 
                   ('x-storage-url', 'http://192.168.2.1:8080/v1.0/AUTH_test')]
        self.assertEqual(self.app.app._rewrite_storage_url_header(headers, 'local'), 
                         [('x-auth-token', 'dummy0'), 
                          ('x-storage-token', 'dummy0'), 
                          ('x-storage-url', 'http://127.0.0.1:10000/local/v1.0/AUTH_test')])
        self.assertEqual(self.app.app._rewrite_storage_url_header(headers), 
                         [('x-auth-token', 'dummy0'), 
                          ('x-storage-token', 'dummy0'), 
                          ('x-storage-url', 'http://127.0.0.1:10000/v1.0/AUTH_test')])

    def test_rewrite_storage_url_body(self):
        """ rewrite_storage_url_body """
        body = '{"storage": {"default": "locals", "locals": "http://172.16.2.0:8080/v1.0/AUTH_test"}}'
        self.assertEqual(self.app.app._rewrite_storage_url_body(body, None), 
                         '{"storage": {"default": "locals", "locals": "http://127.0.0.1:10000/v1.0/AUTH_test"}}')
        self.assertEqual(self.app.app._rewrite_storage_url_body(body, 'local'), 
                         '{"storage": {"default": "locals", "locals": "http://127.0.0.1:10000/local/v1.0/AUTH_test"}}')

    def test_merge_container_lists(self):
        """ merge_container_lists """
        prefixes = ['hoge', 'gere']
        text0 = 'TEST0\nTEST1\nTEST2\nTEST3\nTEST4'
        text1 = 'TEST5\nTEST6\nTEST7\nTEST8\nTEST9'
        self.assertEqual(self.app.app._merge_container_lists('text/plain', [text0, text1], prefixes),
                         'gere:TEST5\ngere:TEST6\ngere:TEST7\ngere:TEST8\ngere:TEST9\nhoge:TEST0\nhoge:TEST1\nhoge:TEST2\nhoge:TEST3\nhoge:TEST4')
        json0 = [{'name':'TEST0','count':1,'bytes':256},
                 {'name':'TEST1','count':0,'bytes':0},
                 {'name':'TEST2','count':0,'bytes':0},
                 {'name':'TEST3','count':0,'bytes':0},
                 {'name':'TEST4','count':0,'bytes':0}]
        json1 = [{'name':'TEST5','count':1,'bytes':256},
                 {'name':'TEST6','count':0,'bytes':0},
                 {'name':'TEST7','count':0,'bytes':0},
                 {'name':'TEST8','count':0,'bytes':0},
                 {'name':'TEST9','count':0,'bytes':0}]
        json_result = [{'count': 1, 'bytes': 256, 'name': 'hoge:TEST0'}, 
                       {'count': 0, 'bytes': 0, 'name': 'hoge:TEST1'}, 
                       {'count': 0, 'bytes': 0, 'name': 'hoge:TEST2'}, 
                       {'count': 0, 'bytes': 0, 'name': 'hoge:TEST3'}, 
                       {'count': 0, 'bytes': 0, 'name': 'hoge:TEST4'}, 
                       {'count': 1, 'bytes': 256, 'name': 'gere:TEST5'}, 
                       {'count': 0, 'bytes': 0, 'name': 'gere:TEST6'}, 
                       {'count': 0, 'bytes': 0, 'name': 'gere:TEST7'}, 
                       {'count': 0, 'bytes': 0, 'name': 'gere:TEST8'}, 
                       {'count': 0, 'bytes': 0, 'name': 'gere:TEST9'}]
        self.assertEqual(self.app.app._merge_container_lists('application/json', [json.dumps(json0), json.dumps(json1)], prefixes),
                         json.dumps(json_result))
