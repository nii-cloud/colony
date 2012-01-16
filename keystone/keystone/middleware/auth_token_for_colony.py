#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
TOKEN-BASED AUTH MIDDLEWARE

This WSGI component performs multiple jobs:
- it verifies that incoming client requests have valid tokens by verifying
    tokens with the auth service.
- it will reject unauthenticated requests UNLESS it is in 'delay_auth_decision'
    mode, which means the final decision is delegated to the downstream WSGI
    component (usually the OpenStack service)
- it will collect and forward identity information from a valid token
    such as user name etc...

Refer to: http://wiki.openstack.org/openstack-authn


HEADERS
-------
Headers starting with HTTP_ is a standard http header
Headers starting with HTTP_X is an extended http header

> Coming in from initial call from client or customer
HTTP_X_AUTH_TOKEN   : the client token being passed in
HTTP_X_STORAGE_TOKEN: the client token being passed in (legacy Rackspace use)
                      to support cloud files
> Used for communication between components
www-authenticate    : only used if this component is being used remotely
HTTP_AUTHORIZATION  : basic auth password used to validate the connection

> What we add to the request for use by the OpenStack service
HTTP_X_AUTHORIZATION: the client identity being passed in


Swift Proxy Setting
-------
[pipeline:main]
pipeline = healthcheck cache swift3 keystone proxy-server

[filter:keystone]
use = egg:keystone#tokenauth_colony
keystone_url = http://172.30.112.168:5000
region_name = RegionOne
admin_role = Admin
memcache_expire = 86400

"""

import eventlet
from eventlet import wsgi
import base64
from hashlib import md5, sha1
import hmac
import httplib
import json
import os
from paste.deploy import loadapp
from time import time
from urllib import unquote
from urlparse import urlparse
from webob.exc import HTTPUnauthorized, HTTPUseProxy, HTTPForbidden, HTTPUnauthorized, HTTPNotFound
from webob import Request, Response
import keystone.tools.tracer  # @UnusedImport # module runs on import

from keystone.common.bufferedhttp import http_connect_raw as http_connect
from swift.common.middleware.acl import clean_acl, parse_acl, referrer_allowed
from swift.common.utils import cache_from_env, split_path, TRUE_VALUES, get_logger

PROTOCOL_NAME = "Token Authentication"


class AuthProtocol(object):
    """Auth Middleware that handles authenticating client calls"""

    def __init__(self, app, conf):
        """ Common initialization code """

        # add by colony. conf tokens be simple.
        self.conf = conf
        self.app = app
        self.logger = get_logger(conf, log_route='auth_token_colony')
        keystone_url = conf.get('keystone_url')
        parsed = urlparse(keystone_url)
        self.auth_netloc = parsed.netloc
        self.auth_protocol = parsed.scheme
        self.auth_location = keystone_url
        self.region_name = conf.get('region_name')
        self.admin_role = conf.get('admin_role', 'Admin')
        # for ACL setting for containers of an account which others possesses.
        self.across_account = conf.get('across_account', 'yes').lower() in TRUE_VALUES
        self.memcache_expire = float(conf.get('memcache_expire', 86400))

    def __call__(self, env, start_response):
        """ Handle incoming request. Authenticate. And send downstream. """

        #Prep headers to forward request to local or remote downstream service
        proxy_headers = env.copy()
        for header in proxy_headers.iterkeys():
            if header[0:5] == 'HTTP_':
                proxy_headers[header[5:]] = proxy_headers[header]
                del proxy_headers[header]

        # get auth token from keystone at first, like swauth. add by colony
        auth_user = self._get_auth_user(env)
        if auth_user and env['PATH_INFO'] == '/auth/v1.0':
            authencated = self._validate_claims_each_user(auth_user)
            if not authencated:
                return self._reject_request(env, start_response)
            headers, body = authencated
            req = Request(env)
            resp = Response(request=req, body=body, headers=headers)
            start_response(resp.status, resp.headerlist)
            return resp.body

        #Look for authentication claims
        claims = self._get_claims(env)
        if not claims:
            return self._reject_request(env, start_response)

        # check auth token with no admin privilege. add by colony
        result = self._accession_by_auth_token(env, claims)

        if not result:
            return self._reject_request(env, start_response)
        tenant, username, roles, storage_url = result
        self._decorate_request('X_AUTHORIZATION', "Proxy %s" %
                               username, env, proxy_headers)
        self._decorate_request('X_TENANT',
                               tenant, env, proxy_headers)
        self._decorate_request('X_USER',
                               username, env, proxy_headers)
        env['REMOTE_USER'] = '%s:%s,%s,%s' % \
            (tenant, username, tenant, '')
            # (tenant, username, tenant, \
            #      'AUTH_%s' % tenant if self.admin_role in roles else '')
        env['swift.authorize'] = self.authorize_colony
        env['swift.clean_acl'] = clean_acl
        return self.app(env, start_response)


    def _get_claims(self, env):
        """Get claims from request"""
        claims = env.get('HTTP_X_AUTH_TOKEN', env.get('HTTP_X_STORAGE_TOKEN'))
        return claims

    def _reject_request(self, env, start_response):
        """Redirect client to auth server"""
        return HTTPUnauthorized("Authentication required",
                    [("WWW-Authenticate",
                      "Keystone uri='%s'" % self.auth_location)])(env,
                                                        start_response)

    def _decorate_request(self, index, value, env, proxy_headers):
        """Add headers to request"""
        proxy_headers[index] = value
        env["HTTP_%s" % index] = value


    def _validate_claims_each_user(self, auth_user):
        """ 
        add by colony.
        """
        tenant, user, password = auth_user
        auth_resp = self._authreq_to_keystone(user, password)
        if not auth_resp:
            return None
        auth_token, auth_tenant, username, roles, storage_url = self._get_swift_info(auth_resp, self.region_name) 
        if auth_tenant != tenant:
            return None
        if not storage_url:
            return None
        body = json.dumps({'storage': {'default': 'locals', 'locals': storage_url}})
        headers = {'X-Storage-Url': storage_url, 'X-Auth-Token': auth_token, 
                   'X-Storage-Token': auth_token, 'Content-Length': len(body)}
        return headers, body


    def _authreq_to_keystone(self, user, password):
        """ 
        add by colony.
        """
        auth_req = {'auth': {'passwordCredentials': {'username': user, 'password': password}}}
        req_headers = {"Content-type": "application/json", "Accept": "text/json"}
        connect = httplib.HTTPConnection if self.auth_protocol == 'http' else httplib.HTTPSConnection
        conn = connect('%s' % self.auth_netloc, timeout=10)
        conn.request('POST', '/v2.0/tokens', json.dumps(auth_req), req_headers)
        resp = conn.getresponse()
        #print resp.status
        if resp.status != 200:
            return None
        data = resp.read()
        return json.loads(data)

    def _get_auth_user(self, env):
        """
        add by colony
        """
        identity = env.get('HTTP_X_AUTH_USER', env.get('HTTP_X_STORAGE_USER'))
        password = env.get('HTTP_X_AUTH_KEY', env.get('HTTP_X_STORAGE_PASS'))
        if identity and password:
            identity_ls = identity.split(':')
            if len(identity_ls) == 2:
                tenant, user = identity_ls
                return (tenant, user, password)


    def _get_swift_info(self, auth_resp, region_name):
        """
        add by colony.
        """
        # memcache_client = cache_from_env(env)
        # if memcache_client:
        #     cached_auth_data = memcache_client.get(memcache_key)

        if not auth_resp.has_key('access'):
            return None
        auth_token = auth_resp['access']['token']['id']
        auth_tenant = auth_resp['access']['token']['tenant']['name']
        username = auth_resp['access']['user']['name']
        roles = []
        for role in auth_resp['access']['user']['roles']:
            roles.append(role['name'])
        storage_url = None
        for sca in auth_resp['access']['serviceCatalog']:
            if sca['type'] == 'object-store' and sca['name'] == 'swift':
                for reg in sca['endpoints']:
                    if reg['region'] == region_name:
                        storage_url = reg['publicURL']
        return auth_token, auth_tenant, username, roles, storage_url  


    def _accession_by_auth_token(self, env, auth_token):
        """
        add by colony.
        """
        req = Request(env)
        memcache_client = cache_from_env(env)

        #get memcache
        if memcache_client:
            memcache_key = 'auth/%s' % auth_token
            cached_auth_data = memcache_client.get(memcache_key)
            if cached_auth_data:
                expires, tenant, username, roles, storage_url = cached_auth_data
                if expires > time():
                    if not self.across_account and not self.valid_account_owner(req, tenant):
                        return None
                    return tenant, username, roles, storage_url

        token = {'auth': {'token': {'id': auth_token}, 'tenantId': ''}}
        req_headers = {'Content-type': 'application/json', 'Accept': 'text/json'}
        connect = httplib.HTTPConnection if self.auth_protocol == 'http' else httplib.HTTPSConnection
        conn = connect('%s' % self.auth_netloc, timeout=10)
        conn.request('POST', '/v2.0/tokens', json.dumps(token), req_headers)
        resp = conn.getresponse()
        if resp.status == 200:
            data = resp.read()
        else:
            return None
        auth_resp = json.loads(data)
        verified_auth_token, tenant, username, roles, storage_url = \
            self._get_swift_info(auth_resp, self.region_name) 
        if auth_token != verified_auth_token:
            return None

        # set memcache
        if memcache_client:
            memcache_client.set(memcache_key,
                                (time() + self.memcache_expire, 
                                 tenant, username, roles, storage_url),
                                timeout=self.memcache_expire)

        if not self.across_account and not self.valid_account_owner(req, tenant):
            return None
        return tenant, username, roles, storage_url


    def valid_account_owner(self, req, tenant):
        """
        add by colony.
        """
        parsed = urlparse(req.url)
        return '/'.join(parsed.path.split('/')[:3]) == '/v1.0/AUTH_%s' % tenant


    def authorize_colony(self, req):
        """ 
        add by colony.
         1. All user GET or HEAD account.
         2. All user create a container.
         3. All user read or write objects with no contaner acl.
         4. But any user are limited by container acl if exists.
        """
        try:
            version, account, container, obj = split_path(req.path, 1, 4, True)
        except ValueError:
            return HTTPNotFound(request=req)
        if not account:
            self.logger.info('no account')
            return self.denied_response(req)
        user_groups = (req.remote_user or '').split(',')
        self.logger.info('request_remote_user: %s' % req.remote_user)
        self.logger.info('request_method: %s' % req.method)
        # all user has normal authority, but 'swift_owner'.
        req.environ['swift_owner'] = True
        # Any user GET or HEAD account
        if req.method in ['HEAD', 'GET'] and not container:
            self.logger.info('HEAD or GET account all ok')
            return None
        # Any user creates container
        if req.method in ['PUT', 'POST', 'DELETE'] and container and not obj:
            self.logger.info('Any user create container')
            return None
        if hasattr(req, 'acl'):
            self.logger.info('container acl: %s' % req.acl)
            referrers, groups = parse_acl(req.acl)
            self.logger.info('referrers: %s' % referrers)
            self.logger.info('group: %s' % groups)
            if referrer_allowed(req.referer, referrers):
                if obj or '.rlistings' in groups:
                    self.logger.info('referer_allowed')
                    return None
                return self.denied_response(req)
            if not req.remote_user:
                return self.denied_response(req)
            for user_group in user_groups:
                if user_group in groups:
                    self.logger.info('group_allowed: %s' % user_group)
                    return None
            if not referrers and not groups:
                self.logger.info('no acl allow default access')
                return None
            self.logger.info('group not allowed.')
            return self.denied_response(req)
        self.logger.info('request forbidden')
        return self.denied_response(req)


    def authorize(self, req):
        """ 
        add by colony.
        stolen from swauth
        """
        try:
            version, account, container, obj = split_path(req.path, 1, 4, True)
        except ValueError:
            return HTTPNotFound(request=req)
        if not account:
            return self.denied_response(req)
        user_groups = (req.remote_user or '').split(',')
        # authority of admin.
        if account in user_groups and \
                (req.method not in ('DELETE', 'PUT') or container):
            req.environ['swift_owner'] = True
            return None
        # authority of normal.
        if hasattr(req, 'acl'):
            referrers, groups = parse_acl(req.acl)
            if referrer_allowed(req.referer, referrers):
                if obj or '.rlistings' in groups:
                    return None
                return self.denied_response(req)
            if not req.remote_user:
                return self.denied_response(req)
            for user_group in user_groups:
                if user_group in groups:
                    return None
        return self.denied_response(req)

    def denied_response(self, req):
        """
        Returns a standard WSGI response callable with the status of 403 or 401
        depending on whether the REMOTE_USER is set or not.
        """
        if req.remote_user:
            return HTTPForbidden(request=req)
        else:
            return HTTPUnauthorized(request=req)


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return AuthProtocol(app, conf)
    return auth_filter


def app_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)
    return AuthProtocol(None, conf)
