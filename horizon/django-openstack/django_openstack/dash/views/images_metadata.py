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
Views for managing Nova images.
"""

import datetime
import logging
import re
import urlparse

from django import http
from django import template
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render_to_response
from django.utils.text import normalize_newlines
from django.utils.translation import ugettext as _
from django import shortcuts

from django_openstack import api
from django_openstack import forms
from glance.common import exception as glance_exception
from lxml import etree
from novaclient import exceptions as novaclient_exceptions
from openstackx.api import exceptions as api_exceptions


LOG = logging.getLogger('django_openstack.dash.views.images_metadata')


class UpdateImageForm(forms.SelfHandlingForm):
    image_id = forms.CharField(widget=forms.HiddenInput())
    name = forms.CharField(max_length="25", label="Name")
    location = forms.CharField(label="Location")
    user = forms.CharField(label="User")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")

    def handle(self, request, data):
        image_id = data['image_id']
        tenant_id = request.user.tenant_id
        error_retrieving = _('Unable to retreive image info from glance: %s' % image_id)
        error_updating = _('Error updating image with id: %s' % image_id)

        scheme, loc, path = _parse_location(data['location'])
        auth = ":".join([data['user'] , data['password']])

        try:
            image = api.image_get_meta(request, image_id)
            #image = api.image_get(request, image_id)
        except glance_exception.ClientConnectionError, e:
            LOG.exception(_('Error connecting to glance'))
            messages.error(request, error_retrieving)
        except glance_exception.Error, e:
            LOG.exception(error_retrieving)
            messages.error(request, error_retrieving)

        if image.owner == request.user.username:
            try:
                meta = {
                    'is_public': True,
                    'name': data['name'],
                    'location' : "%s://%s@%s%s" % (scheme, auth, loc, path)
                }
                api.image_update(request, image_id, meta)
                messages.success(request, _('Image was successfully updated.'))

            except glance_exception.ClientConnectionError, e:
                LOG.exception(_('Error connecting to glance'))
                messages.error(request, error_retrieving)
            except glance_exception.Error, e:
                LOG.exception(error_updating)
                messages.error(request, error_updating)
            except:
                LOG.exception(_('Unspecified Exception in image update'))
                messages.error(request, error_updating)
            return redirect('dash_metadata_update', tenant_id, image_id)
        else:
            messages.info(request, _('Unable to update image. You are not its \
                                      owner.'))
            return redirect('dash_metadata_update', tenant_id, image_id)

                                                
class UploadMetadata(forms.SelfHandlingForm):
    image_meta_file = forms.FileField(label="Image Metadata File", required=True)

    def handle(self, request, data):

        if self.files['image_meta_file'].size > 1024 * 1024 * 256:
            messages.error(request, 'Metadata content is too big (more than 256MB)')

        data = self.files['image_meta_file'].read()

        try:
            root = etree.XML(data)
        except etree.XMLSyntaxError, e:
            messages.error(request, 'Metadata content is invalid %s' % str(e))
            return

        image = {}

        name = root.findtext("name")
        if not name:
            messages.error(request, 'Metadata content does not have Image name')
            return 
        image['name'] = name
        location = root.findtext('location')
        if location:
            image['location'] = location
        image['is_public'] = True
        image['owner'] = request.user.username

        meta = {}
        meta['disk_format'] = root.findtext("format/disk")
        meta['container_format'] = root.findtext("format/container")
        meta['size'] = root.findtext("info/size")
        meta['min_disk'] = root.findtext("info/min_disk")
        meta['min_ram'] = root.findtext("info/min_ram")
        properties = root.find("info/properties")

        # property
        prop = {}
        if properties is not None:
            for property in properties.getchildren():
                name = property.findtext('name')
                value = property.findtext('value')
                prop[name] = value
        meta['properties'] = prop

        meta_send = {}
        for key,value in meta.iteritems():
            if not value:
               continue
            meta_send[key] = value
        LOG.info('sending meta %s' % meta_send) 
        try:
            upload_image = api.image_create(request, image, None)
            try:
                update_image = api.image_update(request, upload_image.id , meta_send)
            except glance_exception.Invalid as e:
                messages.error(request, 'Image Metadata has invalid data %s' % str(e))
                update_image = api.image_update(request, upload_image.id, { 'location' : '' })
                api.image_delete(request, upload_image.id)
                return shortcuts.redirect(request.build_absolute_uri())
            messages.success(request, "Image Metadata was successfully registerd")
        except glance_exception.BadStoreUri as e:
            messages.error(request, 'Metadata has bad location %s' % str(e))

        return shortcuts.redirect(request.build_absolute_uri())

# utility
def _parse_location(url):
    image_loc = urlparse.urlparse(url)
    location = image_loc.netloc.split('@', 1)[-1]
    if location.startswith('['):
       location = location[1:].split(']')[0]
    return image_loc.scheme, location, image_loc.path

def _parse_user(url):
    image_loc = urlparse.urlparse(url)
    creds = image_loc.netloc.split('@', 1)[0]
    creds_list = creds.split(':')
    if len(creds_list) == 1:
        return ''.join(creds_list)
    elif len(creds_list) == 2:
        return creds_list[0]
    elif len(creds_list) == 3:
        return ':'.join(creds_list[0:1])

@login_required
def index(request, tenant_id):
    tenant = {}

    form, handled = UploadMetadata.maybe_handle(request)
    if handled:
        return handled

    try:
        tenant = api.token_get_tenant(request, request.user.tenant_id)
    except api_exceptions.ApiException, e:
        messages.error(request, "Unable to retrienve tenant info\
                                 from keystone: %s" % e.message)

    all_images = []
    try:
        all_images = api.image_list_detailed(request)
        if not all_images:
            messages.info(request, "There are currently no images.")
    except glance_exception.ClientConnectionError, e:
        LOG.exception("Error connecting to glance")
        messages.error(request, "Error connecting to glance: %s" % str(e))
    except glance_exception.Error, e:
        LOG.exception("Error retrieving image list")
        messages.error(request, "Error retrieving image list: %s" % str(e))
    except api_exceptions.ApiException, e:
        msg = "Unable to retreive image info from glance: %s" % str(e)
        LOG.exception(msg)
        messages.error(request, msg)

    images = [im for im in all_images
              if im['container_format'] not in ['aki', 'ari']]

    return render_to_response(
    'django_openstack/dash/images_metadata/index.html', {
        'tenant': tenant,
        'images': images,
        'upload_form' : form,
    }, context_instance=template.RequestContext(request))

@login_required
def download(request, tenant_id, image_id):
    image = None
    try:
        image = api.image_get_meta(request, image_id)
    except glance_exception.ClientConnectionError, e:
        LOG.exception("Error connecting to glance")
        messages.error(request, "Error connecting to glance: %s" % str(e))
    except glance_exception.Error, e:
        LOG.exception("Error retrieving image list")
        messages.error(request, "Error retrieving image list: %s" % str(e))
    except api_exceptions.ApiException, e:
        msg = "Unable to retreive image info from glance: %s" % str(e)
        LOG.exception(msg)
        messages.error(request, msg)

    if not image:
        return shortcuts.redirect('dash_images_metadata', tenant_id)


    if not image.location:
        messages.error(request, "Image location is not specified for %s" % image.name)
        return shortcuts.redirect('dash_images_metadata', tenant_id)
        
    scheme, location, path = _parse_location(image.location)

    try:
        property_value = []
        if image.properties:
            for key in ['architecture', 'image_location', 'image_state', 'kernel_id', 'project_id', 'ramdisk_id']:
                if image.properties.get(key):
                    item = """
                   <item>
                       <name>%s</name>
                       <value>%s</value>
                   </item>""" % (propkey, propval)
                    property_value.append(item)
        data = """
        <image type="openstack-glance">
          <name>%s</name>
          <location>%s</location>
          <format>
            <disk>%s</disk>
            <container>%s</container>
          </format>
          <info>
              <size>%s</size>
              <min_disk>%s</min_disk>
              <min_ram>%s</min_ram>
              <properties>
              %s
              </properties>
          </info>
        </image>
        """ % (image.name, "%s://%s%s" % (scheme,location, path), 
               image.disk_format if image.disk_format else '',
               image.container_format if image.container_format else '',
               image.size, 
               image.min_disk, image.min_ram, ''.join(property_value))
    except AttributeError as e:
        messages.error(request, 
                       'Unable to retrieve image metadata %s' % str(e))
        return shortcuts.redirect('dash_images_metadata', tenant_id)

    response = http.HttpResponse()
    response['Content-Disposition'] = 'attachment; filename=image-%s.xml' % image.name
    response.write(data)

    return response

@login_required
def update(request, tenant_id, image_id):
    try:
        image = api.image_get_meta(request, image_id)
    except glance_exception.ClientConnectionError, e:
        LOG.exception("Error connecting to glance")
        messages.error(request, "Error connecting to glance: %s"
                                 % e.message)
    except glance_exception.Error, e:
        LOG.exception('Error retrieving image with id "%s"' % image_id)
        messages.error(request, "Error retrieving image %s: %s"
                                 % (image_id, e.message))

    scheme, location, path = _parse_location(image.location)
    form, handled = UpdateImageForm.maybe_handle(request, initial={
                 'image_id': image_id,
                 'name': image.get('name', ''),
                 'location' : '%s://%s%s' % ( scheme, location, path),
                 'user': _parse_user(image.location),
                 'password' : '',
                 })
    if handled:
        return handled

    return render_to_response('django_openstack/dash/images_metadata/update.html', {
        'form': form,
    }, context_instance=template.RequestContext(request))

