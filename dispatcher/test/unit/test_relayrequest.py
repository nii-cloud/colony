import os
import sys
try:
    import unittest2 as unittest
except (ImportError):
    import unittest
from dispatcher.server import RelayRequest as rr
from eventlet import sleep, spawn, TimeoutError, util, wsgi, listen
from swift.common.utils import normalize_timestamp, NullLogger
from webob import Request, Response
from urllib import quote, unquote, urlencode
from urlparse import urlparse, parse_qs
import json
import md5

class TmpLogger():
    def write(self, *args):
        with open('/tmp/test.log', 'a') as f:
            f.write(*args)

def setUp(self):
    global _servers, lis, srv, spa
    nl = NullLogger()
    lis = listen(('localhost', 8080))
    srv = DummySrv()
    spa = spawn(wsgi.server, lis, srv, nl)

def tearDown(self):
    spa.kill()

class DummySrv(object):
    """ """
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        if req.method == 'PUT':
            if req.body == 'This is a test':
                status = '201 Created'
            else:
                status = '500 Server Error'
            start_response(status, [('content-type', 'text/plain')])
            return ''
        status = '200 OK'
        start_response(status, [('content-type', 'text/plain')])        
        return ''


class TestController(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_GET_account(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'GET')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test')

    def test_GET_container(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'GET')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0')

    def test_GET_obj(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'GET')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')

    def test_PUT_container(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0',
                            method='PUT')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'PUT')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0')

    @unittest.skip
    def test_PUT_obj(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='PUT',
                            body='This is a test')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'PUT')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')
        self.assertEqual(resp.status, 201)

    def test_HEAD_account(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test',
                            method='HEAD')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'HEAD')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test')

    def test_HEAD_container(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0',
                            method='HEAD')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'HEAD')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0')

    def test_HEAD_obj(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='HEAD')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'HEAD')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')


    def test_POST_container(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0',
                            method='POST')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'POST')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0')

    def test_POST_obj(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='POST')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'POST')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')


    def test_DELETE_container(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0',
                            method='DELETE')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'DELETE')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0')

    def test_DELETE_obj(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='DELETE')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(srv.env['REQUEST_METHOD'], 'DELETE')
        self.assertEqual(srv.env['PATH_INFO'], '/v1.0/AUTH_test/TEST0/test0.txt')


    def test_proxy_request_check(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='GET')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        r = rr(conf, req, connect_url, proxy='http://127.0.0.1:3128')
        self.assertTrue(r._proxy_request_check('/v1.0/AUTH_test/TEST0/test0.txt'))

        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0',
                            method='GET')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0'
        r = rr(conf, req, connect_url, proxy='http://127.0.0.1:3128')
        self.assertFalse(r._proxy_request_check('/v1.0/AUTH_test/TEST0'))

        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='PUT')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        r = rr(conf, req, connect_url, proxy='http://127.0.0.1:3128')
        self.assertFalse(r._proxy_request_check('/v1.0/AUTH_test/TEST0/test0.txt'))

        req = Request.blank('http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt',
                            method='GET')
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test/TEST0/test0.txt'
        r = rr(conf, req, connect_url)
        self.assertFalse(r._proxy_request_check('/v1.0/AUTH_test/TEST0/test0.txt'))


    def test_over_max_size(self):
        conf = {}
        req = Request.blank('http://127.0.0.1:10000/v1.0/AUTH_test',
                            headers={'content-length': '5368709122'})
        connect_url = 'http://127.0.0.1:8080/v1.0/AUTH_test'
        resp = rr(conf, req, connect_url)()
        self.assertEqual(resp.status, '413 Request Entity Too Large')

