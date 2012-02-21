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

        retval = util.auth(request, data, data.get('region'))
        results = util.get_regions(request)

        LOG.info('results %s' % results)
      
        for result in results:
            data['region'] = result
            util.auth(request, data, result, False)
            if api.token_for_region(request, result) == request.session.get('token'):
                request.session['region'] = result.encode('utf-8')

        default_region = getattr(settings, 'SWIFT_DEFAULT_REGION', None)
        if default_region and api.token_for_region(request, default_region):
            request.session['region'] = default_region

        return retval


class LoginWithTenant(Login):
    username = forms.CharField(max_length="255",
                       widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    tenant = forms.CharField(widget=forms.HiddenInput())

class LoginWithRegion(Login):
    username = forms.CharField(max_length="255",
                       widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    region = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        return super(LoginWithRegion, self).handle(request, data)


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

    tokens = request.session.get('token_for_region', {})
    if tokens.has_key(region_name):
        data = { 'username' : request.user.username,
                 'region' : region_name }
        retval =  util.auth_with_token(request, data, tokens.get(region_name), None, region_name, True)
        if retval:
            request.session['region'] = region_name
            return retval

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
    if handled:
        return handled

    return shortcuts.render_to_response('switch_tenants.html', {
        'to_tenant': tenant_id,
        'form': form,
    }, context_instance=template.RequestContext(request))


def logout(request):
    request.session.clear()
    return shortcuts.redirect('splash')
