from http import HTTPStatus

from django.test import TestCase
from eveuniverse.tests.testdata.factories_2 import EveSolarSystemFactory

from app_utils.testdata_factories import UserMainFactory
from app_utils.testing import json_response_to_python

from moonmining.models import Owner
from moonmining.tests.testdata.factories_2 import (
    LabelFactory,
    MoonFactory2,
    OwnerFactory2,
    RefineryFactory2,
)
from moonmining.views import moons


class TestMoonsDataFdd(TestCase):
    def test_should_return_fdd_for_all_moons(self):
        # given
        solar_system_1 = EveSolarSystemFactory()
        solar_system_2 = EveSolarSystemFactory()
        moon_1 = MoonFactory2(eve_moon__eve_planet__eve_solar_system=solar_system_1)
        moon_1.rarity_class.name
        label = LabelFactory()
        moon_1.label = label
        moon_1.save()
        moon_2 = MoonFactory2(eve_moon__eve_planet__eve_solar_system=solar_system_1)
        moon_3 = MoonFactory2(eve_moon__eve_planet__eve_solar_system=solar_system_2)
        owner = OwnerFactory2()
        RefineryFactory2(owner=owner, moon=moon_3)
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
        print(path)
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
