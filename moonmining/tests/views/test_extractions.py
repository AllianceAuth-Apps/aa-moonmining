import datetime as dt
from http import HTTPStatus

from django.test import RequestFactory, TestCase
from django.utils.timezone import now
from eveuniverse.tests.testdata.factories_2 import EveEntityCharacterFactory

from app_utils.testdata_factories import UserMainFactory
from app_utils.testing import json_response_to_dict

import moonmining.views.extractions
from moonmining.models import Extraction, Owner
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    MiningLedgerRecordFactory,
    OwnerFactory,
    RefineryFactory,
)


class TestExtractionsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.owner = OwnerFactory()
        cls.refinery = RefineryFactory(owner=cls.owner)
        cls.started_by = EveEntityCharacterFactory()
        cls.extraction = ExtractionFactory(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=dt.timezone.utc),
            started_by_id=cls.started_by.id,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )

    def test_should_show_extraction_and_ledger_button(self):
        # given
        MiningLedgerRecordFactory(refinery=self.refinery, day=dt.date(2019, 11, 20))
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {self.extraction.pk})
        obj = data[self.extraction.pk]
        self.assertIn("2019-Nov-20 00:01", obj["chunk_arrival_at"]["display"])
        self.assertIn(self.owner.corporation.corporation_name, obj["corporation_name"])
        self.assertIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_extraction_when_user_has_no_permission(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
            ],
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_should_show_extraction_and_no_ledger_button_wo_specific_permission(self):
        # given
        MiningLedgerRecordFactory(refinery=self.refinery, day=dt.date(2019, 11, 20))
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_ledger_button_when_no_data(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
        )
        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])

    def test_ignore_refineries_without_moons(self):
        # given
        MiningLedgerRecordFactory(refinery=self.refinery, day=dt.date(2019, 11, 20))
        refinery_2 = RefineryFactory(moon=None, owner=self.refinery.owner)
        ExtractionFactory(
            refinery=refinery_2,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=dt.timezone.utc),
            started_by_id=self.started_by.id,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )
        MiningLedgerRecordFactory(refinery=refinery_2, day=dt.date(2019, 11, 20))
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
        )

        request = self.factory.get("/")
        request.user = user

        # when
        response = moonmining.views.extractions.extractions_data(
            request, moonmining.views.extractions.ExtractionsCategory.PAST
        )

        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {self.extraction.pk})


class TestExtractionLedgerData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.owner = OwnerFactory()
        cls.refinery = RefineryFactory(owner=cls.owner)
        cls.started_by = EveEntityCharacterFactory()
        cls.extraction = ExtractionFactory(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=dt.timezone.utc),
            started_by_id=cls.started_by.id,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )
        MiningLedgerRecordFactory(refinery=cls.refinery, day=dt.date(2021, 4, 18))

    def test_should_show_ledger_when_user_has_permission(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
        )
        self.client.force_login(user)

        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "moonmining/modals/extraction_ledger.html")

    def test_should_not_show_ledger_when_user_has_no_permission(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
            ],
        )
        self.client.force_login(user)

        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
