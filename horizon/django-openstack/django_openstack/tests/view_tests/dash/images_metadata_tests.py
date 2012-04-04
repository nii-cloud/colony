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

import tempfile
from django import http
from django.contrib import messages
from django.core.urlresolvers import reverse
from django_openstack import api
from django_openstack.tests.view_tests import base
from glance.common import exception as glance_exception
from openstackx.api import exceptions as api_exceptions
#from django_openstack.dash.views.images_metadata import _parse_location
from mox import IgnoreArg, IsA


class FakeQuota:
    ram = 100


class ImageViewTests(base.BaseViewTests):
    def setUp(self):
        super(ImageViewTests, self).setUp()
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage'}
        self.visibleImage = api.Image(image_dict)

        image_dict = {'name': 'invisibleImage',
                      'container_format': 'aki'}
        self.invisibleImage = api.Image(image_dict)

        self.images = (self.visibleImage, self.invisibleImage)

        flavor = self.mox.CreateMock(api.Flavor)
        flavor.id = 1
        flavor.name = 'm1.massive'
        flavor.vcpus = 1000
        flavor.disk = 1024
        flavor.ram = 10000
        self.flavors = (flavor,)

        keypair = self.mox.CreateMock(api.KeyPair)
        keypair.name = 'keyName'
        self.keypairs = (keypair,)

        security_group = self.mox.CreateMock(api.SecurityGroup)
        security_group.name = 'default'
        self.security_groups = (security_group,)

    def test_metadata_index(self):
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)

        self.mox.StubOutWithMock(api, 'image_list_detailed')
        api.image_list_detailed(IsA(http.HttpRequest)).AndReturn(self.images)

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.assertTemplateUsed(res,
                'django_openstack/dash/images_metadata/index.html')

        self.assertIn('images', res.context)
        images = res.context['images']
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()

    def test_metadata_download_invalid(self):
        IMAGE_ID=u'1'
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage',
                      'location' : 'swift://localhost/'}
        image = api.Image(image_dict)

        self.visibleImage = api.Image(image_dict)

        self.mox.StubOutWithMock(api, 'image_get_meta')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(image)

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))

        self.assertRedirectsNoFollow(res, reverse('dash_images_metadata', args=[self.TEST_TENANT]))
        self.mox.VerifyAll()

    def test_metadata_download_noimage(self):
        IMAGE_ID=u'1'
        self.mox.StubOutWithMock(api, 'image_get_meta')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(None)

        self.mox.ReplayAll()
        
        res = self.client.post(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))

        self.assertRedirectsNoFollow(res, reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.mox.VerifyAll()

    def test_metadata_upload_post(self):
        IMAGE_ID=u'1'
        METADATA_DATA = """
<image type="openstack-glance">
    <name>visibleImage</name>
    <location>swift://localhost/AUTH_test/Cont</location>
    <format>
      <disk />
      <container />
    </format>
    <size>0</size>
    <info>
       <min_disk>0</min_disk>
       <min_ram>1G</min_ram>
       <properties />
    </info>
</image>

"""
        METADATA_FILE = tempfile.TemporaryFile()
        METADATA_FILE.write(METADATA_DATA)
        METADATA_FILE.flush()
        METADATA_FILE.seek(0)
        
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage',
                      'location' : 'swift://localhost/',
                      'container_format' : '',
                      'disk_format' : '',
                      'image.size' : '',
                      'image.min_disk' : '',
                      'image.min_ram' : ''}
        form_data = {'method' : 'UploadMetadata',
                      'image_meta_file' : METADATA_FILE }

        image = api.Image(image_dict)

        self.visibleImage = api.Image(image_dict)

        #self.mox.StubOutWithMock(api, 'image_get_meta')
        #api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(image)
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)
        self.mox.StubOutWithMock(api, 'image_list_detailed')
        api.image_list_detailed(IsA(http.HttpRequest)).AndReturn(self.images)
        self.mox.StubOutWithMock(api, 'image_create')
        api.image_create(IsA(http.HttpRequest), image, None)

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_images_metadata', args=[self.TEST_TENANT]), form_data)
        self.assertTemplateUsed(res, 'django_openstack/dash/images_metadata/index.html')

        #self.assertIn('images', res.context)
        #images = res.context['images']
        #self.assertEqual(len(images), 1)
        #self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()

    def test_metadata_upload_post_invalid(self):
        IMAGE_ID=u'1'
        METADATA_DATA = 'objectData'
        METADATA_FILE = tempfile.TemporaryFile()
        METADATA_FILE.write(METADATA_DATA)
        METADATA_FILE.flush()
        METADATA_FILE.seek(0)
        
        form_data = {'method' : 'UploadMetadata',
                      'image_meta_file' : METADATA_FILE }

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IgnoreArg())
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)
        self.mox.StubOutWithMock(api, 'image_list_detailed')
        api.image_list_detailed(IsA(http.HttpRequest)).AndReturn(self.images)

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_images_metadata', args=[self.TEST_TENANT]), form_data)

        #self.assertIn('images', res.context)
        #images = res.context['images']
        #self.assertEqual(len(images), 1)
        #self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()

    def test_metadata_update_post(self):
        self.setActiveUser(self.TEST_TOKEN, self.TEST_USER, self.TEST_TENANT)
        IMAGE_ID=u'1'
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage',
                      'location' : 'swift://localhost/',
                      'container_format' : '',
                      'disk_format' : '',
                      'image.size' : '',
                      'image.min_disk' : '',
                      'image.min_ram' : ''}
        image = api.Image(image_dict)
        form_data = {'method' : 'UpdateImageForm',
                     'name' : 'visibleImage',
                     'image_id' : IMAGE_ID,
                     'location' : 'swift://localhost/',
                     'user' : 'user',
                     'password' : 'password' }

        self.visibleImage = api.Image(image_dict)

        self.mox.StubOutWithMock(api, 'image_get_meta')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(image)

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_metadata_update', args=[self.TEST_TENANT, IMAGE_ID]), form_data)


        #self.assertIn('images', res.context)
        #images = res.context['images']
        #self.assertEqual(len(images), 1)
        #self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()
    
    def test_metadata_update(self):
        IMAGE_ID=u'1'
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage',
                      'location' : 'swift://localhost/',
                      'container_format' : '',
                      'disk_format' : '',
                      'image.size' : '',
                      'image.min_disk' : '',
                      'image.min_ram' : ''}
        image = api.Image(image_dict)

        self.visibleImage = api.Image(image_dict)

        self.mox.StubOutWithMock(api, 'image_get_meta')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(image)

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_metadata_update', args=[self.TEST_TENANT, IMAGE_ID]))


        #self.assertIn('images', res.context)
        #images = res.context['images']
        #self.assertEqual(len(images), 1)
        #self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()

    def test_metadata_download(self):
        IMAGE_ID=u'1'
        image_dict = {'name': 'visibleImage',
                      'container_format': 'novaImage',
                      'location' : 'swift://localhost/',
                      'container_format' : '',
                      'disk_format' : '',
                      'size' : '',
                      'image.min_disk' : '',
                      'image.min_ram' : ''}
        image = api.Image(image_dict)

        self.visibleImage = api.Image(image_dict)

        self.mox.StubOutWithMock(api, 'image_get_meta')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndReturn(image)

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))


        #self.assertIn('images', res.context)
        #images = res.context['images']
        #self.assertEqual(len(images), 1)
        #self.assertEqual(images[0].name, 'visibleImage')

        self.mox.VerifyAll()

    def test_index_no_images(self):
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)

        self.mox.StubOutWithMock(api, 'image_list_detailed')
        api.image_list_detailed(IsA(http.HttpRequest)).AndReturn([])

        self.mox.StubOutWithMock(messages, 'info')
        messages.info(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.assertTemplateUsed(res,
                'django_openstack/dash/images_metadata/index.html')

        self.mox.VerifyAll()

    def test_download_metadata_client_conn_error(self):
        IMAGE_ID='1'

        self.mox.StubOutWithMock(api, 'image_get_meta')
        exception = glance_exception.ClientConnectionError('clientConnError')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))

        self.assertRedirectsNoFollow(res, reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.mox.VerifyAll()

    def test_download_metadata_glance_error(self):
        IMAGE_ID='1'

        self.mox.StubOutWithMock(api, 'image_get_meta')
        exception = glance_exception.Error('glanceError')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))

        self.assertRedirectsNoFollow(res, reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.mox.VerifyAll()

    def test_download_metadata_api_error(self):
        IMAGE_ID='1'

        self.mox.StubOutWithMock(api, 'image_get_meta')
        exception = api_exceptions.ApiException('ApiError')
        api.image_get_meta(IsA(http.HttpRequest), IMAGE_ID).AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_metadata_download', args=[self.TEST_TENANT, IMAGE_ID]))

        self.assertRedirectsNoFollow(res, reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.mox.VerifyAll()

    def test_index_client_conn_error(self):
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)

        self.mox.StubOutWithMock(api, 'image_list_detailed')
        exception = glance_exception.ClientConnectionError('clientConnError')
        api.image_list_detailed(IsA(http.HttpRequest)).AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.assertTemplateUsed(res,
                'django_openstack/dash/images_metadata/index.html')

        self.mox.VerifyAll()

    def test_index_glance_error(self):
        self.mox.StubOutWithMock(api, 'token_get_tenant')
        api.token_get_tenant(IsA(http.HttpRequest), self.TEST_TENANT)

        self.mox.StubOutWithMock(api, 'image_list_detailed')
        exception = glance_exception.Error('glanceError')
        api.image_list_detailed(IsA(http.HttpRequest)).AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')
        messages.error(IsA(http.HttpRequest), IsA(str))

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_images_metadata', args=[self.TEST_TENANT]))

        self.assertTemplateUsed(res,
                'django_openstack/dash/images_metadata/index.html')

        self.mox.VerifyAll()
