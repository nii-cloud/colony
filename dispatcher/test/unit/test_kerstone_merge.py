import os
import sys
try:
    import unittest2 as unittest
except (ImportError):
    import unittest
from dispatcher.server import Dispatcher as server
from dispatcher.common.middleware.keystone_merge import KeystoneMerge as ksm
from dispatcher.common.middleware.keystone_merge import filter_factory
from eventlet import sleep, spawn, TimeoutError, util, wsgi, listen
from swift.common.utils import normalize_timestamp, NullLogger
from test import get_config
from webob import Request, Response
from webtest import TestApp
import json
from urlparse import urlparse

class TmpLogger():
    def write(self, *args):
        with open('/tmp/test.log', 'a') as f:
            f.write(*args)

def setUp(self):
    pass

def tearDown(self):
    pass

class DummyApp(object):
    """ """
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        """ """
        self.env = env
        req = Request(env)
        status = '200 OK'
        return Response(status=status)

class TestController(unittest.TestCase):
    def setUp(self):
        conf = {'keystone_relay_path': '/both/v2.0',
                'keystone_relay_token_paths': '/both/v2.0/tokens /both/v2.0/token_by',
                'keystone_one_url': 'http://192.168.2.100:5001',
                'keystone_other_url': 'http://192.168.2.200:5001',
                'dispatcher_base_url': 'http://192.168.2.1:10000',
                'region_name': 'RegionOne'}
        self.k = filter_factory(conf)(DummyApp())
        #self.assertEqual(dir(self.k),'')

    def tearDown(self):
        pass

    def test_is_keystone_req(self):
        req = Request.blank('http://192.168.2.1:10000/both/v2.0')
        self.assertTrue(self.k.is_keystone_req(req))
        req = Request.blank('http://192.168.2.1:10000/v2.0')
        self.assertFalse(self.k.is_keystone_req(req))

    def test_is_keystone_auth_token_req(self):
        req = Request.blank('http://192.168.2.1:10000/both/v2.0/tokens')
        req.method = 'POST'
        req.content_type = 'application/json'
        self.assertTrue(self.k.is_keystone_auth_token_req(req))
        req = Request.blank('http://192.168.2.1:10000/both/v2.0/dummy_tokens')
        self.assertFalse(self.k.is_keystone_auth_token_req(req))

    def test_merged_request_token_split(self):
        #self.k._merged_request_token_split(request)
        pass

    def test_access_info_merge(self):
        pass

    def test_token_merge(self):
        pass

    def test_swift_catalog_merge(self):
        pass

    def test_get_merged_common_path(self):
        urls = ['http://192.168.2.0:8080/v2.0/tokens', 
                'http://172.16.2.0:8080/v2.0/tokens']
        self.assertEqual(self.k._get_merged_common_path(urls), '/v2.0/tokens')

    def test_merge_headers(self):
        pass

    def test_split_netloc(self):
        self.assertEqual(self.k._split_netloc(urlparse('http://192.168.2.1:8080/')), 
                         ('192.168.2.1', '8080'))
        self.assertEqual(self.k._split_netloc(urlparse('http://192.168.2.1/')),
                         ('192.168.2.1', '80'))
        self.assertEqual(self.k._split_netloc(urlparse('https://192.168.2.1/')),
                         ('192.168.2.1', '443'))

    def test_pass_through(self):
        pass

    def test_auth_token(self):
        pass
