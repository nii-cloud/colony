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

class TmpLogger():
    def write(self, *args):
        with open('/tmp/test.log', 'a') as f:
            f.write(*args)

def setUp(self):
    global _servers, proxy0_srv, proxy1_srv, webcache0_srv, proxy0_lis, \
        proxy1_lis, webcache0_lis
    nl = NullLogger()
    conf = get_config()
    proxy0_lis = listen(('localhost', 8080))
    proxy1_lis = listen(('localhost', 18080))
    webcache0_lis = listen(('localhost', 8888))
    proxy0_srv = DummySrv('http://127.0.0.1:8080')
    proxy1_srv = DummySrv('http://127.0.0.1:18080')
    webcache0_srv = DummySrv('http://127.0.0.1:8888')
    proxy0_spa = spawn(wsgi.server, proxy0_lis, proxy0_srv, nl)
    proxy1_spa = spawn(wsgi.server, proxy1_lis, proxy1_srv, nl)
    webcache0_spa = spawn(wsgi.server, webcache0_lis, webcache0_srv, nl)
    _servers = (proxy0_spa, proxy1_spa, webcache0_spa)

def tearDown(self):
    for s in _servers:
        s.kill()

class DummySrv(object):
    """ """
    def __init__(self, base_url):
        self.base_url = base_url
        self.cont_list_body = ['TEST0\n', 
                               'TEST1\n', 
                               'TEST2\n', 
                               'TEST3\n', 
                               'TEST4']
        self.obj_list_body = ['test0.txt\n', 
                              'test1.txt\n', 
                              'test2.txt\n', 
                              'test2.txt\n', 
                              'test4.txt']
        self.obj_body = ['This is a test0.\n',
                         'OK?']
        self.bodies = {}
    
    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        status = None
        body = None
        headers = [('Content-Type', 'text/plain; charset=utf-8'),
                   ('Accept-Ranges', 'bytes')]

        if req.method == 'GET' or req.method == 'HEAD':
            if req.path == '/v1.0/AUTH_test':
                body = self.cont_list_body if req.method == 'GET' else ''
                headers.append(('X-Account-Bytes-Used', 20))
                headers.append(('X-Account-Container-Count', 5))
                headers.append(('X-Account-Object-Count', 1))
                if req.query_string == 'marker=TEST2':
                    body =  self.cont_list_body[3:]
                status = '200 OK' if req.method == 'GET' else '204 No Content'
            elif req.path == '/v1.0/AUTH_test/TEST0':
                body = self.obj_list_body if req.method == 'GET' else ''
                headers.append(('X-Container-Object-Count', 5))
                headers.append(('X-Container-Bytes-Used', 20))
                status = '200 OK' if req.method == 'GET' else '204 No Content'
            elif req.path == '/v1.0/AUTH_test/TEST0/test0.txt' or \
                    req.path == quote('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'):
                body = self.obj_body if req.method == 'GET' else ''
                headers.append(('Etag', md5.new(''.join(body)).hexdigest()))
                status = '200 OK' if req.method == 'GET' else '204 No Content'
            elif req.path in self.bodies:
                cat = []
                for d in self.bodies.keys():
                    if d.startswith(req.path):
                        cat.append(self.bodies[d])
                if len(cat) > 0:
                    cat.sort(lambda x, y: cmp(y, x))
                    body = ''.join(cat)
                else:
                    body = self.bodies[req.path]
                headers.append(('Etag', md5.new(body).hexdigest()))
                status = '200 OK'
            elif req.path == '/auth/v1.0':
                headers = []
                auth_res = {'storage': {'default': 'locals', 'locals': '%s/v1.0/AUTH_test' % self.base_url}}
                body = json.dumps(auth_res)
                headers.append(('X-Storage-Url', '%s/v1.0/AUTH_test' % self.base_url))
                headers.append(('X-Auth-Token', 'dummy'))
                headers.append(('X-Storage-Token', 'dummy'))
                headers.append(('Content-Type', 'application/json'))
                status = '200 OK'
            else:
                start_response('404 Not Found', [('content-type','text/plain')])
                return ''
        elif req.method == 'PUT':
            self.bodies[req.path] = req.body
            headers = []
            body = ['<html>',
                    '<head><title>201 Created</title></head>', 
                    '<body><h1>201 Created</h1><br /><br /></body>',
                    '</html>']
            headers.append(('Content-Type', 'text/html; charset=UTF-8'))
            headers.append(('X-Copied-From', 'TEST0/test0.txt'))
            status = '201 Created'
        elif req.method == 'POST':
            pass
        elif req.method == 'DELETE':
            pass
        else:
            pass
        start_response(status, headers)
        return body

class TestController(unittest.TestCase):
    def setUp(self):
        self.app = TestApp(server(get_config()))

    def tearDown(self):
        pass

    # location str parser
    def test_01_LOCATION_load_location(self):
        """ location str parse and construct server info from server.txt"""
        loc_str = ':test/server0.txt, local:test/server1.txt, both:(hoge)test/server2.txt (gere)test/server3.txt, remote:test/server4.txt'
        loc = Location(loc_str)
        self.assertEqual({'webcache': {'http://127.0.0.1:8080': 'http://127.0.0.1:8888'}, 
                          'container_prefix': {'http://127.0.0.1:8080': None}, 
                          'swift': [['http://127.0.0.1:8080']]}, 
                         loc.servers_of(''))
        self.assertEqual({'webcache': {'http://127.0.0.1:8080': None}, 
                          'container_prefix': {'http://127.0.0.1:8080': None}, 
                          'swift': [['http://127.0.0.1:8080']]},
                         loc.servers_of('local'))
        self.assertEqual({'webcache': {'http://127.0.0.1:18080': None, 'http://127.0.0.1:8080': None}, 
                          'container_prefix': {'http://127.0.0.1:18080': 'gere', 'http://127.0.0.1:8080': 'hoge'}, 
                          'swift': [['http://127.0.0.1:8080'], ['http://127.0.0.1:18080']]},
                         loc.servers_of('both'))
        self.assertEqual({'webcache': {'http://127.0.0.1:18080': None}, 
                          'container_prefix': {'http://127.0.0.1:18080': None}, 
                          'swift': [['http://127.0.0.1:18080']]},
                         loc.servers_of('remote'))
        self.assertEqual([['http://127.0.0.1:8080']], loc.swift_of(''))
        self.assertEqual([['http://127.0.0.1:8080']], loc.swift_of('local'))
        self.assertEqual([['http://127.0.0.1:8080'], ['http://127.0.0.1:18080']], loc.swift_of('both'))
        self.assertEqual([['http://127.0.0.1:18080']], loc.swift_of('remote'))
        self.assertEqual(False, loc.is_merged(''))
        self.assertEqual(False, loc.is_merged('local'))
        self.assertEqual(True, loc.is_merged('both'))
        self.assertEqual(False, loc.is_merged('remote'))
        self.assertEqual(None, loc.container_prefix_of('', 'http://127.0.0.1:8080'))
        self.assertEqual('hoge', loc.container_prefix_of('both', 'http://127.0.0.1:8080'))
        self.assertEqual('gere', loc.container_prefix_of('both', 'http://127.0.0.1:18080'))
        self.assertEqual({'http://127.0.0.1:8080': 'http://127.0.0.1:8888'}, loc.webcache_of(''))
        self.assertEqual({'http://127.0.0.1:8080': None},  loc.webcache_of('local'))
        self.assertEqual({'http://127.0.0.1:18080': None, 'http://127.0.0.1:8080': None}, loc.webcache_of('both'))
        self.assertEqual({'http://127.0.0.1:18080': None}, loc.webcache_of('remote'))
        self.assertEqual({'http://127.0.0.1:8080': None}, loc.container_prefixes_of(''))
        self.assertEqual({'http://127.0.0.1:8080': None},  loc.container_prefixes_of('local'))
        self.assertEqual({'http://127.0.0.1:18080': 'gere', 'http://127.0.0.1:8080': 'hoge'}, loc.container_prefixes_of('both'))
        self.assertEqual({'http://127.0.0.1:18080': None}, loc.container_prefixes_of('remote'))
        self.assertEqual( ['http://127.0.0.1:8080'], loc.servers_by_container_prefix_of('both', 'hoge'))
        self.assertEqual( ['http://127.0.0.1:18080'], loc.servers_by_container_prefix_of('both', 'gere'))
        self.assertEqual('http://127.0.0.1:9999', 
                         loc._sock_connect_faster(['http://127.0.0.1:8080', 
                                                   'http://127.0.0.1:18080', 
                                                   'http://127.0.0.1:9999'])[2])
    
    def test_02_LOCATION_update_location(self):
        """ server.txt reload if update."""
        loc_str = ':test/server0.txt, local:test/server1.txt, both:(hoge)test/server2.txt (gere)test/server3.txt, remote:test/server4.txt'
        loc = Location(loc_str)
        old_server2_swifts = loc.swift_of('remote')
        with open('test/server4.txt', 'r') as f:
            olddata = f.read()
        with open('test/server4.txt', 'w') as f:
            f.write('http://192.168.2.1:8080')
        loc.reload()
        with open('test/server4.txt', 'w') as f:
            f.write(olddata)
        self.assertEqual([['http://192.168.2.1:8080']], 
                         loc.swift_of('remote'))

        
    # rewrite url
    def test_03_REWRITE_PATH_blank(self):
        """ rewrite path when location prefix is blank."""
        res = self.app.get('/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'), expect_errors=True)
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])

    def test_04_REWRITE_PATH_local(self):
        """ rewrite path when location prefix is 'local'."""
        res = self.app.get('/local/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'), expect_errors=True)
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])

    def test_05_REWRITE_PATH_both(self):
        """ rewrite path when location prefix is 'both' (merge mode)."""
        res = self.app.get('/both/v1.0/AUTH_test', headers=dict(X_Auth_Token='t__@@__v'), expect_errors=True)
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])
        self.assertEqual('/v1.0/AUTH_test', proxy1_srv.env['PATH_INFO'])

    def test_06_REWRITE_PATH_remote(self):
        """ rewrite path when location prefix is 'remote'."""
        res = self.app.get('/remote/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'), expect_errors=True)
        self.assertEqual('/v1.0/AUTH_test', proxy1_srv.env['PATH_INFO'])

    # auth request in normal
    def test_07_REQUEST_normal_GET_auth(self):
        """ rewrite auth info from swift in normal mode. """
        res = self.app.get('/local/auth/v1.0', 
                           headers={'X-Auth-User': 'test:tester', 
                                    'X-Auth-Key': 'testing'})
        print res.body
        print res.headers
        body = {'storage': {'default': 'locals', 
                            'locals': 'http://127.0.0.1:10000/local/v1.0/AUTH_test'}}
        self.assertEqual(res.headers['x-storage-url'], 'http://127.0.0.1:10000/local/v1.0/AUTH_test')
        self.assertEqual(res.headers['x-auth-token'], 'dummy')
        self.assertEqual(res.headers['x-storage-token'], 'dummy')
        self.assertEqual(body, json.loads(res.body))

    # request relay
    def test_08_REQUEST_normal_GET_account(self):
        """ relay to get account (container listing) in normal mode. """
        res = self.app.get('/local//v1.0/AUTH_test', headers=dict(X_Auth_Token='t'))
        body='TEST0\nTEST1\nTEST2\nTEST3\nTEST4'
        self.assertEqual(body, res.body)

    def test_09_REQUEST_normal_GET_container(self):
        """ relay to get container (object listing) in normal mode. """
        res = self.app.get('/local/v1.0/AUTH_test/TEST0', headers=dict(X_Auth_Token='t'))
        body = 'test0.txt\ntest1.txt\ntest2.txt\ntest2.txt\ntest4.txt'
        print proxy0_srv.env
        self.assertEqual(body, res.body)

    def test_10_REQUEST_normal_GET_object(self):
        """ relay to get object in normal mode. """
        res = self.app.get('/local/v1.0/AUTH_test/TEST0/test0.txt', headers=dict(X_Auth_Token='t'))
        body = 'This is a test0.\nOK?'
        self.assertEqual(body, res.body)

    # request via webcache
    def test_11_REQUEST_normal_GET_object_via_webcache(self):
        """ relay to get object in normal mode via WebCache. """
        res = self.app.get('/v1.0/AUTH_test/TEST0/test0.txt', headers=dict(X_Auth_Token='t'))
        self.assertEqual('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt', 
                         webcache0_srv.env['PATH_INFO'])

    # auth request in merge
    #@unittest.skip
    def test_12_REQUEST_merge_GET_auth(self):
        """ rewrite auth info from swift in merge mode. """
        res = self.app.get('/both/auth/v1.0', 
                           headers={'X-Auth-User': 'test:tester', 
                                    'X-Auth-Key': 'testing'})
        print res.body
        print res.headers
        body = {'storage': {'default': 'locals', 
                            'locals': 'http://127.0.0.1:10000/both/v1.0/AUTH_test'}}
        self.assertEqual(res.headers['x-storage-url'], 'http://127.0.0.1:10000/both/v1.0/AUTH_test')
        self.assertEqual(res.headers['x-auth-token'], 'dummy__@@__dummy')
        self.assertEqual(res.headers['x-storage-token'], 'dummy__@@__dummy')
        self.assertEqual(body, json.loads(res.body))

    # request relay in merge mode
    #@unittest.skip
    def test_13_REQUEST_merge_GET_account(self):
        """ relay to get account (container listing) in merge mode. """
        res = self.app.get('/both/v1.0/AUTH_test', headers=dict(X_Auth_Token='t__@@__v'))
        body = 'gere:TEST0\ngere:TEST1\ngere:TEST2\ngere:TEST3\ngere:TEST4\n' + \
            'hoge:TEST0\nhoge:TEST1\nhoge:TEST2\nhoge:TEST3\nhoge:TEST4'
        print res.body
        print res.headers
        self.assertEqual(res.headers['x-account-bytes-used'], '40')
        self.assertEqual(res.headers['x-account-container-count'], '10')
        self.assertEqual(res.headers['x-account-object-count'], '2')
        self.assertEqual(body, res.body)

    def test_14_REQUEST_merge_GET_account_with_marker(self):
        """ relay to get account (container listing) in merge mode with marker param. """
        res = self.app.get('/both/v1.0/AUTH_test?marker=hoge:TEST2', headers=dict(X_Auth_Token='t__@@__v'))
        body = 'hoge:TEST3\nhoge:TEST4'
        print res.body
        print res.headers
        self.assertEqual(body, res.body)

    def test_15_REQUEST_merge_GET_container(self):
        """ relay to get container (object listing) in merge mode. """
        res = self.app.get('/both/v1.0/AUTH_test/hoge:TEST0', headers=dict(X_Auth_Token='t__@@__v'), expect_errors=True)
        body = 'test0.txt\ntest1.txt\ntest2.txt\ntest2.txt\ntest4.txt'
        #print self.app.app.debug
        print res.status
        print res.body
        print res.headers
        print proxy0_srv.env
        print proxy1_srv.env
        self.assertEqual(body, res.body)

    def test_16_REQUEST_merge_GET_object(self):
        """ relay to get object in merge mode. """
        res = self.app.get('/both/v1.0/AUTH_test/hoge:TEST0/test0.txt', headers=dict(X_Auth_Token='t__@@__v'), expect_errors=True)
        body = 'This is a test0.\nOK?'
        self.assertEqual(body, res.body)

    def test_17_REQUEST_merge_COPY_object_in_same_account(self):
        """ relay to copy object in the same account. """
        res = self.app.request('/both/v1.0/AUTH_test/hoge:TEST1/copied_test0.txt', method='PUT', body='',
                               headers={'X_Auth_Token': 't__@@__v',
                                        'X_Copy_From': '/hoge:TEST0/test0.txt'},
                               expect_errors=True)
        print res.status
        print res.body
        self.assertEqual(proxy0_srv.env['CONTENT_LENGTH'], '0')
        self.assertEqual(proxy0_srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST1/copied_test0.txt')
        self.assertEqual(proxy0_srv.env['HTTP_X_COPY_FROM'], '/TEST0/test0.txt')
    
    def test_18_REQUEST_merge_COPY_object_across_accounts(self):
        """ relay to copy object across accounts. """
        res = self.app.request('/both/v1.0/AUTH_test/gere:TEST1/copied_test0.txt', method='PUT', body='',
                               headers={'X_Auth_Token': 't__@@__v',
                                        'X_Copy_From': '/hoge:TEST0/test0.txt'},
                               expect_errors=True)
        print proxy0_srv.env
        print proxy0_srv.env['REQUEST_METHOD']
        print proxy0_srv.env['PATH_INFO']
        print proxy1_srv.env
        print proxy1_srv.env['REQUEST_METHOD']
        print proxy1_srv.env['PATH_INFO']
        self.assertEqual(proxy0_srv.env['SERVER_NAME'], '127.0.0.1')
        self.assertEqual(proxy0_srv.env['SERVER_PORT'], '8080')
        self.assertEqual(proxy0_srv.env['REQUEST_METHOD'], 'GET')
        self.assertEqual(proxy0_srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')
        self.assertEqual(proxy1_srv.env['SERVER_NAME'], '127.0.0.1')
        self.assertEqual(proxy1_srv.env['SERVER_PORT'], '18080')
        self.assertEqual(proxy1_srv.env['REQUEST_METHOD'], 'PUT')
        self.assertEqual(proxy1_srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST1/copied_test0.txt')
        res = self.app.get('/both/v1.0/AUTH_test/gere:TEST1/copied_test0.txt', headers=dict(X_Auth_Token='t__@@__v'), expect_errors=True)
        body = 'This is a test0.\nOK?'
        print res.body
        self.assertEqual(body, res.body)

    #@unittest.skip
    def test_19_REQUEST_merge_COPY_object_across_accounts_with_split_upload(self):
        """ relay to copy object across accounts with split uploading. """
        swift_store_large_chunk_size  = self.app.app.swift_store_large_chunk_size
        self.app.app.no_split_copy_max_size = 15
        res = self.app.request('/both/v1.0/AUTH_test/gere:TEST1/copied_test0.txt', method='PUT', body='',
                               headers={'X_Auth_Token': 't__@@__v',
                                        'X_Copy_From': '/hoge:TEST0/test0.txt'},
                               expect_errors=True)
        self.app.app.swift_store_large_chunk_size = swift_store_large_chunk_size
        print proxy0_srv.env
        print proxy0_srv.env['REQUEST_METHOD']
        print proxy0_srv.env['PATH_INFO']
        print proxy1_srv.env
        print proxy1_srv.env['REQUEST_METHOD']
        print proxy1_srv.env['PATH_INFO']
        self.assertEqual(proxy0_srv.env['SERVER_NAME'], '127.0.0.1')
        self.assertEqual(proxy0_srv.env['SERVER_PORT'], '8080')
        self.assertEqual(proxy0_srv.env['REQUEST_METHOD'], 'GET')
        self.assertEqual(proxy0_srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')
        self.assertEqual(proxy1_srv.env['SERVER_NAME'], '127.0.0.1')
        self.assertEqual(proxy1_srv.env['SERVER_PORT'], '18080')
        self.assertEqual(proxy1_srv.env['REQUEST_METHOD'], 'PUT')
        self.assertEqual(proxy1_srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST1/copied_test0.txt')
        res = self.app.get('/both/v1.0/AUTH_test/gere:TEST1/copied_test0.txt', headers=dict(X_Auth_Token='t__@@__v'), expect_errors=True)
        body = 'This is a test0.\nOK?'
        print res.body
        self.assertEqual(body, res.body)

