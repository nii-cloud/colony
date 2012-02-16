

import logging

from django import template
from django import shortcuts
from django.contrib import messages

from django_openstack import api

from openstackx.api import exceptions as api_exceptions

LOG = logging.getLogger('django_openstack.auth')


def set_token_for_region(request, token, region=None, unscoped=False):
    if unscoped:
       request.session['unscoped_token'] = token.id
    else:
        if region:
            if not request.session.has_key('token_for_region'):
                request.session['token_for_region'] = {}
            request.session['token_for_region'][region] = token.id
        else:
            request.session['token'] = token.id
    if not request.session.get('defaultServiceCatalog'):
        request.session['defaultServiceCatalog'] = token.serviceCatalog


def auth_with_token(request, data, token_id, tenant_id = None,  region=None, session_override=True):
    def is_admin(token):
        for role in token.user['roles']:
            if role['name'].lower() == 'admin':
                return True
        return False
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

        if session_override:
            request.session['admin'] = is_admin(token)
            request.session['serviceCatalog'] = token.serviceCatalog
            #request.session['admin'] = True
            #request.session['serviceCatalog'] = {}

            LOG.info('Login form for user "%s". Service Catalog data:\n%s' %
                 (data['username'], token.serviceCatalog))

            request.session['tenant'] = tenant.name
            request.session['tenant_id'] = tenant.id
            request.session['user'] = data['username']

        return shortcuts.redirect('dash_containers', tenant.id)

    except api_exceptions.Unauthorized as e:
        msg = 'Error authenticating: %s' % e.message
        LOG.exception(msg)
        if session_override:
            messages.error(request, msg)
    except api_exceptions.ApiException as e:
        if session_override:
            messages.error(request, 'H Error authenticating with keystone: %s' %
                                 e.message)


def auth(request, data, region, session_override=True):

    try:

        region = data.get('region', '')
        tenant_id = data.get('tenant', '')

        token = api.token_create_with_region(request,
                                     tenant_id,
                                     data['username'],
                                     data['password'],
                                     region)
        set_token_for_region(request, token, region)

        return auth_with_token(request, data, token.id, tenant_id, region, session_override)

    except api_exceptions.Unauthorized as e:
        msg = 'Error authenticating: %s' % e.message
        LOG.exception(msg)
        if session_override:
            messages.error(request, msg)
    except api_exceptions.ApiException as e:
        if session_override:
            messages.error(request, 'Error authenticating with keystone: %s' %
                                 e.message)

