

from django import http
from django_openstack import forms
from django_openstack import test
from django_openstack.dash.views import containers
from django_openstack.tests.view_tests import base


class ContainerFormTests(base.BaseViewTests):
    def setUp(self):
        super(ContainerFormTests, self).setUp()


    def test_delete_container(self):
        request = http.HttpRequest()
        forms, handled = containers.DeleteContainer.maybe_handle(request)
        self.assertEqual(forms.is_valid(), False)

    def test_delete_container_2(self):
        request = http.HttpRequest()
        request.POST['method'] = 'DeleteContainer'
        forms, handled = containers.DeleteContainer.maybe_handle(request)
        self.assertEqual(forms.is_valid(), False)

    def test_create_container(self):
        request = http.HttpRequest()
        forms, handled = containers.CreateContainer.maybe_handle(request)

    def test_create_container_2(self):
        request = http.HttpRequest()
        request.POST['method'] = 'CreateContainer'
        forms, handled = containers.CreateContainer.maybe_handle(request)
        self.assertEqual(forms.is_valid(), False)

    def test_create_container_3(self):
        request = http.HttpRequest()
        request.POST.update({'method': 'CreateContainer',
                                       'name' : 'a' * 100})
        forms = containers.CreateContainer(request.POST)

        self.assertEqual(forms.is_valid(), True)

    def test_create_container_7(self):
        request = http.HttpRequest()
        request.POST.update({'method': 'CreateContainer',
                                       'name' : 'a' * 300})
        forms = containers.CreateContainer(request.POST)
        self.assertEqual(forms.is_valid(), False)


    def test_container_acl_1(self):
        request = http.HttpRequest()
        request.POST.update({'method': 'ContainerAcl',
                                       'acl_add' : 'a' * 300})
        forms = containers.ContainerAcl(request.POST)
        self.assertEqual(forms.is_valid(), False)
