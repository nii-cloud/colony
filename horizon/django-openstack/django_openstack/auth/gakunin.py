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
from django.conf import settings

from django_openstack import api
from django_openstack import forms
from django_openstack.auth import util

from openstackx.api import exceptions as api_exceptions


LOG = logging.getLogger('django_openstack.auth.gakunin')


def _login_with_gakunin(request, from_email, from_eppn, region, show_error=False):

    try:
        token = None
        # first , try by eppn
        if from_eppn:
            try:
                token = api.token_create_by_eppn(request, from_eppn, region)
            except Exception, e:
                LOG.exception('error in token_create_by_eppn')
                pass
        # second, try by email
        if not token and from_email:
            try:
                token = api.token_create_by_email(request, from_email, region)
                if token:
                    api.user_update_eppn(request, token.user['id'], from_eppn, region)
            except Exception, e:
                LOG.exception('error in token_create_by_email')
                pass
 
        if not token:
            messages.error(request, "Can't retrieve information from Gakunin")
            return None

        util.set_region_info(request, token, region) 
 
        data = {}
        data['username'] = token.user['name']

        return util.auth_with_token(request, data, token.id, None, region, True)
    except Exception, e:
        if show_error:
            messages.error(request, 'Exception occured while gakunin login %s' % str(e))
        LOG.exception('exception')


def login(request):

    if request.user and request.user.is_authenticated():
        if request.session.get('tenant_id', None):
            return shortcuts.redirect('dash_containers', request.session['tenant_id'])
        elif getattr(request.user, "tenant_id", None):
            return shortcuts.redirect('dash_containers', request.user.tenant_id)
        else:
            return shortcuts.redirect('dash_startup')

    # check ssl
    if not request.is_secure():
        messages.error(request, "Gakunin Support needs to be accessed through TLS")
        return shortcuts.redirect('auth_login')
    from_email = request.META.get('mail', None)
    from_eppn = request.META.get('eppn', None)

    LOG.debug('headers from gakunin %s' % request.META)
    try:

        if getattr(settings, "KEYSTONE_USE_LOCAL_FOR_ENDPOINTS_ONLY", False):
            data = { 'username' : 'dummy' }
            token = util.auth_with_token(request, data, getattr(settings,
                          "KEYSTONE_ADMIN_TOKEN", ''), None, None, True)
        else:
            token = _login_with_gakunin(request, from_email, from_eppn, None, True)

        if not token:
            request.session.clear()
            return shortcuts.redirect('auth_login')

        util.set_default_service_catalog(request, token.serviceCatalog)

        regions = util.get_regions(request)
        default_region = getattr(settings, 'SWIFT_DEFAULT_REGION', None)
        tokens = []
        for region in regions:
            if region == default_region:
                retval = _login_with_gakunin(request, from_email, from_eppn, region, True)
                if retval:
                    request.session['region'] = region
            else:
                retval = _login_with_gakunin(request, from_email, from_eppn, region, True)
            if retval:
                tokens.append(region)

        if not tokens:
            request.session.clear()
            return shortcuts.redirect('auth_login')

        if not request.session.get('region', None):
            request.session['region'] = tokens[0]

        tenant = util.get_tenant_for_region(request)
        util.set_default_for_region(request)
        api.check_services_for_region(request)

        if not tenant:
            return shortcuts.redirect('dash_startup')
        else:
            return shortcuts.redirect('dash_containers', tenant)

    except Exception, e:
        messages.error(request, 'Exception occured while gakunin login %s' % str(e))
        LOG.exception('exception')
        return shortcuts.redirect('auth_login') 

