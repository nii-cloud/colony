

import logging

from django import template
from django import shortcuts
from django.contrib import messages

from django_openstack import api

from openstackx.api import exceptions as api_exceptions

LOG = logging.getLogger('django_openstack.auth')

def get_regions(request):
    catalogs = request.session.get('defaultServiceCatalog')
    results = set()
    if catalogs:
        for catalog in catalogs:
            regions = [ catalog['endpoints'][i]['region'] for i in range(len(catalog['endpoints'])) ]
            for region in regions:
                results.add(region)
    return results

def get_tenant_for_region(request, region=None):

    try:
        if not region:
            region = request.session.get('region')
        return request.session['tenant_for_region'][region]['tenant_id']
    except:
        return None


def set_tenant_for_region(request, tenant, region):
    if region:
        if not request.session.has_key('tenant_for_region'):
            request.session['tenant_for_region'] = {}
        request.session['tenant_for_region'][region] = {}
        request.session['tenant_for_region'][region]['tenant_id'] = tenant.id
        request.session['tenant_for_region'][region]['tenant_name'] = tenant.name
        LOG.debug('tenant info %s' % request.session['tenant_for_region'])

def set_default_service_catalog(request, catalog):
    request.session['defaultServiceCatalog'] = catalog

def set_region_info(request, token, region=None, unscoped=False):
    if unscoped:
       request.session['unscoped_token'] = token.id
    else:
        if region:
            if not request.session.has_key('region_info'):
                request.session['region_info'] = {}
            request.session['region_info'][region] = {}
            request.session['region_info'][region]['token_id'] = token.id
            request.session['region_info'][region]['serviceCatalog'] = token.serviceCatalog
            request.session['region_info'][region]['user'] = token.user
            LOG.debug('region_info %s' % request.session['region_info'])
        else:
            request.session['token'] = token.id
    if not request.session.get('defaultServiceCatalog'):
        request.session['defaultServiceCatalog'] = token.serviceCatalog

def set_default_for_region(request, region=None):

    def is_admin(user):
        for role in user['roles']:
            if role['name'].lower() == 'admin':
                return True
        return False

    if not region:
        region = request.session.get('region')
    info = request.session['region_info'][region]

    request.session['token'] = info['token_id']
    request.session['serviceCatalog'] = info['serviceCatalog']
    LOG.debug('info %s' % info)
    request.session['admin'] = is_admin(info['user'])
    request.session['user'] = info['user']['name']

    try:
        tenant_info = request.session['tenant_for_region'][region]
        LOG.debug('tenant_info_info %s' % tenant_info)
 
        request.session['tenant'] = tenant_info['tenant_name']
        request.session['tenant_id'] = tenant_info['tenant_id']
    except KeyError, e:
        pass
    
 

def auth_with_token(request, data, token_id, tenant_id = None, region=None, show_error=False):
    try:
        try:
            tenants = api.tenant_list_for_token_and_region(request, token_id, region)
        except api.ServiceCatalogException, e:
            tenants = api.tenant_list_for_token(request, token_id)

        if tenant_id:
            for t in tenants:
                if t.id == tenant_id:
                    tenant = t
        else:
            tenant = tenants[0] if len(tenants) else None

        # Abort if there are no valid tenants for this user
        if not tenant:
            messages.error(request, 'No tenants present for user: %s' %
                                    data['username'])
            return
        # Create a token
        LOG.info('tokencreate')
        token = api.token_create_scoped_with_token_and_region(request,
                                 tenant.id,
                                 token_id,
                                 region)

        # set tanent info for region
        set_tenant_for_region(request, tenant, region)

        return token

    except api_exceptions.Unauthorized as e:
        msg = 'Error authenticating: %s' % e.message
        LOG.exception(msg)
        if show_error:
            messages.error(request, msg)
    except api_exceptions.ApiException as e:
        if show_error:
            messages.error(request, 'Error authenticating with keystone: %s' %
                                 e.message)
        LOG.exception('Error authenticating with keystone: %s for region %s' %
                                 (e.message, region))


def auth(request, data, region, show_error=False):

    try:

        region = data.get('region', '')
        tenant_id = data.get('tenant', '')

        token = api.token_create_with_region(request,
                                     tenant_id,
                                     data['username'],
                                     data['password'],
                                     region)
        set_region_info(request, token, region)

        return auth_with_token(request, data, token.id, tenant_id, region, show_error)

    except api_exceptions.Unauthorized as e:
        msg = 'Error authenticating: %s for region %s' % (e.message, region)
        LOG.exception(msg)
        if show_error:
            messages.error(request, msg)
    except api_exceptions.ApiException as e:
        if show_error:
            messages.error(request, 'Error authenticating with keystone: %s' %
                                 e.message)
        LOG.exception('Error authenticating with keystone: %s for region %s' %
                                 (e.message, region))

