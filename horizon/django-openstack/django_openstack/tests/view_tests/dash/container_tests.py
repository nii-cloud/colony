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

from cloudfiles.errors import ContainerNotEmpty
from django import http
from django.contrib import messages
from django.core.urlresolvers import reverse
from django_openstack import api
from django_openstack.tests.view_tests import base
from mox import IgnoreArg, IsA


class ContainerViewTests(base.BaseViewTests):
    def setUp(self):
        super(ContainerViewTests, self).setUp()
        self.container = self.mox.CreateMock(api.Container)
        self.container.name = 'containerName'
        self.container.headers = {}
        self.object = self.mox.CreateMock(api.SwiftObject)
        self.object.name = 'objectName'

    def test_index(self):
        self.mox.StubOutWithMock(api, 'swift_get_containers')
        api.swift_get_containers(
                IsA(http.HttpRequest)).AndReturn([self.container])

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_containers', args=['tenant']))

        self.assertTemplateUsed(res,
                'django_openstack/dash/containers/index.html')
        self.assertIn('containers', res.context)
        containers = res.context['containers']

        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0].name, 'containerName')

        self.mox.VerifyAll()

    def test_delete_container(self):
        formData = {'container_name': 'containerName',
                    'method': 'DeleteContainer'}

        self.mox.StubOutWithMock(api, 'swift_delete_container')
        api.swift_delete_container(IsA(http.HttpRequest),
                                   'containerName')

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_containers', args=['tenant']),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                                  args=['tenant']))

        self.mox.VerifyAll()

    def test_delete_container_invalid(self):
        formData = { 'method': 'DeleteContainer'}

        exception = ContainerNotEmpty('containerNotEmpty')

        self.mox.StubOutWithMock(api, 'swift_delete_container')
        api.swift_delete_container(
                IsA(http.HttpRequest),
                'containerName')

        self.mox.StubOutWithMock(messages, 'error')

        messages.error(IgnoreArg(), IsA(unicode))

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_containers', args=['tenant']),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                          args=['tenant']))

        self.mox.VerifyAll()

    def test_delete_container_nonempty(self):
        formData = {'container_name': 'containerName',
                          'method': 'DeleteContainer'}

        exception = ContainerNotEmpty('containerNotEmpty')

        self.mox.StubOutWithMock(api, 'swift_delete_container')
        api.swift_delete_container(
                IsA(http.HttpRequest),
                'containerName').AndRaise(exception)

        self.mox.StubOutWithMock(messages, 'error')

        messages.error(IgnoreArg(), IsA(unicode))

        self.mox.ReplayAll()

        res = self.client.post(reverse('dash_containers', args=['tenant']),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                          args=['tenant']))

        self.mox.VerifyAll()

    def test_container_public_put(self):
       
        formData = {'container_name':'containerName',
                    'method':'MakePublicContainer',
                    'index_object_name' : 'index',
                        'css_object_name' : 'index'}

        self.mox.StubOutWithMock(api, 'swift_get_container')
        api.swift_get_container(
                                IsA(http.HttpRequest), self.container.name
                                ).AndReturn(self.container)
        
        self.mox.StubOutWithMock(api, 'swift_get_objects')
        api.swift_get_objects(
                              IsA(http.HttpRequest), self.container.name
                              ).AndReturn([self.object])

        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                                     IsA(http.HttpRequest), self.container.name,
                                     {})
        
        self.mox.ReplayAll()
            
        res = self.client.post(reverse('dash_containers_public', args=['tenant', self.container.name]),
                                       formData)

    def test_container_public_get(self):
        self.mox.StubOutWithMock(api, 'swift_get_container')
        api.swift_get_container(
                IsA(http.HttpRequest), self.container.name).AndReturn(self.container)

        self.mox.StubOutWithMock(api, 'swift_get_objects')
        api.swift_get_objects(
                IsA(http.HttpRequest), self.container.name).AndReturn([self.object])
                
        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_containers_public',
                              args=['tenant', self.container.name]))

        self.assertTemplateUsed(res, 'django_openstack/dash/containers/public.html')
        self.mox.VerifyAll()


    def test_container_meta_get(self):
        ret_container = self.container
        ret_container.headers = [('x-container-meta-fuga','test'), ('x-container-meta-hoge', 'fuga') ]
        self.mox.StubOutWithMock(api, 'swift_get_container')
        api.swift_get_container(
                IsA(http.HttpRequest), self.container.name).AndReturn(ret_container)

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_containers_meta',
                              args=['tenant', self.container.name]))

        self.assertTemplateUsed(res, 'django_openstack/dash/containers/meta.html')
        self.mox.VerifyAll()

    def test_container_meta_remove(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerMetaRemove',
                    'header_name' : 'x-container-meta-test' }
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'x-container-meta-test' : ''})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_meta',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.mox.VerifyAll()

    def test_container_meta_put_maxlen(self):

        postvalue = 'v' * 4099 # length limit over
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerMeta',
                    'header_name' : 'x-container-meta-test',
                    'header_value' : postvalue }
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'x-container-meta-test':postvalue})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_meta',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_meta',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_container_meta_put(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerMeta',
                    'header_name' : 'x-container-meta-test',
                    'header_value' : 'hoge' }
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'x-container-meta-test':'hoge'})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_meta',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_meta',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_container_acl_get(self):
        self.mox.StubOutWithMock(api, 'swift_get_container')
        ret_container = self.container
        ret_container.headers = [('x-container-read','test'), ('x-container-write', 'fuga') ]
        api.swift_get_container(
                IsA(http.HttpRequest), self.container.name).AndReturn(ret_container)

        self.mox.ReplayAll()

        res = self.client.get(reverse('dash_containers_acl',
                              args=['tenant', self.container.name]))

        self.assertTemplateUsed(res, 'django_openstack/dash/containers/acl.html')
        self.mox.VerifyAll()

    def test_container_acl_put_write(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerAcl',
                    'acl_add' : 'test',
                    'write_acl' : ''}
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'X-Container-Write' : 'test'})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_acl',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_acl',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_container_acl_put_write_duplicate(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerAcl',
                    'acl_add' : 'test',
                    'write_acl' : 'test'}
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'X-Container-Write' : 'test'})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_acl',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_acl',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_contianer_acl_put_read(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerAcl',
                    'acl_add' : 'test',
                    'read_acl' : ''}
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'X-Container-Read' : 'test'})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_acl',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_acl',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_contianer_acl_put_read_duplicate(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerAcl',
                    'acl_add' : 'test',
                    'read_acl' : 'test'}
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'X-Container-Read' : 'test'})
        self.mox.ReplayAll()
        res = self.client.post(reverse('dash_containers_acl',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_acl',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()

    def test_container_acl_remove(self):
        formData = {'container_name' : 'containerName',
                    'method' : 'ContainerAclRemove',
                    'header_name' : 'X-Container-Write',
                    'read_acl' : 'test'}
        self.mox.StubOutWithMock(api, 'swift_set_container_info')
        api.swift_set_container_info(
                    IsA(http.HttpRequest), self.container.name, {'X-Container-Write':''})
       
        self.mox.ReplayAll()
 
        res = self.client.post(reverse('dash_containers_acl',
                                       args=[self.request.user.tenant_id, self.container.name]),
                                       formData) 
        self.assertRedirectsNoFollow(res, reverse('dash_containers_acl',
                                                  args=[self.request.user.tenant_id, self.container.name]))
        self.mox.VerifyAll()
        
    def test_create_container_get(self):
        res = self.client.get(reverse('dash_containers_create',
                              args=['tenant']))

        self.assertTemplateUsed(res,
                'django_openstack/dash/containers/create.html')

    def test_create_container_post_limitover(self):
        formData = { 'method': 'CreateContainer',
                     'container_name' : 'value' * 60 }

        self.mox.StubOutWithMock(api, 'swift_create_container')
        api.swift_create_container(
                IsA(http.HttpRequest), 'CreateContainer')

        self.mox.StubOutWithMock(messages, 'success')
        messages.success(IgnoreArg(), IsA(str))

        res = self.client.post(reverse('dash_containers_create',
                                       args=[self.request.user.tenant_id]),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                          args=[self.request.user.tenant_id]))

    def test_create_container_post_badformvalue(self):
        formData = { 'method': 'CreateContainer'}

        self.mox.StubOutWithMock(api, 'swift_create_container')
        api.swift_create_container(
                IsA(http.HttpRequest), 'CreateContainer')

        self.mox.StubOutWithMock(messages, 'success')
        messages.success(IgnoreArg(), IsA(str))

        res = self.client.post(reverse('dash_containers_create',
                                       args=[self.request.user.tenant_id]),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                          args=[self.request.user.tenant_id]))

    def test_create_container_post(self):
        formData = {'name': 'containerName',
                    'method': 'CreateContainer'}

        self.mox.StubOutWithMock(api, 'swift_create_container')
        api.swift_create_container(
                IsA(http.HttpRequest), 'CreateContainer')

        self.mox.StubOutWithMock(messages, 'success')
        messages.success(IgnoreArg(), IsA(str))

        res = self.client.post(reverse('dash_containers_create',
                                       args=[self.request.user.tenant_id]),
                               formData)

        self.assertRedirectsNoFollow(res, reverse('dash_containers',
                                          args=[self.request.user.tenant_id]))
