import datetime as dt
from unittest.mock import patch

import pytz

from django.test import TestCase
from eveuniverse.models import EveMarketPrice, EveMoon

from app_utils.testing import (
    create_user_from_evecharacter,
    json_response_to_dict,
    json_response_to_python,
)

from moonmining.models import EveOreType, Owner
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    MiningLedgerRecordFactory,
    MoonFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "moonmining.views.reports"


class TestReportsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        cls.refinery = RefineryFactory(moon=cls.moon)
        cls.user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.reports_access"],
            scopes=Owner.esi_scopes(),
        )
        MoonFactory(
            eve_moon=EveMoon.objects.get(id=40131695), products_updated_by=cls.user
        )
        MoonFactory(
            eve_moon=EveMoon.objects.get(id=40161709), products_updated_by=cls.user
        )

    def test_should_return_owned_moon_values(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_owned_value_data")
        # then
        self.assertEqual(response.status_code, 200)
        # TODO: Test values

    def test_should_return_user_mining_data(self):
        # given
        today = dt.datetime(2021, 1, 15, 12, 0, tzinfo=pytz.UTC)
        months_1 = dt.datetime(2020, 12, 15, 12, 0, tzinfo=pytz.UTC)
        months_2 = dt.datetime(2020, 11, 15, 12, 0, tzinfo=pytz.UTC)
        months_3 = dt.datetime(2020, 10, 15, 12, 0, tzinfo=pytz.UTC)
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        EveMarketPrice.objects.create(eve_type_id=45494, average_price=20)
        EveOreType.objects.update_current_prices(use_process_pricing=False)
        character = EveEntityCharacterFactory()
        corporation = EveEntityCorporationFactory()
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            day=today.date() - dt.timedelta(days=1),
            character=character,
            corporation=corporation,
            ore_type_id=45506,
            quantity=100,
            user=self.user,
        )
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            day=today.date() - dt.timedelta(days=2),
            character=character,
            corporation=corporation,
            ore_type_id=45494,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            day=months_1.date() - dt.timedelta(days=1),
            character=character,
            corporation=corporation,
            ore_type_id=45494,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            day=months_2.date() - dt.timedelta(days=1),
            character=character,
            corporation=corporation,
            ore_type_id=45494,
            quantity=500,
            user=self.user,
        )
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            day=months_3.date() - dt.timedelta(days=1),
            character=character,
            corporation=corporation,
            ore_type_id=45494,
            quantity=600,
            user=self.user,
        )
        self.client.force_login(self.user)
        # when
        with patch(MODULE_PATH + ".now") as mock_now:
            mock_now.return_value = today
            response = self.client.get("/moonmining/report_user_mining_data")
        # then
        self.assertEqual(response.status_code, 200)
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
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_user_uploaded_data")
        # then
        self.assertEqual(response.status_code, 200)
        user_data = [
            row
            for row in json_response_to_python(response)
            if row["name"] == self.user.profile.main_character.character_name
        ]
        self.assertEqual(user_data[0]["num_moons"], 2)

    def test_should_return_ore_prices(self):
        # given
        helpers.generate_market_prices()
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_ore_prices_data")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        ore = data[45506]
        self.assertEqual(ore["name"], "Cinnabar")
        self.assertEqual(ore["price"], 2400.0)
        self.assertEqual(ore["group"], "Rare Moon Asteroids")
        self.assertEqual(ore["rarity_str"], "R32")
