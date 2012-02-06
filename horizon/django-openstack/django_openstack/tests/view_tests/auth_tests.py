# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2011 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django import http
from django.contrib import messages
from django.core.urlresolvers import reverse
from django_openstack import api
from django_openstack.tests.view_tests import base
from django_openstack import authext
from openstackx.api import exceptions as api_exceptions
from mox import IsA


class AuthViewTests(base.BaseViewTests):
    def setUp(self):
        super(AuthViewTests, self).setUp()
        self.setActiveUser()
        self.PASSWORD = 'secret'

    def test_login_index(self):
        res = self.client.get(reverse('auth_login'))
        self.assertTemplateUsed(res, 'splash.html')

    def test_login_user_logged_in(self):
        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT,
                           False, self.TEST_SERVICE_CATALOG)

        res = self.client.get(reverse('auth_login'))
        self.assertRedirectsNoFollow(res, reverse('dash_containers', args=[self.TEST_TENANT]))

    def test_login_admin_logged_in(self):
        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT,
                           True, self.TEST_SERVICE_CATALOG)

        res = self.client.get(reverse('auth_login'))
        self.assertRedirectsNoFollow(res, reverse('syspanel_overview'))

    def test_login_no_tenants(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1

        form_data = {'method': 'Login',
                    'password': self.PASSWORD,
                    'username': self.TEST_USER}

        self.mox.StubOutWithMock(api, 'token_create_with_region')
        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'fake'}]}
        aToken.serviceCatalog = {}
        api.token_create_with_region(IsA(http.HttpRequest), "", self.TEST_USER,
                         self.PASSWORD).AndReturn(aToken)

        aTenant = self.mox.CreateMock(api.Tenant)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([])

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(unicode))

        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_login'), form_data)

        self.assertTemplateUsed(res, 'splash.html')

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_gakunin_login(self):
        res = self.client.get(reverse('gakunin_login'))
        self.assertRedirectsNoFollow(res, reverse('auth_login'))

    def test_gakunin_login_https(self):
        key = {}
        key['wsgi.url_scheme'] =  'https'
        res = self.client.get(reverse('gakunin_login'),  **key )
        self.assertRedirectsNoFollow(res, reverse('auth_login'))

    def test_gakunin_login_with_no_tenants(self):
        TOKEN_ID = 1
        key = {}
        key['wsgi.url_scheme'] =  'https'
        key['email'] = 'test@test.com'

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'admin'}]}
        aToken.serviceCatalog = {}
        self.mox.StubOutWithMock(api, 'token_create_by_email')
        api.token_create_by_email(IsA(http.HttpRequest), 'test@test.com').AndReturn(aToken)
        

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([])

        self.mox.ReplayAll()
        res = self.client.get(reverse('gakunin_login'),  **key )
        self.assertRedirectsNoFollow(res, reverse('auth_login'))
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_gakunin_login_by_email_admin(self):
        TOKEN_ID = 1
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        key = {}
        key['wsgi.url_scheme'] =  'https'
        key['email'] = 'test@test.com'

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'admin'}]}
        aToken.serviceCatalog = {}
        self.mox.StubOutWithMock(api, 'token_create_by_email')
        api.token_create_by_email(IsA(http.HttpRequest), 'test@test.com').AndReturn(aToken)
        
        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([aTenant])

        self.mox.ReplayAll()
        res = self.client.get(reverse('gakunin_login'),  **key )
        self.assertRedirectsNoFollow(res, reverse('auth_login'))
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_gakunin_login_by_email_admin_with_session(self):
        TOKEN_ID = 1
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        key = {}
        key['wsgi.url_scheme'] =  'https'
        key['email'] = 'test@test.com'

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'admin'}]}
        aToken.serviceCatalog = {}
        self.mox.StubOutWithMock(api, 'token_create_by_email')
        api.token_create_by_email(IsA(http.HttpRequest), 'test@test.com').AndReturn(aToken)
        
        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([aTenant])

        self.mox.ReplayAll()
        res = self.client.get(reverse('gakunin_login'),  **key )
        self.assertRedirectsNoFollow(res, reverse('auth_login'))
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_login(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1

        form_data = {'method': 'Login',
                    'password': self.PASSWORD,
                    'username': self.TEST_USER}

    def test_gakunin_login_by_email(self):
        TOKEN_ID = 1
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        key = {}
        key['wsgi.url_scheme'] =  'https'
        key['email'] = 'test@test.com'

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'fake'}]}
        aToken.serviceCatalog = {}
        self.mox.StubOutWithMock(api, 'token_create_by_email')
        api.token_create_by_email(IsA(http.HttpRequest), 'test@test.com').AndReturn(aToken)
        
        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([aTenant])

        self.mox.ReplayAll()
        res = self.client.get(reverse('gakunin_login'),  **key )
        self.assertRedirectsNoFollow(res, reverse('auth_login'))
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_login(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1

        form_data = {'method': 'Login',
                    'password': self.PASSWORD,
                    'username': self.TEST_USER}

        self.mox.StubOutWithMock(api, 'token_create_with_region')
        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'fake'}]}
        aToken.serviceCatalog = {}
        api.token_create_with_region(IsA(http.HttpRequest), "", self.TEST_USER,
                         self.PASSWORD).AndReturn(aToken)

        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([aTenant])

        self.mox.StubOutWithMock(api, 'token_create_scoped_with_token_and_region')
        api.token_create_scoped_with_token_and_region(IsA(http.HttpRequest), aTenant.id,
                         aToken.id).AndReturn(aToken)


        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_login'), form_data)

        self.assertRedirectsNoFollow(res, reverse('dash_containers', args=[NEW_TENANT_ID]))

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_login_invalid_credentials(self):
        form_data = {'method': 'Login',
                    'password': self.PASSWORD,
                    'username': self.TEST_USER}

        self.mox.StubOutWithMock(api, 'token_create_with_region')
        unauthorized = api_exceptions.Unauthorized('unauth', message='unauth')
        api.token_create_with_region(IsA(http.HttpRequest), "", self.TEST_USER,
                         self.PASSWORD).AndRaise(unauthorized)

        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_login'), form_data)

        self.assertTemplateUsed(res, 'splash.html')

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_login_exception(self):
        form_data = {'method': 'Login',
                    'password': self.PASSWORD,
                    'username': self.TEST_USER}

        self.mox.StubOutWithMock(api, 'token_create_with_region')
        api_exception = api_exceptions.ApiException('apiException',
                                                    message='apiException')
        api.token_create_with_region(IsA(http.HttpRequest), "", self.TEST_USER,
                         self.PASSWORD).AndRaise(api_exception)

        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_login'), form_data)

        self.assertTemplateUsed(res, 'splash.html')

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_switch_regions(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1
        REGION_NAME = 'region1'
        form_data = {'method': 'LoginWithRegion',
                     'password': self.PASSWORD,
                     'username': self.TEST_USER,
                     'region' : REGION_NAME}

        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT,
                           False, self.TEST_SERVICE_CATALOG)
        self.mox.StubOutWithMock(api, 'token_create_with_region')
        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'fake'}]}
        aToken.serviceCatalog = {}

        api.token_create_with_region(IsA(http.HttpRequest), NEW_TENANT_ID, self.TEST_USER,
                         self.PASSWORD).AndReturn(aToken)

        #self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        #api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
        #                          AndReturn([aTenant])


        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_region_switch', args=['testRegion']),
                               form_data)

        #self.assertRedirectsNoFollow(res, reverse('dash_containers', args=[NEW_TENANT_ID]))
        self.assertTemplateUsed(res, 'switch_regions.html')
        #self.assertEqual(self.client.session['tenant'], NEW_TENANT_NAME)

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_switch_regions_admin(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1
        REGION_NAME = 'region1'
        form_data = {'method': 'LoginWithRegion',
                     'password': self.PASSWORD,
                     'tenant': NEW_TENANT_ID,
                     'username': self.TEST_USER,
                     'region' : REGION_NAME}

        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT,
                           False, self.TEST_SERVICE_CATALOG)
        self.mox.StubOutWithMock(api, 'token_create_with_region')
        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'admin'}]}
        aToken.serviceCatalog = {}

        api.token_create_with_region(IsA(http.HttpRequest), NEW_TENANT_ID, self.TEST_USER,
                         self.PASSWORD).AndReturn(aToken)

        #self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        #api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
        #                          AndReturn([aTenant])


        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_region_switch', args=['testRegion']),
                               form_data)

        #self.assertRedirectsNoFollow(res, reverse('dash_containers', args=[NEW_TENANT_ID]))
        self.assertTemplateUsed(res, 'switch_regions.html')
        #self.assertEqual(self.client.session['tenant'], NEW_TENANT_NAME)

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_switch_tenants_index(self):
        res = self.client.get(reverse('auth_switch', args=[self.TEST_TENANT]))

        self.assertTemplateUsed(res, 'switch_tenants.html')

    def test_switch_tenants(self):
        NEW_TENANT_ID = '6'
        NEW_TENANT_NAME = 'FAKENAME'
        TOKEN_ID = 1

        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT,
                           False, self.TEST_SERVICE_CATALOG)

        form_data = {'method': 'LoginWithTenant',
                     'password': self.PASSWORD,
                     'tenant': NEW_TENANT_ID,
                     'username': self.TEST_USER}

        self.mox.StubOutWithMock(api, 'token_create_with_region')
        #self.mox.StubOutWithMock(api, 'token_create')

        aTenant = self.mox.CreateMock(api.Token)
        aTenant.id = NEW_TENANT_ID
        aTenant.name = NEW_TENANT_NAME

        aToken = self.mox.CreateMock(api.Token)
        aToken.id = TOKEN_ID
        aToken.user = { 'roles': [{'name': 'fake'}]}
        aToken.serviceCatalog = {}

        api.token_create_with_region(IsA(http.HttpRequest), NEW_TENANT_ID, self.TEST_USER,
                         self.PASSWORD).AndReturn(aToken)

        self.mox.StubOutWithMock(api, 'tenant_list_for_token')
        api.tenant_list_for_token(IsA(http.HttpRequest), aToken.id).\
                                  AndReturn([aTenant])


        self.mox.ReplayAll()

        res = self.client.post(reverse('auth_switch', args=[NEW_TENANT_ID]),
                               form_data)

        self.assertRedirectsNoFollow(res, reverse('dash_containers', args=[NEW_TENANT_ID]))
        self.assertEqual(self.client.session['tenant'], NEW_TENANT_NAME)

        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_logout(self):
        KEY = 'arbitraryKeyString'
        VALUE = 'arbitraryKeyValue'
        self.assertNotIn(KEY, self.client.session)
        self.client.session[KEY] = VALUE

        res = self.client.get(reverse('auth_logout'))

        self.assertRedirectsNoFollow(res, reverse('splash'))
        self.assertNotIn(KEY, self.client.session)
