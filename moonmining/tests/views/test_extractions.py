import datetime as dt

import pytz

from django.test import RequestFactory, TestCase
from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice, EveMoon

from app_utils.testing import create_user_from_evecharacter, json_response_to_dict

import moonmining.views.extractions
from moonmining.models import Extraction, Owner
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    MiningLedgerRecordFactory,
    MoonFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse


class TestExtractionsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        moon = MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        cls.refinery = RefineryFactory(moon=moon)
        cls.extraction = ExtractionFactory(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        cls.user_1003, _ = create_user_from_evecharacter(1003)

    def test_should_show_extraction(self):
        # given
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            corporation_id=2001,
            user=self.user_1003,
        )
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {self.extraction.pk})
        obj = data[self.extraction.pk]
        self.assertIn("2019-Nov-20 00:01", obj["chunk_arrival_at"]["display"])
        self.assertEqual(obj["corporation_name"], "Wayne Technologies [WYN]")
        self.assertIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_extraction(self):
        # given
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )
        self.assertEqual(response.status_code, 302)

    def test_should_not_show_ledger_button_wo_permission(self):
        # given
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            corporation_id=2001,
            user=self.user_1003,
        )
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_ledger_button_when_no_data(self):
        # given
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])

    def test_ignore_refineries_without_moons(self):
        # given
        MiningLedgerRecordFactory(
            refinery=self.refinery,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            corporation_id=2001,
            user=self.user_1003,
        )
        refinery_2 = RefineryFactory(moon=None, owner=self.refinery.owner)
        ExtractionFactory(
            refinery=refinery_2,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )
        MiningLedgerRecordFactory(
            refinery=refinery_2,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            corporation_id=2001,
            user=self.user_1003,
        )
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {self.extraction.pk})


class TestExtractionLedgerData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        moon = MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        cls.refinery = RefineryFactory(moon=moon)
        cls.extraction = ExtractionFactory(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        user_1003, _ = create_user_from_evecharacter(
            1003,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        MiningLedgerRecordFactory(
            refinery=cls.refinery,
            character_id=1001,
            day=dt.date(2021, 4, 18),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=100,
            user=user_1003,
        )

    def test_should_show_ledger(self):
        # given
        user_1002, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user_1002)
        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertTemplateUsed(response, "moonmining/modals/extraction_ledger.html")

    def test_should_not_show_ledger(self):
        # given
        user_1002, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user_1002)
        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertEqual(response.status_code, 302)
