import datetime as dt
from http import HTTPStatus
from unittest.mock import patch

from django.test import TestCase

from app_utils.testdata_factories import UserMainFactory
from app_utils.testing import json_response_to_dict, json_response_to_python

from moonmining.constants import EveGroupId
from moonmining.models import Owner
from moonmining.tests.testdata.factories_2 import (
    EveOreTypeFactory,
    MiningLedgerRecordFactory2,
    MoonFactory2,
    RefineryFactory2,
)

MODULE_PATH = "moonmining.views.reports"


class TestReportsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moon = MoonFactory2()
        cls.refinery = RefineryFactory2(moon=cls.moon)
        cls.user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.reports_access",
            ],
        )

    def test_should_return_owned_moon_values(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_owned_value_data")
        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # TODO: Test values

    def test_should_return_user_mining_data(self):
        # given
        today = dt.datetime(2021, 1, 15, 12, 0, tzinfo=dt.timezone.utc)
        months_1 = dt.datetime(2020, 12, 15, 12, 0, tzinfo=dt.timezone.utc)
        months_2 = dt.datetime(2020, 11, 15, 12, 0, tzinfo=dt.timezone.utc)
        months_3 = dt.datetime(2020, 10, 15, 12, 0, tzinfo=dt.timezone.utc)
        ore_1 = EveOreTypeFactory(create_price__average_price=10)
        ore_2 = EveOreTypeFactory(create_price__average_price=20)
        MiningLedgerRecordFactory2(
            refinery=self.refinery,
            day=today.date() - dt.timedelta(days=1),
            ore_type=ore_1,
            quantity=100,
            user=self.user,
        )
        MiningLedgerRecordFactory2(
            refinery=self.refinery,
            day=today.date() - dt.timedelta(days=2),
            ore_type=ore_2,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecordFactory2(
            refinery=self.refinery,
            day=months_1.date() - dt.timedelta(days=1),
            ore_type=ore_2,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecordFactory2(
            refinery=self.refinery,
            day=months_2.date() - dt.timedelta(days=1),
            ore_type=ore_2,
            quantity=500,
            user=self.user,
        )
        MiningLedgerRecordFactory2(
            refinery=self.refinery,
            day=months_3.date() - dt.timedelta(days=1),
            ore_type=ore_2,
            quantity=600,
            user=self.user,
        )
        self.client.force_login(self.user)

        # when
        with patch(MODULE_PATH + ".now") as mock_now:
            mock_now.return_value = today
            response = self.client.get("/moonmining/report_user_mining_data")

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        row = data[self.user.id]
        self.assertEqual(row["volume_month_0"], 100 * 10 + 200 * 10)
        self.assertEqual(row["price_month_0"], 10 * 100 + 20 * 200)
        self.assertEqual(row["volume_month_1"], 200 * 10)
        self.assertEqual(row["price_month_1"], 20 * 200)
        self.assertEqual(row["volume_month_2"], 500 * 10)
        self.assertEqual(row["price_month_2"], 20 * 500)
        self.assertEqual(row["volume_month_3"], 600 * 10)
        self.assertEqual(row["price_month_3"], 20 * 600)

    def test_should_return_user_uploads_data(self):
        # given
        MoonFactory2(products_updated_by=self.user)
        MoonFactory2(products_updated_by=self.user)
        self.client.force_login(self.user)

        # when
        response = self.client.get("/moonmining/report_user_uploaded_data")

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        user_data = [
            row
            for row in json_response_to_python(response)
            if row["name"] == self.user.profile.main_character.character_name
        ]
        self.assertEqual(user_data[0]["num_moons"], 2)


class TestReportsData_OrePrices(TestCase):
    def test_should_return_ore_prices(self):
        # given
        average_price = 2400.0
        group_name = "Rare Moon Asteroids"
        ore_name = "Cinnabar"
        oreType = EveOreTypeFactory(
            name=ore_name,
            create_price__average_price=average_price,
            eve_group__id=EveGroupId.RARE_MOON_ASTEROIDS,
            eve_group__name=group_name,
        )
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.reports_access",
            ],
        )
        self.client.force_login(user)

        # when
        response = self.client.get("/moonmining/report_ore_prices_data")

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        ore = data[oreType.id]
        self.assertEqual(ore["name"], ore_name)
        self.assertEqual(ore["price"], average_price)
        self.assertEqual(ore["group"], group_name)
        self.assertEqual(ore["rarity_str"], "R32")
