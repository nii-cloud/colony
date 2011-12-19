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
from webob.exc import HTTPUnauthorized, HTTPUseProxy, HTTPForbidden, HTTPUnauthorized
from webob import Request, Response
import keystone.tools.tracer  # @UnusedImport # module runs on import

from keystone.common.bufferedhttp import http_connect_raw as http_connect
from swift.common.middleware.acl import clean_acl, parse_acl, referrer_allowed
from swift.common.utils import cache_from_env, split_path, TRUE_VALUES

PROTOCOL_NAME = "Token Authentication"


class AuthProtocol(object):
    """Auth Middleware that handles authenticating client calls"""

    def _init_protocol_common(self, app, conf):
        """ Common initialization code"""
        print "Starting the %s component" % PROTOCOL_NAME

        self.conf = conf
        self.app = app
        #if app is set, then we are in a WSGI pipeline and requests get passed
        # on to app. If it is not set, this component should forward requests

        # where to find the OpenStack service (if not in local WSGI chain)
        # these settings are only used if this component is acting as a proxy
        # and the OpenSTack service is running remotely
        self.service_protocol = conf.get('service_protocol', 'https')
        self.service_host = conf.get('service_host')
        self.service_port = int(conf.get('service_port'))
        self.service_url = '%s://%s:%s' % (self.service_protocol,
                                           self.service_host,
                                           self.service_port)
        # used to verify this component with the OpenStack service or PAPIAuth
        self.service_pass = conf.get('service_pass')

        # delay_auth_decision means we still allow unauthenticated requests
        # through and we let the downstream service make the final decision
        self.delay_auth_decision = int(conf.get('delay_auth_decision', 0))

    def _init_protocol(self, conf):
        """ Protocol specific initialization """

        # where to find the auth service (we use this to validate tokens)
        self.auth_host = conf.get('auth_host')
        self.auth_port = int(conf.get('auth_port'))
        self.auth_protocol = conf.get('auth_protocol', 'https')

        # where to tell clients to find the auth service (default to url
        # constructed based on endpoint we have for the service to use)
        self.auth_location = conf.get('auth_uri',
                                        "%s://%s:%s" % (self.auth_protocol,
                                        self.auth_host,
                                        self.auth_port))

        # Credentials used to verify this component with the Auth service since
        # validating tokens is a privileged call
        self.admin_token = conf.get('admin_token')

    def __init__(self, app, conf):
        """ Common initialization code """

        #TODO(ziad): maybe we refactor this into a superclass
        #self._init_protocol_common(app, conf)  # Applies to all protocols
        #self._init_protocol(conf)  # Specific to this protocol

        # add by colony. conf tokens be simple.
        self.conf = conf
        self.app = app
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

        # s3 support. add by colony
        s3 = env.get('HTTP_AUTHORIZATION')
        if s3:
            result = self._s3_auth(env, claims)
        else:
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
            (tenant, username, tenant, \
                 'AUTH_%s' % tenant if self.admin_role in roles else '')
        env['swift.authorize'] = self.authorize
        env['swift.clean_acl'] = clean_acl
        return self.app(env, start_response)

        #Look for authentication claims
        # claims = self._get_claims(env)
        # if not claims:
        #     #No claim(s) provided
        #     if self.delay_auth_decision:
        #         #Configured to allow downstream service to make final decision.
        #         #So mark status as Invalid and forward the request downstream
        #         self._decorate_request("X_IDENTITY_STATUS",
        #             "Invalid", env, proxy_headers)
        #     else:
        #         #Respond to client as appropriate for this auth protocol
        #         return self._reject_request(env, start_response)
        # else:
        #     #this request is presenting claims. Let's validate them
        #     valid = self._validate_claims(claims)
        #     if not valid:
        #         # Keystone rejected claim
        #         if self.delay_auth_decision:
        #             # Downstream service will receive call still and decide
        #             self._decorate_request("X_IDENTITY_STATUS",
        #                 "Invalid", env, proxy_headers)
        #         else:
        #             #Respond to client as appropriate for this auth protocol
        #             return self._reject_claims(env, start_response)
        #     else:
        #         self._decorate_request("X_IDENTITY_STATUS",
        #             "Confirmed", env, proxy_headers)
        #     #Collect information about valid claims
        #     if valid:
        #         if not self._verify_auth_token(req, claims):
        #             return self._reject_request(env, start_response)
        #         claims = self._expound_claims(claims)

        #         # Store authentication data
        #         if claims:
        #             self._decorate_request('X_AUTHORIZATION', "Proxy %s" %
        #                 claims['user'], env, proxy_headers)
        #             self._decorate_request('X_TENANT',
        #                 claims['tenant'], env, proxy_headers)
        #             self._decorate_request('X_USER',
        #                 claims['user'], env, proxy_headers)
        #             if 'roles' in claims and len(claims['roles']) > 0:
        #                 if claims['roles'] != None:
        #                     roles = ''
        #                     for role in claims['roles']:
        #                         if len(roles) > 0:
        #                             roles += ','
        #                         roles += role
        #                     self._decorate_request('X_ROLE',
        #                         roles, env, proxy_headers)
        #             # NOTE(todd): unused
        #             self.expanded = True
        # #Send request downstream
        # return self._forward_request(env, start_response, proxy_headers)

    # NOTE(todd): unused
    def get_admin_auth_token(self, username, password):
        """
        This function gets an admin auth token to be used by this service to
        validate a user's token. Validate_token is a priviledged call so
        it needs to be authenticated by a service that is calling it
        """
        headers = {"Content-type": "application/json", "Accept": "text/json"}
        params = {"passwordCredentials": {"username": username,
                                          "password": password,
                                          "tenantId": "1"}}
        conn = httplib.HTTPConnection("%s:%s" \
            % (self.auth_host, self.auth_port))
        conn.request("POST", "/v2.0/tokens", json.dumps(params), \
            headers=headers)
        response = conn.getresponse()
        data = response.read()
        return data

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

    def _reject_claims(self, env, start_response):
        """Client sent bad claims"""
        return HTTPUnauthorized()(env,
            start_response)


    def _validate_claims(self, claims):
        """Validate claims, and provide identity information isf applicable """

        # Step 1: We need to auth with the keystone service, so get an
        # admin token
        #TODO(ziad): Need to properly implement this, where to store creds
        # for now using token from ini
        #auth = self.get_admin_auth_token("admin", "secrete", "1")
        #admin_token = json.loads(auth)["auth"]["token"]["id"]

        # Step 2: validate the user's token with the auth service
        # since this is a priviledged op,m we need to auth ourselves
        # by using an admin token
        headers = {"Content-type": "application/json",
                    "Accept": "text/json",
                    "X-Auth-Token": self.admin_token}
                    ##TODO(ziad):we need to figure out how to auth to keystone
                    #since validate_token is a priviledged call
                    #Khaled's version uses creds to get a token
                    # "X-Auth-Token": admin_token}
                    # we're using a test token from the ini file for now
        conn = http_connect(self.auth_host, self.auth_port, 'GET',
                            '/v2.0/tokens/%s' % claims, headers=headers)
        resp = conn.getresponse()
        # data = resp.read()
        conn.close()

        if not str(resp.status).startswith('20'):
            # Keystone rejected claim
            return False
        else:
            #TODO(Ziad): there is an optimization we can do here. We have just
            #received data from Keystone that we can use instead of making
            #another call in _expound_claims
            return True

    def _expound_claims(self, claims):
        # Valid token. Get user data and put it in to the call
        # so the downstream service can use it
        headers = {"Content-type": "application/json",
                    "Accept": "text/json",
                    "X-Auth-Token": self.admin_token}
                    ##TODO(ziad):we need to figure out how to auth to keystone
                    #since validate_token is a priviledged call
                    #Khaled's version uses creds to get a token
                    # "X-Auth-Token": admin_token}
                    # we're using a test token from the ini file for now
        conn = http_connect(self.auth_host, self.auth_port, 'GET',
                            '/v2.0/tokens/%s' % claims, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        if not str(resp.status).startswith('20'):
            raise LookupError('Unable to locate claims: %s' % resp.status)

        token_info = json.loads(data)
        #print token_info
        roles = []
        role_refs = token_info["access"]["user"]["roles"]
        if role_refs != None:
            for role_ref in role_refs:
                roles.append(role_ref["name"])

        try:
            tenant = token_info['access']['token']['tenant']['Id']
        except:
            tenant = None
        if not tenant:
            tenant = token_info['access']['user']['tenantName']
        verified_claims = {'user': token_info['access']['user']['username'],
                    'tenant': tenant,
                    'roles': roles}
        return verified_claims

    def _decorate_request(self, index, value, env, proxy_headers):
        """Add headers to request"""
        proxy_headers[index] = value
        env["HTTP_%s" % index] = value

    def _forward_request(self, env, start_response, proxy_headers):
        """Token/Auth processed & claims added to headers"""
        self._decorate_request('AUTHORIZATION',
            "Basic %s" % self.service_pass, env, proxy_headers)
        #now decide how to pass on the call
        if self.app:
            # Pass to downstream WSGI component
            return self.app(env, start_response)
            #.custom_start_response)
        else:
            # We are forwarding to a remote service (no downstream WSGI app)
            req = Request(proxy_headers)
            parsed = urlparse(req.url)

            conn = http_connect(self.service_host,
                                self.service_port,
                                req.method,
                                parsed.path,
                                proxy_headers,
                                ssl=(self.service_protocol == 'https'))
            resp = conn.getresponse()
            data = resp.read()

            #TODO(ziad): use a more sophisticated proxy
            # we are rewriting the headers now

            if resp.status == 401 or resp.status == 305:
                # Add our own headers to the list
                headers = [("WWW_AUTHENTICATE",
                   "Keystone uri='%s'" % self.auth_location)]
                return Response(status=resp.status, body=data,
                            headerlist=headers)(env,
                                                start_response)
            else:
                return Response(status=resp.status, body=data)(env,
                                                start_response)
    

    def _validate_claims_each_user(self, auth_user):
        """ 
        add by colony.
        """
        tenant, user, password = auth_user
        auth_resp = self._authreq_to_keystone(user, password)
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
        conn = connect('%s' % self.auth_netloc)
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
        conn = connect('%s' % self.auth_netloc)
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
            print 'no account'
            return self.denied_response(req)
        user_groups = (req.remote_user or '').split(',')
        print 'request_remote_user: %s' % req.remote_user
        print 'request_method: %s' % req.method
        # authority of admin.
        if account in user_groups and \
                (req.method not in ('DELETE', 'PUT') or container):
            print 'authorize full through' 
            req.environ['swift_owner'] = True
            return None
        # authority of normal.
        if hasattr(req, 'acl'):
            print 'container acl: %s' % req.acl 
            referrers, groups = parse_acl(req.acl)
            print 'referrers: %s' % referrers
            print 'group: %s' % groups
            if referrer_allowed(req.referer, referrers):
                if obj or '.rlistings' in groups:
                    print 'referer_allowed'
                    return None
                return self.denied_response(req)
            if not req.remote_user:
                return self.denied_response(req)
            for user_group in user_groups:
                if user_group in groups:
                    print 'group_allowed: %s' % user_group
                    return None
        print 'request forbidden'
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


    def _s3_auth(self, env, token):
        """
        add by colony

        AWS S3 API support. co-working with swift3.py.

        Authorization header is assumed,
         'AWS account:user:password:sign'
        like 'Authorization: AWS test:tester:testing:ZqDmuA7PLBtw6Qrl/nJWLyGX5Ck='

        in s3curl as:
        $ s3curl.pl --id test:tester:testing --key testing -- http://192.168.2.1:8080/TEST0

        """
        account = env['HTTP_AUTHORIZATION'].split(' ')[1]
        try:
            tenant, user, password, sign = account.split(':')
        except ValueError:
            return None
        msg = base64.urlsafe_b64decode(unquote(token))
        s = base64.encodestring(hmac.new(password, msg, sha1).digest()).strip()
        # print 'tenant: %s, user: %s, sign: %s' % (tenant, user, sign)
        # print 'msg: %s' % msg
        # print 'sign: %s' % sign
        # print 's: %s' % s
        if sign != s:
            return None
        auth_resp = self._authreq_to_keystone(user, password)
        auth_token, auth_tenant, username, roles, storage_url = self._get_swift_info(auth_resp, self.region_name) 
        if auth_tenant != tenant:
            return None
        if not storage_url:
            return None
        return tenant, username, roles, storage_url 


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

if __name__ == "__main__":
    app = loadapp("config:" + \
        os.path.join(os.path.abspath(os.path.dirname(__file__)),
                     os.pardir,
                     os.pardir,
                    "examples/paste/auth_token.ini"),
                    global_conf={"log_name": "auth_token.log"})
    wsgi.server(eventlet.listen(('', 8090)), app)
