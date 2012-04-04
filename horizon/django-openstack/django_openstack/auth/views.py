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

import logging

from django import template
from django import shortcuts
from django.contrib import messages

from django_openstack import api
from django_openstack import forms
from django_openstack.auth import util
from django.conf import settings

from openstackx.api import exceptions as api_exceptions


LOG = logging.getLogger('django_openstack.auth')


class Login(forms.SelfHandlingForm):
    username = forms.CharField(max_length="255", label="User Name")
    password = forms.CharField(max_length="255", label="Password",
                               widget=forms.PasswordInput(render_value=False))

    def handle(self, request, data):

        # retrieve endpoints
        if getattr(settings, "KEYSTONE_USE_LOCAL_FOR_ENDPOINTS_ONLY", False):
            token = util.auth_with_token(request, data, getattr(settings, "KEYSTONE_ADMIN_TOKEN", ''))
        else:
            token = util.auth(request, data, data.get('region'), True)

        if not token:
            request.session.clear()
            return shortcuts.redirect('auth_login')

        # set default service catalog
        util.set_default_service_catalog(request, token.serviceCatalog)

        # region
        results = util.get_regions(request)
        LOG.info('results %s' % results)
     
        tokens = [] 
        for result in results:
            data['region'] = result
            token = util.auth(request, data, result, True)
            if token:
                tokens.append(result)

        if not tokens:
            request.session.clear()
            return shortcuts.redirect('auth_login')

        default_region = getattr(settings, 'SWIFT_DEFAULT_REGION', None)
        if default_region and api.token_for_region(request, default_region):
            request.session['region'] = default_region

        if not request.session.get('region', None):
            request.session['region'] = tokens[0]

        tenant = util.get_tenant_for_region(request)
        util.set_default_for_region(request)
        api.check_services_for_region(request)

        if not tenant:
            return shortcuts.redirect('dash_startup')

        return shortcuts.redirect('dash_containers', tenant)


class LoginWithTenant(Login):
    username = forms.CharField(max_length="255",
                       widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    tenant = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        tenant = data['tenant']
        region = request.session.get('region', None)
        token = util.auth(request, data, region)
        if not token:
            return None
        if not tenant:
            return shortcuts.redirect('dash_startup')
        return shortcuts.redirect('dash_containers', tenant)

class LoginWithRegion(Login):
    username = forms.CharField(max_length="255",
                       widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    region = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        token = util.auth(request, data, data['region'])
        if not token:
            return None
        request.session['region'] = data['region']
        util.set_default_for_region(request)
        tenant = util.get_tenant_for_region(request)
        api.check_services_for_region(request)
        if not tenant:
            return shortcuts.redirect('dash_startup')
        return shortcuts.redirect('dash_containers', tenant)


def login(request):
    if request.user and request.user.is_authenticated():
        if getattr(request.user, 'tenant_id', None):
            return shortcuts.redirect('dash_containers', request.user.tenant_id)
        else:
            return shortcuts.redirect('dash_startup')

    form, handled = Login.maybe_handle(request)
    if handled:
        return handled

    return shortcuts.render_to_response('splash.html', {
        'form': form,
    }, context_instance=template.RequestContext(request))


def switch_regions(request, region_name):
    form, handled = LoginWithRegion.maybe_handle(
            request, initial={'region' : region_name,
                              'username' : request.user.username})

    token = api.token_for_region(request, region_name)
    LOG.debug('token %s' % token)
    if token:
        data = { 'username' : request.user.username,
                 'region' : region_name }
        retval =  util.auth_with_token(request, data, token, None, region_name, True)
        LOG.debug("retval %s" % retval)
        if retval:
            request.session['region'] = region_name
            util.set_default_for_region(request)
            api.check_services_for_region(request)
            tenant_id = request.session.get('tenant_id', None)
            if tenant_id:
                return shortcuts.redirect('dash_containers', tenant_id)
            else:
                return shortcuts.redirect('dash_startup')

    if handled:
        request.session['region'] = region_name
        return handled

    return shortcuts.render_to_response('switch_regions.html', {
        'to_region' : region_name,
        'form' : form,
    }, context_instance=template.RequestContext(request))

def switch_tenants(request, tenant_id):
    form, handled = LoginWithTenant.maybe_handle(
            request, initial={'tenant': tenant_id,
                              'username': request.user.username})
    token = api.token_for_region(request)
    LOG.debug('token %s' % token)
    if token:
        data = { 'username' : request.user.username,
                 'tenant_id' : tenant_id }
        retval =  util.auth_with_token(request, data, token, 
                                tenant_id, request.session.get('region', None), True)
        LOG.debug("retval %s" % retval)
        if retval:
            util.set_default_for_region(request)
            api.check_services_for_region(request)
            request.session['tenant_id'] = tenant_id
            return shortcuts.redirect('dash_containers', tenant_id)

    if handled:
        return handled

    return shortcuts.render_to_response('switch_tenants.html', {
        'to_tenant': tenant_id,
        'form': form,
    }, context_instance=template.RequestContext(request))


def logout(request):
    request.session.clear()
    return shortcuts.redirect('splash')
