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

def setUp(self):
    global _servers, proxy0_srv, proxy1_srv, webcache0_srv, proxy0_lis, \
        proxy1_lis, webcache0_lis
    nl = NullLogger()
    conf = get_config()
    proxy0_lis = listen(('localhost', 8080))
    proxy1_lis = listen(('localhost', 18080))
    webcache0_lis = listen(('localhost', 8888))
    proxy0_srv = DummySrv()
    proxy1_srv = DummySrv()
    webcache0_srv = DummySrv()
    proxy0_spa = spawn(wsgi.server, proxy0_lis, proxy0_srv, nl)
    proxy1_spa = spawn(wsgi.server, proxy1_lis, proxy1_srv, nl)
    webcache0_spa = spawn(wsgi.server, webcache0_lis, webcache0_srv, nl)
    _servers = (proxy0_spa, proxy1_spa, webcache0_spa)

def tearDown(self):
    for s in _servers:
        s.kill()

class DummySrv(object):
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        body = None
        headers = []
        if req.method == 'GET':
            status = '200 OK'
            headers.append(('content-type','text/plain'))
            if req.path == '/v1.0/AUTH_test':
                body = ['TEST0\n', 
                        'TEST1\n', 
                        'TEST2\n', 
                        'TEST3\n', 
                        'TEST4\n']
            elif req.path == '/v1.0/AUTH_test/TEST0':
                body = ['test0.txt\n', 
                        'test1.txt\n', 
                        'test2.txt\n', 
                        'test2.txt\n', 
                        'test4.txt\n']
            elif req.path == '/v1.0/AUTH_test/TEST0/test0.txt':
                body = ['This is a test0.\n',
                        'OK?']
            else:
                start_response('404 Not Found', {})
                return ''
        elif req.method == 'HEAD':
            pass
        elif req.method == 'POST':
            pass
        elif req.method == 'PUT':
            pass
        else:
            pass
        start_response(status, headers)
        return body


class TestController(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    # location str parser
    def test_LOCATION_load_location(self):
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
    
    def test_LOCATION_update_location(self):
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


    # request
    def test_REQUEST_normal_GET_account(self):
        app = TestApp(server(get_config()))
        res = app.get('/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'))
        self.assertEqual('a', proxy0_srv.env)

    def test_REQUEST_normal_GET_container(self):
        pass

    def test_REQUEST_normal_GET_object(self):
        pass

    def test_REWRITE_PATH_blank(self):
        app = TestApp(server(get_config()))
        res = app.get('/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'))
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])

    def test_REWRITE_PATH_local(self):
        app = TestApp(server(get_config()))
        res = app.get('/local/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'))
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])

    def test_REWRITE_PATH_both(self):
        app = TestApp(server(get_config()))
        res = app.get('/both/v1.0/AUTH_test', headers=dict(X_Auth_Token='t__@@__v'))
        self.assertEqual('/v1.0/AUTH_test', proxy0_srv.env['PATH_INFO'])
        self.assertEqual('/v1.0/AUTH_test', proxy1_srv.env['PATH_INFO'])

    def test_REWRITE_PATH_remote(self):
        app = TestApp(server(get_config()))
        res = app.get('/remote/v1.0/AUTH_test', headers=dict(X_Auth_Token='t'))
        self.assertEqual('/v1.0/AUTH_test', proxy1_srv.env['PATH_INFO'])

    def test_REQUEST_merge_GET_account(self):
        pass

    def test_REQUEST_merge_GET_container(self):
        pass

    def test_REQUEST_merge_GET_object(self):
        pass
