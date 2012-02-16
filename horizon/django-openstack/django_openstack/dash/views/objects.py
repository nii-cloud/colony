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

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from cloudfiles.errors import NoSuchContainer, NoSuchObject, ResponseError
from django import http
from django import template
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import shortcuts
from django.shortcuts import render_to_response

from django_openstack import api
from django_openstack import forms

from urllib import unquote

LOG = logging.getLogger('django_openstack.dash')


class FilterObjects(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    object_prefix = forms.CharField(required=False)

    def handle(self, request, data):
        object_prefix = data['object_prefix'] or None
        container_name = data['container_name'] or None
        if object_prefix:
            object_prefix = object_prefix.encode('utf-8')
        if container_name:
            container_name = container_name.encode('utf-8')
        try:
           objects = api.swift_get_objects(request, container_name,
                         None,request.session.get('storage_url', None))
        except NoSuchContainer, e:
            messages.error(request, 'No Such Container %s' % container_name)
            return None

        if not objects:
            messages.info(request,
                          'There are no objects matching that prefix in %s' %
                          data['container_name'])
        return objects


class DeleteObject(forms.SelfHandlingForm):
    object_name = forms.CharField(widget=forms.HiddenInput())
    container_name = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        api.swift_delete_object(
                request,
                data['container_name'],
                data['object_name'],
                request.session.get('storage_url', None))
        messages.info(request,
                      'Successfully deleted object: %s' % \
                      data['object_name'])
        return None


class UploadObject(forms.SelfHandlingForm):
    name = forms.CharField(max_length="255", label="Object Name")
    object_file = forms.FileField(label="File")
    container_name = forms.CharField(widget=forms.HiddenInput())

    def handle(self, request, data):
        try:
            file = self.files['object_file']
            cont = data['container_name']
            cont = cont.encode('utf-8')
            obj = data['name']
            obj = obj.encode('utf-8')
            obj = obj.replace('/', '%2F')
            api.swift_upload_object_with_manifest(request, cont, obj, file,
                request.session.get('storage_url', None))
            messages.success(request, "Object was successfully uploaded.")
        except Exception as e:
            messages.error(request, "Upload Object was failed (%s)" % str(e))

        return None


class CopyObject(forms.SelfHandlingForm):
    new_container_name = forms.ChoiceField(
        label="Container to store object in")

    new_object_name = forms.CharField(max_length="1024",
                                      label="New object name")
    orig_container_name = forms.CharField(widget=forms.HiddenInput())
    orig_object_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        containers = kwargs.pop('containers')

        super(CopyObject, self).__init__(*args, **kwargs)

        self.fields['new_container_name'].choices = containers

    def handle(self, request, data):

        values = {}
        values['orig_cont'] = data['orig_container_name']
        values['orig_obj']  = data['orig_object_name']
        values['new_cont'] = data['new_container_name']
        values['new_obj'] = data['new_object_name']

        escaped = {}
        for key, value in values.iteritems():
            #escaped[key] = value.encode('utf-8').replace('/', '%2F')
            escaped[key] = value.encode('utf-8')


        try:
            api.swift_copy_object(request, escaped['orig_cont'],
                                  escaped['orig_obj'] , escaped['new_cont'],
                                  escaped['new_obj'],
                                  request.session.get('storage_url', None))
 
            messages.success(request,
                             'Object was successfully copied to %s/%s' %
                             (values['new_cont'], values['new_obj']))
        except NoSuchContainer, e:
            messages.error(request, 'Object copy is failed. %s' % str(e))
        except ResponseError, e:
            messages.error(request, 'Object copy is failed. %s' % str(e))

        return None

class ObjectMeta(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    object_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(max_length="128", label="Name")
    header_value = forms.CharField(max_length="256", label="Value")

    def __init__(self, *args, **kwargs):
        super(ObjectMeta, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        value = data['header_value']
        container_name = data['container_name']
        object_name = data['object_name']

        try:
           header.encode('ascii')
           value.encode('ascii')
        except UnicodeEnccodeError, e:
           messages.error(request, "Object metadata contains non-ASCII character %s" % str(e))
           return None

        if not header.lower().startswith('x-object-meta-'):
            messages.error(request, 'Object metadata must begin with x-object-meta-')
            return None

        hdrs = {}
        hdrs[header[14:]] = value

        try:
            api.swift_set_object_info(request, container_name, object_name, hdrs, 
                               request.session.get('storage_url', None))
        except ResponseError, e:
            messages.error(request, 'Unable to set object metadata : %s' % str(e))

        return None

class ObjectMetaRemove(forms.SelfHandlingForm):
    container_name = forms.CharField(widget=forms.HiddenInput())
    object_name = forms.CharField(widget=forms.HiddenInput())
    header_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ObjectMetaRemove, self).__init__(*args, **kwargs)

    def handle(self, request, data):
        header = data['header_name']
        container_name = data['container_name']
        object_name = data['object_name']

        if not header.lower().startswith('x-object-meta-'):
            messages.error(request, 'Object metadata must begin with x-object-meta-')
        else:
            hdrs = {}
            hdrs[header[14:]] = ''
            try:
               api.swift_remove_object_info(request, container_name, object_name, hdrs,
                               request.session.get('storage_url', None))
            except ResponseError, e:
               messages.error(request, 'Removing Object Metadata fails %s' % str(e))

        return None
 

@login_required
def index(request, tenant_id, container_name):
    delete_form, handled = DeleteObject.maybe_handle(request)
    if handled:
        return handled

    filter_form, objects = FilterObjects.maybe_handle(request)
    container_name_unquoted = unquote(container_name)

    if objects is None:
        filter_form.fields['container_name'].initial = container_name
        try:
           objects = api.swift_get_objects(request, container_name, 
                               None, request.session.get('storage_url', None))
        except NoSuchContainer, e:
           messages.error(request, 'No Such Container %s' % container_name)
        except ResponseError, e:
           messages.error(request, 'Unable to get list of objects : %s' % str(e))

    delete_form.fields['container_name'].initial = container_name
    return render_to_response(
    'django_openstack/dash/objects/index.html', {
        'container_name': container_name,
        'container_name_unquoted': container_name_unquoted,
        'objects': objects,
        'delete_form': delete_form,
        'filter_form': filter_form,
    }, context_instance=template.RequestContext(request))


@login_required
def upload(request, tenant_id, container_name):
    form, handled = UploadObject.maybe_handle(request)
    if handled:
        return handled

    container_name_unquoted = unquote(container_name)
    form.fields['container_name'].initial = container_name
    return render_to_response(
    'django_openstack/dash/objects/upload.html', {
        'container_name': container_name,
        'container_name_unquoted': container_name_unquoted,
        'upload_form': form,
    }, context_instance=template.RequestContext(request))


@login_required
def download(request, tenant_id, container_name, object_name):

    try:
        object_data = api.swift_get_object_data(
                request, container_name, object_name,
                               request.session.get('storage_url', None))
    except NoSuchObject, e:
        messages.error('Error occurs in downloading object %s' % str(e))
        request.redirect('dash_objects', tenant_id, container_name)

    response = http.HttpResponse()
    response['Content-Disposition'] = 'attachment; filename=%s' % \
            object_name.encode('utf-8')
    for data in object_data:
        response.write(data)
    return response


@login_required
def copy(request, tenant_id, container_name, object_name):
    containers = \
            [(c.unquote_name, c.unquote_name) for c in api.swift_get_containers(
                    request, request.session.get('storage_url', None)) ]
    form, handled = CopyObject.maybe_handle(request, containers=containers)

    container_name_unquoted = unquote(container_name)
    object_name_unquoted = unquote(object_name)

    if handled:
        return handled

    form.fields['new_container_name'].initial = container_name_unquoted
    form.fields['orig_container_name'].initial = container_name_unquoted
    form.fields['orig_object_name'].initial = object_name_unquoted

    return render_to_response(
        'django_openstack/dash/objects/copy.html',
        {'container_name': container_name,
         'container_name_unquoted' : container_name_unquoted,
         'object_name': object_name,
         'object_name_unquoted' : object_name_unquoted,
         'copy_form': form},
        context_instance=template.RequestContext(request))


@login_required
def meta(request, tenant_id, container_name, object_name):

    form, handled = ObjectMeta.maybe_handle(request)
    if handled:
        return handled

    remove_form, handled = ObjectMetaRemove.maybe_handle(request)
    if handled:
        return handled


    container_name_unquoted = unquote(container_name)
    object_name_unquoted = unquote(object_name)

    try:
        metadata = api.swift_get_object_info(request, container_name, object_name,
                                             request.session.get('storage_url', None))
        headers = []
        if metadata:
            for h, v in metadata.iteritems():
                headers.append(('%s-%s' % ('x-object-meta',h) ,v))
    except ResponseError, e:
        messages.error('Retrieving Metadata from %s is failed: %s' % (container_name_unquoted, str(e)))

    return render_to_response(
        'django_openstack/dash/objects/meta.html',
        {'container_name': container_name,
         'container_name_unquoted': container_name_unquoted,
         'object_name': object_name,
         'object_name_unquoted': object_name_unquoted,
         'metadata' : headers,
         'meta_form' : form,
         'remove_form' : remove_form
        },
        context_instance=template.RequestContext(request))
