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

from django import template
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import shortcuts

from django_openstack import api
from django_openstack import forms
from django_openstack.acl import parse_acl, clean_acl

from cloudfiles.errors import ContainerNotEmpty


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
        else:
            messages.info(request,
                      'Successfully deleted container: %s' % \
                      data['container_name'])
        return shortcuts.redirect(request.build_absolute_uri())


class CreateContainer(forms.SelfHandlingForm):
    name = forms.CharField(max_length="255", label="Container Name")

    def handle(self, request, data):
        api.swift_create_container(request, data['name'])
        messages.success(request, "Container was successfully created.")
        return shortcuts.redirect("dash_containers", request.user.tenant_id)

class ContainerMetaRemove(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ContainerMetaRemove, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        container_name = data['container_name']

        hdrs = {}
        hdrs[header] = ''

        api.swift_set_container_info(request, container_name, hdrs)

        return shortcuts.redirect(request.build_absolute_uri())

class ContainerMeta(forms.SelfHandlingForm):
    ''' Form that handles Swift Container Meta Data '''
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(max_length="128", label='Name', required=True)
    header_value = forms.CharField(max_length="256", label="Value", required=True)
    
    def __init__(self, *args, **kwargs):
        super(ContainerMeta, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        value = data['header_value']
        container_name = data['container_name']

        hdrs = {}
        hdrs[header] = value

        api.swift_set_container_info(request, container_name, hdrs)

        return shortcuts.redirect(request.build_absolute_uri())

class ContainerAclRemove(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ContainerAclRemove, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        container_name = data['container_name']

        return shortcuts.redirect(request.build_absolute_uri())

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
        if acl_type:
           type = 'X-Container-Read'
           acl_value = data['read_acl']
        else:
           type = 'X-Container-Write'
           acl_value = data['write_acl']

        # clean and parse acl
        acl = clean_acl(type, data['acl_add'])
        acl_orig = clean_acl(type, acl_value)
        group_add, ref_add = parse_acl(acl)
        group_orig, ref_orig = parse_acl(acl_orig)

        # duplicate check
        acl_result = []
        acl_ref_result = []
        for item in group_add:
            if not item in group_orig:
                acl_result.append(item)
        for item in ref_add:
            if not item in ref_orig:
                acl_ref_result.append(item)

        group_result = group_add + acl_result
        ref_result = acl_ref_result + ref_orig

        # set header
        hdrs = {}
        hdrs[type] = ','.join(group_result + ref_result)
        api.swift_set_container_info(request, container_name, hdrs)
       
        return shortcuts.redirect(request.build_absolute_uri()) 


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
            if name == 'x-container-meta-web-listing':
                self.fields['html_listing'].initial = value == 'true'
            if name == 'x-container-meta-web-listing-css':
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
        html_listing = data['html_listing']
        use_css_in_listing = data['use_css_in_listing']
        container_name = data['container_name']
        for name in ['Index', 'Listing', 'Listing-Css', 'Error']:
           hdrs['X-Container-Meta-Web-' + name] = ''
        if public_html:
           hdrs['X-Container-Meta-Web-Index'] = index_object_name
        if html_listing:
           hdrs['X-Container-Meta-Web-Listing'] = 'true'
        if use_css_in_listing:
           hdrs['X-Container-Meta-Web-Listing-Css'] = css_object_name
        if error:
           hdrs['X-Container-Meta-Web-Error'] = error

        api.swift_set_container_info(request, container_name, hdrs)

        return shortcuts.redirect("dash_containers", request.user.tenant_id)

@login_required
def index(request, tenant_id):
    delete_form, handled = DeleteContainer.maybe_handle(request)
    if handled:
        return handled

    containers = []
    try:
        containers = api.swift_get_containers(request)
    except Exception, e:
        msg = "Unable to retrieve containers from swift: %s" % str(e)
        LOG.exception(msg)
        messages.error(request, msg)

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/index.html', {
        'containers': containers,
        'delete_form': delete_form,
    }, context_instance=template.RequestContext(request))


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
    container = api.swift_get_container(request, container_name)
    objects = [(o.name, o.name) for o in api.swift_get_objects(request, container_name)]
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

    container = api.swift_get_container(request, container_name)
    headers = []
    for h, v in container.headers:
        if h.startswith('x-container-meta'):
             headers.append((h,v))

    return shortcuts.render_to_response(
    'django_openstack/dash/containers/meta.html', {
       'container_name' : container_name,
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

    container = api.swift_get_container(request, container_name)
    read_ref, read_groups, write_ref, write_groups = [],[],[],[]
    read_acl, write_acl = '', ''
    for h,v in container.headers:
        if 'x-container-read' == h:
            v = clean_acl('X-Container-Read', v)
            read_ref, read_groups = parse_acl(v)
            read_acl = v
        if 'x-container-write' == h:
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
    users = api.users_list_for_token_and_tenant(request, request.user.token, tenant_id)
    return shortcuts.render_to_response(
    'django_openstack/dash/containers/users.html', {
        'users': users,
    }, context_instance=template.RequestContext(request))

