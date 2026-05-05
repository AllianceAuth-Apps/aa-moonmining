from http import HTTPStatus

from django.test import TestCase

from app_utils.testdata_factories import UserFactory

from moonmining.tests.testdata.factories_2 import EveOreTypeFactory


class TestAdminUI(TestCase):
    def test_should_open_prices_page(self):
        # given
        EveOreTypeFactory()
        user = UserFactory(is_superuser=True, is_staff=True)
        self.client.force_login(user)
        # when
        response = self.client.get("/admin/moonmining/eveoretype/")
        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
