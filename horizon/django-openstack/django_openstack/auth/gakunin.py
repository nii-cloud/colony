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


def _login_with_gakunin(request, from_email, from_eppn, region, session_override=False):

    try:
        token = None
        # first , try by eppn
        if from_eppn:
            try:
                token = api.token_create_by_eppn(request, from_eppn)
            except Exception, e:
                LOG.exception('error in token_create_by_eppn')
                pass
        # second, try by email
        if not token and from_email:
            try:
                token = api.token_create_by_email(request, from_email)
                if token:
                    api.user_update_eppn(request, token.user['id'], from_eppn)
            except Exception, e:
                LOG.exception('error in token_create_by_email')
                pass
 
        def get_first_tenant_for_user():
            tenants = api.tenant_list_for_token(request, token.id)
            return tenants[0] if len(tenants) else None
 
        if not token:
            messages.error(request, "Can't retrieve information from Gakunin")
            return shortcuts.redirect('auth_login')

        util.set_token_for_region(request, token, region) 
        tenant = get_first_tenant_for_user()
 
        if not tenant:
            messages.error(request, 'No tenants present for user')
            return shortcuts.redirect('auth_login')

        data = {}
        data['username'] = token.user['name']

        util.auth_with_token(request, data, token.id, tenant.id, session_override, True)
        return shortcuts.redirect('dash_containers', tenant.id)
    except Exception, e:
        messages.error(request, 'Exception occured while gakunin login %s' % str(e))
        LOG.exception('exception')


def login(request):

    if request.user and request.user.is_authenticated():
        return shortcuts.redirect('dash_containers', request.user.tenant_id)

    # check ssl
    if not request.is_secure():
        messages.error(request, "Gakunin Support needs to be accessed through TLS")
        return shortcuts.redirect('auth_login')
    from_email = request.META.get('email', None)
    from_eppn = request.META.get('eppn', None)

    try:

        retval = _login_with_gakunin(request, from_email, from_eppn, None, True)
        regions = util.get_regions(request)

        default_region = getattr(settings, 'SWIFT_DEFAULT_REGION', None)
        for region in regions:
            if region == default_region:
                retval = _login_with_gakunin(request, from_email, from_eppn, region, True)
                request.session['region'] = region
            else:
                _login_with_gakunin(request, from_email, from_eppn, region, False)

        return retval
    except Exception, e:
        messages.error(request, 'Exception occured while gakunin login %s' % str(e))
        LOG.exception('exception')
        return shortcuts.redirect('auth_login') 

