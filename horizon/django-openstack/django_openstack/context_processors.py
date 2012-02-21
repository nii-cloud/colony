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

from django.conf import settings
from django_openstack import api
from django.contrib import messages
from openstackx.api import exceptions as api_exceptions


def tenants(request):
    if not request.user or not request.user.is_authenticated():
        return {}

    try:
        try:
            tenants = api.tenant_list_for_token_and_region(request, 
                       api.token_for_region(request),
                       request.session.get('region', None))
        except api.ServiceCatalogException, e:
            tenants = api.tenant_list_for_token(request, request.user.token)
        return {'tenants': tenants }
    except api_exceptions.BadRequest, e:
        messages.error(request, "Unable to retrieve tenant list from\
                                  keystone: %s" % e.message)
        return {'tenants': []}

def regions(request):
    if not request.user or not request.user.is_authenticated():
        return {}
    try:
        catalogs = request.session['defaultServiceCatalog']
        results = []
        for catalog in catalogs:
            regions = [ api.Region(id=i+1, name=catalog['endpoints'][i]['region']) for i in range(len(catalog['endpoints'])) ]
            for region in regions:
                dupl = False
                for result in results:
                    if result.name == region.name:
                        dupl = True
                        break
                if not dupl:
                    results.append(region)
        return {'regions' : results}
    except KeyError:
        return {'regions' : []}

def compute(request):
    return {'compute_configured' : settings.OPENSTACK_COMPUTE_ENABLED}

def swift(request):
    return {'swift_configured': settings.SWIFT_ENABLED}

def quantum(request):
    return {'quantum_configured': settings.QUANTUM_ENABLED}

def image_metadata_glance(request):
    return {'image_metadata_glance' : settings.IMAGE_METADATA_GLANCE_ENABLED}

def gakunin(request):
    return {'gakunin_configured' : settings.GAKUNIN_ENABLED }

def gakunin_url(request):
    return {'gakunin_login_url' : getattr(settings, 'GAKUNIN_LOGIN_URL', '/auth/gakunin') }

def swift_enable_access_to_other_account(request):
    return {'swift_enable_other_account' : settings.SWIFT_ACCESS_OTHER_ACCOUNT_ENABLED }

