import datetime as dt
from unittest.mock import patch

import pytz

from django.utils.timezone import now
from esi.models import Token
from eveuniverse.models import EveMoon

from app_utils.testdata_factories import UserFactory
from app_utils.testing import NoSocketsTestCase

from moonmining.constants import EveTypeId
from moonmining.models import Extraction, NotificationType, Refinery
from moonmining.tests import helpers
from moonmining.tests.testdata.esi_client_stub import esi_client_stub
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    ExtractionProductFactory,
    MiningLedgerRecordFactory,
    MoonFactory,
    NotificationFactory2,
    OwnerFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import (
    load_eveuniverse,
    nearest_celestial_stub,
)

MODELS_PATH = "moonmining.models"


class TestOwner(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    def test_should_return_token(self):
        # given
        owner = OwnerFactory()
        # when
        result = owner.fetch_token()
        # then
        self.assertIsInstance(result, Token)

    def test_should_raise_error_when_no_character_ownership(self):
        # given
        owner = OwnerFactory.build(character_ownership=None)
        # when
        with self.assertRaises(RuntimeError):
            owner.fetch_token()

    def test_should_raise_error_when_no_token_found(self):
        # given
        owner = OwnerFactory()
        Token.objects.filter(user=owner.character_ownership.user).delete()
        # when
        with self.assertRaises(Token.DoesNotExist):
            owner.fetch_token()


@patch(MODELS_PATH + ".owners.esi")
class TestOwnerFetchNotifications(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_create_new_notifications_from_esi(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1005)
        owner = OwnerFactory(character_ownership=character_ownership)
        # when
        owner.fetch_notifications_from_esi()
        # then
        self.assertEqual(owner.notifications.count(), 5)
        obj = owner.notifications.get(notification_id=1005000101)
        self.assertEqual(obj.notif_type, NotificationType.MOONMINING_EXTRACTION_STARTED)
        self.assertEqual(obj.sender_id, 2101)
        self.assertEqual(
            obj.timestamp, dt.datetime(2019, 11, 22, 1, 0, tzinfo=pytz.UTC)
        )
        self.assertEqual(obj.details["moonID"], 40161708)
        self.assertEqual(obj.details["structureID"], 1000000000001)


@patch(MODELS_PATH + ".owners.esi")
@patch(MODELS_PATH + ".owners.notify_admins_throttled", lambda *args, **kwargs: None)
class TestOwnerUpdateRefineries(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.owner = OwnerFactory()

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    def test_should_create_new_refineries_from_scratch(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        my_eve_moon = EveMoon.objects.get(id=40161708)
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1000000000001, 1000000000002})
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    @patch(MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial")
    def test_should_handle_OSError_exceptions_from_nearest_celestial(
        self, mock_nearest_celestial, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        mock_nearest_celestial.side_effect = OSError
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1000000000001, 1000000000002})
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertIsNone(refinery.moon)
        self.assertEqual(mock_nearest_celestial.call_count, 2)

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    def test_should_remove_refineries_that_no_longer_exist(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        RefineryFactory(id=1990000000001, owner=self.owner)
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1000000000001, 1000000000002})

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    def test_should_not_remove_refineries_after_OSError_in_corporation_structures(
        self, mock_esi
    ):
        # given
        mock_esi.client.Corporation.get_corporations_corporation_id_structures.side_effect = (
            OSError
        )
        RefineryFactory(id=1990000000001, owner=self.owner)
        # when
        with self.assertRaises(OSError):
            self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1990000000001})

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    def test_should_continue_with_other_refineries_after_OS_error(self, mock_esi):
        def my_get_corporations_corporation_id_structures(*args, **kwargs):
            """Pass through"""
            return (
                esi_client_stub.Corporation.get_corporations_corporation_id_structures(
                    *args, **kwargs
                )
            )

        def my_get_universe_structures_structure_id(*args, **kwargs):
            """Return OS error for specific structure only."""
            if "structure_id" in kwargs and kwargs["structure_id"] == 1000000000001:
                raise OSError
            return esi_client_stub.Universe.get_universe_structures_structure_id(
                *args, **kwargs
            )

        # given
        mock_esi.client.Corporation.get_corporations_corporation_id_structures = (
            my_get_corporations_corporation_id_structures
        )
        mock_esi.client.Universe.get_universe_structures_structure_id = (
            my_get_universe_structures_structure_id
        )
        RefineryFactory(id=1000000000001, owner=self.owner)
        RefineryFactory(id=1000000000002, owner=self.owner)
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1000000000001, 1000000000002})


@patch(MODELS_PATH + ".owners.esi")
class TestOwnerUpdateExtractions(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_create_started_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        # when
        owner.update_extractions()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(
            extraction.chunk_arrival_at,
            dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.started_by_id, 1001)
        self.assertEqual(extraction.products.count(), 4)
        product = extraction.products.get(ore_type_id=45506)
        self.assertEqual(product.volume, 1288475.124715103)
        product = extraction.products.get(ore_type_id=46676)
        self.assertEqual(product.volume, 544691.7637724016)
        product = extraction.products.get(ore_type_id=22)
        self.assertEqual(product.volume, 526825.4047522942)
        product = extraction.products.get(ore_type_id=46689)
        self.assertEqual(product.volume, 528996.6386983792)
        self.assertIsNotNone(extraction.value)
        self.assertIsNotNone(extraction.is_jackpot)


@patch(MODELS_PATH + ".owners.esi")
class TestOwnerUpdateExtractionsFromEsi(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.owner = OwnerFactory()

    def test_should_create_started_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        refinery = RefineryFactory(id=1000000000001, owner=self.owner)
        # when
        with patch(MODELS_PATH + ".owners.now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 4, 5, 12, 0, 0, tzinfo=pytz.UTC)
            self.owner.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(
            extraction.chunk_arrival_at,
            dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
        )
        self.assertEqual(
            extraction.started_at, dt.datetime(2021, 4, 1, 12, 00, tzinfo=pytz.UTC)
        )
        self.assertEqual(
            extraction.auto_fracture_at,
            dt.datetime(2021, 4, 15, 21, 00, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.products.count(), 0)
        self.assertIsNone(extraction.value)
        self.assertIsNone(extraction.is_jackpot)

    def test_should_create_completed_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        refinery = RefineryFactory(id=1000000000001, owner=self.owner)
        # when
        with patch(MODELS_PATH + ".owners.now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 4, 18, 18, 15, 0, tzinfo=pytz.UTC)
            self.owner.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)

    def test_should_identify_canceled_extractions(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        refinery = RefineryFactory(id=1000000000001, owner=self.owner)
        started_extraction = ExtractionFactory(
            refinery=refinery,
            started_at=dt.datetime(2021, 3, 10, 18, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 3, 15, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 3, 15, 21, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        # when
        with patch(MODELS_PATH + ".owners.now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 4, 1, 12, 0, tzinfo=pytz.UTC)
            self.owner.update_extractions_from_esi()
        # then
        started_extraction.refresh_from_db()
        self.assertEqual(started_extraction.status, Extraction.Status.CANCELED)
        self.assertTrue(started_extraction.canceled_at)


@patch(MODELS_PATH + ".owners.esi")
class TestOwnerUpdateExtractionsFromNotifications(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_update_started_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.STARTED
        )
        calc_extraction = extraction.to_calculated_extraction()
        NotificationFactory2(
            extraction=calc_extraction, owner=owner, create_products=True
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME},
        )

    def test_should_create_canceled_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000002, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
            create_products=False,
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.CANCELED)
        self.assertEqual(
            extraction.canceled_at,
            dt.datetime(2019, 11, 22, 2, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.canceled_by_id, 1001)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {45506, 46676, 22, 46689},
        )

    def test_should_create_finished_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000003, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
            create_products=False,
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProductFactory(extraction=extraction, ore_type_id=22, volume=526825)
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.READY)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )

    def test_should_create_manually_fractured_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000004, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
            create_products=False,
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProductFactory(extraction=extraction, ore_type_id=22, volume=526825)
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        self.assertEqual(extraction.fractured_by_id, 1001)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )

    def test_should_create_auto_fractured_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000005, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
            create_products=False,
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProductFactory(extraction=extraction, ore_type_id=22, volume=526825)
        ExtractionProductFactory(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        self.assertIsNone(extraction.fractured_by)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678},
        )

    def test_should_create_manually_fractured_extraction_with_products_2(
        self, mock_esi
    ):
        """notification chain starting with 'finished' and missing 'started'"""
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000006, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 00, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        self.assertEqual(extraction.fractured_by_id, 1001)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )

    def test_should_cancel_existing_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1002)
        owner = OwnerFactory(character_ownership=character_ownership)
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
            create_products=False,
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.CANCELED)

    def test_should_cancel_existing_and_update_two_other(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1004)
        owner = OwnerFactory(character_ownership=character_ownership)
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        ready_time_1 = dt.datetime(2019, 11, 21, 10, tzinfo=pytz.UTC)
        ready_time_2 = dt.datetime(2019, 11, 21, 11, tzinfo=pytz.UTC)
        ready_time_3 = dt.datetime(2019, 11, 21, 12, tzinfo=pytz.UTC)
        extraction_1 = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=ready_time_1,
            started_at=ready_time_1 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_1 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_2 = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=ready_time_2,
            started_at=ready_time_2 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_2 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        ExtractionProductFactory(
            extraction=extraction_2, ore_type_id=45506, volume=1288475
        )
        ExtractionProductFactory(
            extraction=extraction_2, ore_type_id=46676, volume=544691
        )
        ExtractionProductFactory(extraction=extraction_2, ore_type_id=22, volume=526825)
        ExtractionProductFactory(
            extraction=extraction_2, ore_type_id=46689, volume=528996
        )
        extraction_3 = ExtractionFactory(
            refinery=refinery,
            chunk_arrival_at=ready_time_3,
            started_at=ready_time_3 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_3 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 3)
        extraction_1.refresh_from_db()
        self.assertEqual(extraction_1.status, Extraction.Status.CANCELED)
        extraction_2.refresh_from_db()
        self.assertEqual(extraction_2.status, Extraction.Status.COMPLETED)
        self.assertEqual(
            set(extraction_2.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )
        extraction_3.refresh_from_db()
        self.assertEqual(extraction_3.status, Extraction.Status.STARTED)
        self.assertEqual(
            set(extraction_3.products.values_list("ore_type_id", flat=True)),
            {45506, 46676, 22, 46689},
        )

    def test_should_update_refinery_with_moon_from_notification_if_not_found(
        self, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        owner.fetch_notifications_from_esi()
        refinery = RefineryFactory(id=1000000000001, moon=None, owner=owner)
        # when
        owner.update_extractions()
        # then
        refinery.refresh_from_db()
        self.assertEqual(refinery.moon.pk, 40161708)

    def test_should_update_moon_products_when_no_survey_exists(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        moon = MoonFactory()
        moon.products.first().delete()
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner, moon=moon)
        extraction = ExtractionFactory(
            refinery=refinery, status=Extraction.Status.STARTED
        )
        calc_extraction = extraction.to_calculated_extraction()
        NotificationFactory2(
            extraction=calc_extraction, owner=owner, create_products=True
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(moon.products.count(), 3)

    @patch(MODELS_PATH + ".owners.MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", False)
    def test_should_not_update_moon_products_when_survey_exists(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        moon = MoonFactory(products_updated_by=UserFactory())
        moon.products.first().delete()
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner, moon=moon)
        extraction = ExtractionFactory(
            refinery=refinery, status=Extraction.Status.STARTED
        )
        calc_extraction = extraction.to_calculated_extraction()
        NotificationFactory2(
            extraction=calc_extraction, owner=owner, create_products=True
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(moon.products.count(), 2)

    @patch(MODELS_PATH + ".owners.MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", True)
    def test_should_update_moon_products_when_survey_exists_alternate(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        moon = MoonFactory(products_updated_by=UserFactory())
        moon.products.first().delete()
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner, moon=moon)
        extraction = ExtractionFactory(
            refinery=refinery, status=Extraction.Status.STARTED
        )
        calc_extraction = extraction.to_calculated_extraction()
        NotificationFactory2(
            extraction=calc_extraction, owner=owner, create_products=True
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(moon.products.count(), 3)


@patch(MODELS_PATH + ".owners.esi")
class TestOwnerUpdateMiningLedger(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_return_observer_ids_from_esi(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        # when
        result = owner.fetch_mining_ledger_observers_from_esi()
        # then
        self.assertSetEqual(result, {1000000000001, 1000000000002})

    def test_should_create_new_mining_ledger(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        # when
        refinery.update_mining_ledger_from_esi()
        # then
        refinery.refresh_from_db()
        self.assertTrue(refinery.ledger_last_update_ok)
        self.assertAlmostEqual(
            refinery.ledger_last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
        self.assertEqual(refinery.mining_ledger.count(), 2)
        obj = refinery.mining_ledger.get(character_id=1001)
        self.assertEqual(obj.day, dt.date(2017, 9, 19))
        self.assertEqual(obj.quantity, 500)
        self.assertEqual(obj.corporation_id, 2001)
        self.assertEqual(obj.ore_type_id, 45506)

    def test_should_update_existing_mining_ledger(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        MiningLedgerRecordFactory(
            refinery=refinery,
            day=dt.date(2017, 9, 19),
            character_id=1001,
            ore_type_id=EveTypeId.CINNABAR,
            quantity=199,
        )
        # when
        refinery.update_mining_ledger_from_esi()
        # then
        self.assertEqual(refinery.mining_ledger.count(), 2)
        obj = refinery.mining_ledger.get(character_id=1001)
        self.assertEqual(obj.quantity, 500)

    def test_should_mark_when_update_failed(self, mock_esi):
        # given
        mock_esi.client.Industry.get_corporation_corporation_id_mining_observers_observer_id.side_effect = (
            OSError
        )
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        # when
        with self.assertRaises(OSError):
            refinery.update_mining_ledger_from_esi()
        # then
        refinery.refresh_from_db()
        self.assertFalse(refinery.ledger_last_update_ok)
        self.assertAlmostEqual(
            refinery.ledger_last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
