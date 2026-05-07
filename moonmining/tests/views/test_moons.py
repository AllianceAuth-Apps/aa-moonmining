from http import HTTPStatus
from typing import Set

from django.test import RequestFactory, TestCase
from eveuniverse.tests.testdata.factories_2 import EveSolarSystemFactory

from app_utils.testdata_factories import UserMainFactory
from app_utils.testing import json_response_to_python

from moonmining.models import Owner
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    LabelFactory,
    MoonFactory,
    OwnerFactory,
    RefineryFactory,
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
        moon_1 = MoonFactory()
        moon_2 = MoonFactory()
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
        moon = MoonFactory()
        MoonFactory()
        owner = OwnerFactory(user=user)
        RefineryFactory(owner=owner, moon=moon)
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
        moon = MoonFactory()
        MoonFactory()
        owner = OwnerFactory(user=user)
        RefineryFactory(owner=owner, moon=moon)
        RefineryFactory(owner=owner, moon=None)
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
        moon = MoonFactory(products_updated_by=user)
        MoonFactory()
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
        moon = MoonFactory()
        self.client.force_login(user)

        # when
        response = self.client.get(f"/moonmining/moon/{moon.pk}")

        # then
        self.assertTemplateUsed(response, "moonmining/modals/moon_details.html")


class TestMoonsDataFdd(TestCase):
    def test_should_return_fdd_for_all_moons(self):
        # given
        solar_system_1 = EveSolarSystemFactory()
        solar_system_2 = EveSolarSystemFactory()
        moon_1 = MoonFactory(eve_moon__eve_planet__eve_solar_system=solar_system_1)
        moon_1.rarity_class.name
        label = LabelFactory()
        moon_1.label = label
        moon_1.save()
        moon_2 = MoonFactory(eve_moon__eve_planet__eve_solar_system=solar_system_1)
        moon_3 = MoonFactory(eve_moon__eve_planet__eve_solar_system=solar_system_2)
        owner = OwnerFactory()
        RefineryFactory(owner=owner, moon=moon_3)
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.view_all_moons",
            ],
        )
        self.client.force_login(user)

        # when
        path = (
            f"/moonmining/moons_fdd_data/{moons.MoonsCategory.ALL.value}"
            "?columns=alliance_name,corporation_name,region_name,"
            "constellation_name,solar_system_name,rarity_class_str,label_name,"
            "has_refinery_str,has_extraction_str,invalid_column"
        )
        response = self.client.get(path)

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_python(response)
        self.assertSetEqual(
            set(data["solar_system_name"]), {solar_system_1.name, solar_system_2.name}
        )

        self.assertListEqual(
            data["alliance_name"], [owner.corporation.alliance.alliance_name]
        )
        self.assertListEqual(
            data["corporation_name"], [owner.corporation.corporation_name]
        )
        self.assertSetEqual(
            set(data["region_name"]),
            {
                solar_system_1.eve_constellation.eve_region.name,
                solar_system_2.eve_constellation.eve_region.name,
            },
        )
        self.assertSetEqual(
            set(data["constellation_name"]),
            {
                solar_system_1.eve_constellation.name,
                solar_system_2.eve_constellation.name,
            },
        )
        self.assertListEqual(data["label_name"], [label.name])
        self.assertSetEqual(
            set(data["rarity_class_str"]),
            {
                moon_1.rarity_class.name,
                moon_2.rarity_class.name,
                moon_3.rarity_class.name,
            },
        )
        self.assertListEqual(data["has_refinery_str"], ["no", "yes"])
        self.assertListEqual(data["has_extraction_str"], [])
        self.assertIn("ERROR", data["invalid_column"][0])
