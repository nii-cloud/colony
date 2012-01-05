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
from openstackx.api import exceptions as api_exceptions
from glance.common import exception as glance_exception
from novaclient import exceptions as novaclient_exceptions


LOG = logging.getLogger('django_openstack.dash.views.images_metadata')


class UploadMetadata(forms.SelfHandlingForm):
    image_meta_file = forms.FileField(label="Image Metadata File")

    def handle(self, request, data):
        data = self.files['image_meta_file'].read()
        messages.success(request, "Image Metadata was successfully registerd")
        return shortcuts.redirect(request.build_absolute_uri())


@login_required
def index(request, tenant_id):
    tenant = {}

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
    'django_openstack/dash/images/index.html', {
        'tenant': tenant,
        'images': images,
    }, context_instance=template.RequestContext(request))

@login_required
def download(request, tenant_id, image_id):
    image = None
    try:
        image = api.image_get(request, image_id)
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
        return

    response = http.HttpResponse()
    response['Content-Disposition'] = 'attachment; filename=image-%s.xml' % image.name
    response.write("""
        <image>
           <name>%s</name>
        </image>
    """)

    return response

@login_required
def upload(request, tenant_id):
    form, handled = UploadMetadata.may_be_handle(request)
    if handled:
        return handled

    return render_to_response(
    'django_openstack/dash/images_metadata/upload.html', {
       'upload_form': form,
    }, context_instance=template.RequestContext(request))
