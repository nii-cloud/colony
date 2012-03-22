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

"""
Views for managing Swift containers.
"""
import logging

from urllib import unquote
from urlparse import urlparse
from django import template
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import shortcuts
from django.core import validators
from django.views.decorators.cache import cache_control

from django_openstack import api
from django_openstack import forms
from django_openstack.acl import parse_acl, clean_acl

from cloudfiles.errors import ContainerNotEmpty, InvalidContainerName, ResponseError, NoSuchContainer


LOG = logging.getLogger('django_openstack.dash')

class DeleteContainer(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        try:
            api.swift_delete_container(request, data['container_name'])
        except ContainerNotEmpty, e:
            messages.error(request,
                           'Unable to delete non-empty container: %s' % \
                           data['container_name'])
            LOG.exception('Unable to delete container "%s".  Exception: "%s"' %
                      (data['container_name'], str(e)))
        except ResponseError, e:
            messages.error(request, 'Unable to delete container. \
                       Perhaps you do not have right permission : %s'  % str(e))
        except NoSuchContainer, e:
            messages.error(request, 'Unable to delete container. : %s' % str(e))
        else:
            messages.info(request,
                      'Successfully deleted container: %s' % \
                      data['container_name'])
        return shortcuts.redirect(request.build_absolute_uri())

class OtherContainer(forms.SelfHandlingForm):
    storage_url = forms.CharField(widget=forms.HiddenInput(), required=False)
    storage_urls = forms.ChoiceField(initial=1, widget=forms.Select, required=False)

    def __init__(self, *args, **kwargs):
        fields = kwargs.pop('storage_urls')
        storage_url = kwargs.pop('storage_url')
        super(OtherContainer, self).__init__(*args, **kwargs)
        self.fields['storage_urls'].choices = [ (value, value) for value in fields ]
        if storage_url:
            self.fields['storage_urls'].initial = (storage_url, storage_url)

    def handle(self, request, data):
        storage_url = data['storage_url']
        storage_urls = data['storage_urls']
        if storage_url:
            target_url = storage_url
        elif storage_urls:
            target_url = storage_urls
        containers = []
        try:
            containers = api.swift_get_containers(request, target_url)
            request.session['storage_url'] = target_url
            if not request.session.get('storage_url_list', None):
                request.session['storage_url_list'] =  set()
            request.session['storage_url_list'].add(target_url)
        except Exception, e:
            msg = "Unable to retrieve containers from swift: %s" % str(e)
            LOG.exception(msg)
            messages.error(request, msg)
            return shortcuts.redirect('dash_containers' , request.user.tenant_id)
 
        return shortcuts.render_to_response(
        'django_openstack/dash/containers/index.html', {
            'containers': containers,
            'storage_url_form' : self,
            'storage_url' : storage_url
        }, context_instance=template.RequestContext(request))

class CreateContainer(forms.SelfHandlingForm):
    name = forms.CharField(max_length="255", label="Container Name",
           validators=[validators.MaxLengthValidator(255)])

    def handle(self, request, data):
        cont_name = data['name']
        cont_name = cont_name.encode('utf-8')
        cont_name = cont_name.replace('/', '%2F')
        try:
            api.swift_create_container(request, cont_name)
            messages.success(request, "Container was successfully created.")
        except InvalidContainerName as e:
            messages.error(request, "Invalid Container Name %s" % str(e))
        except Exception, e:
            messages.error(request, 'Unable to create container. \
                       Perhaps you do not have right permission : %s'  % str(e))
        return shortcuts.redirect("dash_containers", request.user.tenant_id)

class ContainerMetaRemove(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ContainerMetaRemove, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        container_name = data['container_name']

        if not header.lower().startswith('x-container-meta'):
            messages.error(request, "Container metadata must begin with x-container-meta-")
        else:
            hdrs = {}
            hdrs[header] = ''
            try:
                api.swift_set_container_info(request, container_name, hdrs)
            except ResponseError, e:
                messages.error(request, 'Unable to remove metadata from container : %s' % str(e))

        return None

class ContainerMeta(forms.SelfHandlingForm):
    ''' Form that handles Swift Container Meta Data '''
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(max_length="128", label='Name', required=True,
                  validators=[validators.MaxLengthValidator(128)])
    header_value = forms.CharField(max_length="256", label="Value", required=True,
                  validators=[validators.MaxLengthValidator(256)])
    
    def __init__(self, *args, **kwargs):
        super(ContainerMeta, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        value = data['header_value']
        container_name = data['container_name']

        try:
           header.encode('ascii')
           value.encode('ascii')
        except UnicodeEncodeError, e:
           messages.error(request, "Container metadata contains non-ASCII character %s" % str(e))
           return shortcuts.redirect(request.build_absolute_uri())

        if not header.lower().startswith('x-container-meta'):
            messages.error(request, "Container metadata must begin with x-container-meta-")
            return shortcuts.redirect(request.build_absolute_uri())

        hdrs = {}
        hdrs[header] = value

        try:
            api.swift_set_container_info(request, container_name, hdrs)
        except Exception, e:
            messages.error(request, 'Unable to setting Container Meta Information is failed: %s' % str(e))

        return None

class ContainerAclRemove(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(widget=forms.HiddenInput())
    acl_type = forms.CharField(widget=forms.HiddenInput())
    acl_value = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ContainerAclRemove, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        container_name = data['container_name']
        acl_type = data['acl_type']
        acl_value = data['acl_value']

        if acl_type == "read":
            type = 'X-Container-Read'
        elif acl_type == "write":
            type = 'X-Container-Write'
        else:
            pass
        # clean and parse acl
        try:
            acl = clean_acl(type, acl_value)
            refs, groups = parse_acl(acl)
        except ValueError, e:
            messages.error(request, 'ACL value is invalid %s' % str(e))
            return None

        if header in groups:
            groups.remove(header)
        if header in refs:
            refs.remove(header)

        # re-calcurate referer string
        refs = map( lambda x: '.r:%s' % x.encode('utf-8'), refs)
        LOG.debug('ref  %s' % refs)

        tenant_name = request.user.tenant_name
        tenant_user_name = '%s:%s' % (request.user.tenant_name, request.user.username)
        LOG.debug('acl_type %s' % acl_type)
        # check ACL
        val = []
        for each_acl in groups:
            if each_acl == tenant_name or each_acl == tenant_user_name:
                val.append(True)
            else:
                val.append(False)
        if not True in val and len(val) > 0:
            messages.error(request, 'Removing Your ACL from this Container is not allowed unless other ACLs are deleted')
            return
            
        #messages.error(request, refs)
        # set header
        hdrs = {}
        hdrs[type] = ','.join(groups + refs)

        LOG.debug('delete acl %s' % hdrs)
        try:
            api.swift_set_container_info(request, container_name, hdrs)
        except Exception, e:
            # TODO error message
            messages.error(request, 'Removing Container Meta Information is failed: %s' % str(e))

        return None

class ContainerAcl(forms.SelfHandlingForm):
    ''' Form that handles Swift Container Acl '''
    container_name = forms.CharField(widget=forms.HiddenInput())
    acl_type = forms.ChoiceField(label="ACL Type", choices=((1, 'ReadAcl'),(0,'WriteAcl')), initial=1, widget=forms.RadioSelect)
    read_acl = forms.CharField(widget=forms.HiddenInput(), required=False)
    write_acl = forms.CharField(widget=forms.HiddenInput(), required=False)
    acl_add = forms.CharField(max_length="255", label="ACL", required=True)

    def __init__(self, *args, **kwargs):
        super(ContainerAcl, self).__init__(*args, **kwargs)

    def handle(self, request, data):

        container_name = data['container_name']
        acl_type = data['acl_type']
        try:
            acl_add = data['acl_add']
            acl_add.encode('ascii')
        except UnicodeEncodeError, e:
            messages.error(request, "Container ACL contains non-ASCII \
            character %s" % str(e))
            return shortcuts.redirect(request.build_absolute_uri()) 

        if acl_type == "1":
           type = 'X-Container-Read'
           acl_value = data.get('read_acl', '')
        elif acl_type == "0":
           type = 'X-Container-Write'
           acl_value = data.get('write_acl', '')


        # clean and parse acl
        try:
            acl = clean_acl(type, acl_add)
            acl_orig = clean_acl(type, acl_value)
            ref_add, group_add = parse_acl(acl)
            ref_orig, group_orig = parse_acl(acl_orig)
        except ValueError, e:
            messages.error(request, 'ACL value is invalid %s' % str(e))
            return None

        # duplicate check
        ref_add = list(set(ref_add))
        ref_orig = list(set(ref_orig))
        group_add = list(set(group_add))
        group_orig = list(set(group_orig))

        acl_result = []
        acl_ref_result = []

        for item in group_add:
            if not item in group_orig:
                acl_result.append(item)
        for item in ref_add:
            if not item in ref_orig:
                acl_ref_result.append(item)

        group_result = group_orig + acl_result
        ref_result = acl_ref_result + ref_orig
        # re-calcurate referer string
        ref_result = map( lambda x: '.r:%s' % x, ref_result)

        tenant_name = request.user.tenant_name
        tenant_user_name = '%s:%s' % (request.user.tenant_name, request.user.username)
        LOG.debug('acl_type %s' % acl_type)
        # check ACL
        val = []
        for each_acl in group_result:
            if each_acl == tenant_name or each_acl == tenant_user_name:
                val.append(True)
            else:
                val.append(False)
        LOG.debug('val %s' % val)
        if not True in val:
             messages.error(request, 'Adding ReadAcl or WriteACL for other account is not \
             allowed unless Your Acl is allowed. Please add your Acl \
             first (ex %s ' % request.user.tenant_name)
             return None

        # set header
        hdrs = {}
        hdrs[type] = ','.join(group_result + ref_result)

        LOG.debug("sending ACL %s" % hdrs)
        try:
            api.swift_set_container_info(request, container_name, hdrs)
        except Exception, e:
            messages.error(request, 'Unable to set container acl : %s' % str(e))


        return None       


class MakePublicContainer(forms.SelfHandlingForm):
    index_object_name = forms.ChoiceField(label="Object used for index.html")
    css_object_name = forms.ChoiceField(label="Object used as a css file for listing Container")
    error = forms.CharField(max_length="255", label="file suffix to be used when error occurs", required=False )
    public_html = forms.BooleanField(label="Published as HTML", required=False)
    use_css_in_listing = forms.BooleanField(label="Use CSS file for listing Container", required=False)
    html_listing = forms.BooleanField(label="Enable Container listing", required=False )
    container_name = forms.CharField(widget=forms.HiddenInput())
    

    def __init__(self, *args, **kwargs):
        objects = kwargs.pop('objects')
        headers = kwargs.pop('headers')
        super(MakePublicContainer, self).__init__(*args, **kwargs)
        self.fields['index_object_name'].choices = objects
        self.fields['css_object_name'].choices = objects

        for name, value in headers:
            name = name.lower()
            if name == 'x-container-meta-web-index':
                self.fields['public_html'].initial = True
                self.fields['index_object_name'].initial = ( value, value)
            if name == 'x-container-meta-web-listings':
                self.fields['html_listing'].initial = value == 'true'
            if name == 'x-container-meta-web-listings-css':
                self.fields['use_css_in_listing'].initial = True
                self.fields['css_object_name'].initial = ( value, value )
            if name == 'x-container-meta-web-error':
                self.fields['error'].value = value

    def handle(self, request, data):
        hdrs = {}
        index_object_name = data['index_object_name']
        css_object_name = data['css_object_name']
        public_html = data['public_html']
        error = data['error']
        try:
            error = error.encode('ascii')
        except Exception, e:
            messages.error(request, 'Container Public contains non-ASCII character %s' % str(e))
            return
        html_listing = data['html_listing']
        use_css_in_listing = data['use_css_in_listing']
        container_name = data['container_name']
        for name in ['Index', 'Listings', 'Listings-Css', 'Error']:
           hdrs['X-Container-Meta-Web-' + name] = ''
        if public_html:
           hdrs['X-Container-Meta-Web-Index'] = index_object_name
        if html_listing:
           hdrs['X-Container-Meta-Web-Listings'] = 'true'
        if use_css_in_listing:
           hdrs['X-Container-Meta-Web-Listings-Css'] = css_object_name
        if error:
           hdrs['X-Container-Meta-Web-Error'] = error

        try:
            api.swift_set_container_info(request, container_name, hdrs)
        except Exception, e:
            messages.error(request, 'Unable to set container metadata for public : %s' % str(e))
            return

        messages.success(request, 'Successfully updated container metadata for public')

def _index(request, tenant_id, expire_session):

    delete_form, handled = DeleteContainer.maybe_handle(request)
    if handled:
        return handled

    if expire_session and request.session.has_key('storage_url'):
       print 'removing session'
       del request.session['storage_url']
    storage_urls = request.session.get('storage_url_list', [])
    storage_url = request.session.get('storage_url', None)
    storage_url_form, handled = OtherContainer.maybe_handle(request,
                  storage_urls=storage_urls, storage_url=storage_url)
    if handled:
        return handled


    containers = []
    try:
        containers = api.swift_get_containers(request, storage_url)
    except Exception, e:
        msg = "Unable to retrieve containers from swift: %s" % str(e)
        LOG.exception(msg)
        messages.error(request, msg)

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/index.html', {
        'containers': containers,
        'delete_form': delete_form,
        'storage_url_form' : storage_url_form,
        'storage_url' : storage_url
    }, context_instance=template.RequestContext(request))


@cache_control(must_revalidate=True, max_age=0, no_cache=True)
@login_required
def index_storage_url(request, tenant_id):
    return _index(request, tenant_id, False)

@cache_control(must_revalidate=True, max_age=0, no_cache=True)
@login_required
def index(request, tenant_id):
    return _index(request, tenant_id, True)

@login_required
def create(request, tenant_id):
    form, handled = CreateContainer.maybe_handle(request)
    if handled:
        return handled

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/create.html', {
        'create_form': form,
    }, context_instance=template.RequestContext(request))

@login_required
def public(request, tenant_id, container_name):


    try:
        container = api.swift_get_container(request, container_name)
        objects = [(o.name, o.name) for o in api.swift_get_objects(request, container_name)]
    except ResponseError, e:
        messages.error(request, 'Unable to retrive container meta data for public. \
                       Perhaps you do not have right permission : %s'  % str(e))
        return shortcuts.redirect('dash_containers', tenant_id)

    form, handled = MakePublicContainer.maybe_handle(request, objects=objects, headers=container.headers)
    if handled:
        return handled

    #if len(objects) > 0:
    #   form.fields['index_object_name'].initial = objects[0]
    #   form.fields['css_object_name'].initial = objects[0]

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/public.html', {
        'container_name' : container_name,
        'container': container,
        'objects' : objects,
        'public_form' : form
    }, context_instance=template.RequestContext(request))

@login_required
def meta(request, tenant_id, container_name):
    form, handled = ContainerMeta.maybe_handle(request)
    if handled:
        return handled

    remove_form, handled = ContainerMetaRemove.maybe_handle(request)
    if handled:
        return handled

    try:
        container = api.swift_get_container(request, container_name)
        headers = []
        for h, v in container.headers:
            if h.startswith('x-container-meta'):
                headers.append((h,v))
    except ResponseError, e:
        messages.error(request, 'Unable to retrive container meta data. \
                       Perhaps you do not have right permission : %s'  % str(e))
        return shortcuts.redirect('dash_containers', tenant_id)

    container_name_unquoted = unquote(container_name)
    return shortcuts.render_to_response(
    'django_openstack/dash/containers/meta.html', {
       'container_name' : container_name,
       'container_name_unquoted' : container_name_unquoted,
       'headers' : headers,
       'meta_form' : form,
       'remove_form' : remove_form
    }, context_instance=template.RequestContext(request))


@login_required
def acl(request, tenant_id, container_name):

    form, handled = ContainerAcl.maybe_handle(request)
    if handled:
        return handled

    remove_form, handled = ContainerAclRemove.maybe_handle(request)
    if handled:
        return handled
   
    try: 
        container = api.swift_get_container(request, container_name)
    except ResponseError, e:
        messages.error(request, 'Unable to retrive ACL data. \
                       Perhaps you do not have right permission : %s'  % str(e))
        return shortcuts.redirect('dash_containers', tenant_id)
    read_ref, read_groups, write_ref, write_groups = [],[],[],[]
    read_acl, write_acl = '', ''
    for h,v in container.headers:
        if 'x-container-read' == h.lower():
            v = clean_acl('X-Container-Read', v)
            read_ref, read_groups = parse_acl(v)
            read_acl = v
        if 'x-container-write' == h.lower():
            v = clean_acl('X-Container-Write', v)
            write_ref, write_groups = parse_acl(v)
            write_acl = v
    #if container.headers.get('x-container-read'):
    #   ref, groups = utils.parse_acl(container.headers.get('x-container-read'))
    #if container.headers.get('x-container-write'):
    #   ref, groups = utils.parse_acl(container.headers.get('x-container-write'))

    #ref, groups = parse_acl('test:test,hoge,.r:*')
    #read_ref, read_groups = ref, groups 
    #write_ref, write_groups = ref, groups 

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/acl.html', {
	'container_name' : container_name,
	'container' : container,
	'acl_form' : form,
        'remove_form' : remove_form,
        'read_acl_ref' : read_ref,
        'read_acl_groups' : read_groups,
        'write_acl_ref' : write_ref,
        'write_acl_groups' : write_groups,
        'write_acl' : write_acl,
        'read_acl' : read_acl
	}, context_instance=template.RequestContext(request))

@login_required
def user_list(request, tenant_id):
    try:
        users = api.users_list_for_token_and_tenant(request, request.user.token, tenant_id)
    except Exception, e:
        messages.error(request, 'Unable to get user list : %s' % str(e))
        users = None

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/users.html', {
        'users': users,
    }, context_instance=template.RequestContext(request))

