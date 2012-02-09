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

from django import http
from django import template
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import shortcuts
from django.shortcuts import render_to_response

from django_openstack import api
from django_openstack import forms


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

        objects = api.swift_get_objects(request,
                                        container_name,
                                        prefix=object_prefix)

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
                data['object_name'])
        messages.info(request,
                      'Successfully deleted object: %s' % \
                      data['object_name'])
        return shortcuts.redirect(request.build_absolute_uri())


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
            api.swift_upload_object_with_manifest(request, cont, obj, file)
            messages.success(request, "Object was successfully uploaded.")
        except Exception as e:
            messages.error(request, "Upload Object was failed (%s)" % str(e))
        return shortcuts.redirect(request.build_absolute_uri())


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


        orig_container_name = data['orig_container_name']
        orig_object_name = data['orig_object_name']
        new_container_name = data['new_container_name']
        new_object_name = data['new_object_name']
        orig_container_name = orig_container_name.encode('utf-8')
        orig_object_name = orig_object_name.encode('utf-8')
        new_container_name = new_container_name.encode('utf-8')
        new_object_name = new_object_name.encode('utf-8')


        api.swift_copy_object(request, orig_container_name,
                              orig_object_name, new_container_name,
                              new_object_name)

        messages.success(request,
                         'Object was successfully copied to %s\%s' %
                         (new_container_name, new_object_name))

        return shortcuts.redirect(request.build_absolute_uri())

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

        if not header.lower().startswith('x-object-meta-'):
            messages.error(request, 'Object metadata must begin with x-object-meta-')
        else:
            hdrs = {}
            hdrs[header[14:]] = value
            api.swift_set_object_info(request, container_name, object_name, hdrs)

        return shortcuts.redirect(request.build_absolute_uri())

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
            api.swift_remove_object_info(request, container_name, object_name, hdrs)

        return shortcuts.redirect(request.build_absolute_uri())
 

@login_required
def index(request, tenant_id, container_name):
    delete_form, handled = DeleteObject.maybe_handle(request)
    if handled:
        return handled

    filter_form, objects = FilterObjects.maybe_handle(request)

    if objects is None:
        filter_form.fields['container_name'].initial = container_name
        objects = api.swift_get_objects(request, container_name)

    delete_form.fields['container_name'].initial = container_name
    return render_to_response(
    'django_openstack/dash/objects/index.html', {
        'container_name': container_name,
        'objects': objects,
        'delete_form': delete_form,
        'filter_form': filter_form,
    }, context_instance=template.RequestContext(request))


@login_required
def upload(request, tenant_id, container_name):
    form, handled = UploadObject.maybe_handle(request)
    if handled:
        return handled

    form.fields['container_name'].initial = container_name
    return render_to_response(
    'django_openstack/dash/objects/upload.html', {
        'container_name': container_name,
        'upload_form': form,
    }, context_instance=template.RequestContext(request))


@login_required
def download(request, tenant_id, container_name, object_name):
    object_data = api.swift_get_object_data(
            request, container_name, object_name)

    response = http.HttpResponse()
    response['Content-Disposition'] = 'attachment; filename=%s' % \
            object_name.encode('utf-8')
    for data in object_data:
        response.write(data)
    return response


@login_required
def copy(request, tenant_id, container_name, object_name):
    containers = \
            [(c.name, c.name) for c in api.swift_get_containers(
                    request)]
    form, handled = CopyObject.maybe_handle(request,
            containers=containers)

    if handled:
        return handled

    form.fields['new_container_name'].initial = container_name
    form.fields['orig_container_name'].initial = container_name
    form.fields['orig_object_name'].initial = object_name

    return render_to_response(
        'django_openstack/dash/objects/copy.html',
        {'container_name': container_name,
         'object_name': object_name,
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

    metadata = api.swift_get_object_info(request, container_name, object_name)

    headers = []
    if metadata:
        for h, v in metadata.iteritems():
            headers.append(('%s-%s' % ('x-object-meta',h) ,v))
    return render_to_response(
        'django_openstack/dash/objects/meta.html',
        {'container_name': container_name,
         'object_name': object_name,
         'metadata' : headers,
         'meta_form' : form,
         'remove_form' : remove_form
        },
        context_instance=template.RequestContext(request))
