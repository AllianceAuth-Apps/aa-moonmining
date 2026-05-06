from http import HTTPStatus
from typing import Set

from django.test import RequestFactory, TestCase

from app_utils.testdata_factories import UserMainFactory

from moonmining.models import Owner
from moonmining.tests import helpers
from moonmining.tests.testdata.factories_2 import (
    MoonFactory2,
    OwnerFactory2,
    RefineryFactory2,
)
from moonmining.views import moons


def _response_to_ids(response) -> Set[int]:
    data = helpers.json_response_to_python_2(response)
    return {int(obj[0]) for obj in data}


class TestMoonsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

    def test_should_return_all_moons(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.view_all_moons"],
        )
        moon_1 = MoonFactory2()
        moon_2 = MoonFactory2()
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.ALL)

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data_1 = helpers.json_response_to_python_2(response)
        data_2 = {int(obj[0]): obj for obj in data_1}
        self.assertSetEqual(set(data_2.keys()), {moon_1.id, moon_2.id})
        obj = data_2[moon_1.id]
        self.assertEqual(obj[1], moon_1.name)

    def test_should_return_our_moons_only(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        moon = MoonFactory2()
        MoonFactory2()
        owner = OwnerFactory2(user=user)
        RefineryFactory2(owner=owner, moon=moon)
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.OURS)

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertSetEqual(_response_to_ids(response), {moon.id})

    def test_should_handle_empty_refineries(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        moon = MoonFactory2()
        MoonFactory2()
        owner = OwnerFactory2(user=user)
        RefineryFactory2(owner=owner, moon=moon)
        RefineryFactory2(owner=owner, moon=None)
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.OURS)

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertSetEqual(_response_to_ids(response), {moon.id})

    def test_should_return_uploaded_moons_only(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.upload_moon_scan"],
        )
        moon = MoonFactory2(products_updated_by=user)
        MoonFactory2()
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.UPLOADS)

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertSetEqual(_response_to_ids(response), {moon.id})


class TestMoonInfo(TestCase):
    def test_should_open_page(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.view_all_moons"],
        )
        moon = MoonFactory2()
        self.client.force_login(user)

        # when
        response = self.client.get(f"/moonmining/moon/{moon.pk}")

        # then
        self.assertTemplateUsed(response, "moonmining/modals/moon_details.html")
