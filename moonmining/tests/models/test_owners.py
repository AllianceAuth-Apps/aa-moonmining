import datetime as dt
from typing import NamedTuple
from unittest.mock import Mock, patch

import pook
import yaml

from django.db.models import QuerySet
from django.utils.timezone import now
from esi.models import Token
from eveuniverse.tests.testdata.factories_2 import EveMoonFactory

from app_utils.testdata_factories import UserFactory
from app_utils.testing import NoSocketsTestCase, queryset_pks

from moonmining.core import CalculatedExtraction
from moonmining.models import (
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Notification,
    NotificationType,
    Owner,
    Refinery,
)
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    CalculatedExtractionFactory,
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    ExtractionFactory,
    MiningLedgerRecordFactory,
    MoonAsteroidsTypeFactory,
    MoonFactory,
    MoonNotificationFactory,
    NotificationFactory2,
    OwnerFactory,
    RefineryFactory,
    make_esi_url,
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
        owner: Owner = OwnerFactory.build(character_ownership=None)
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


class TestOwnerFetchNotifications(helpers.TestCaseWithClearCache):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    @pook.on
    def test_should_create_new_notifications_from_esi(self):
        # given
        character_id = 1005
        sender_id = 2101
        timestamp = dt.datetime(2019, 11, 22, 1, 0, tzinfo=dt.timezone.utc)
        moon_id = 40161465
        structure_id = 1000000000001
        notification_id = 1005000101
        pook.get(
            make_esi_url(f"characters/{character_id}/notifications"),
            reply=200,
            response_json=[
                {
                    "notification_id": notification_id,
                    "type": "MoonminingExtractionStarted",
                    "sender_id": sender_id,
                    "sender_type": "corporation",
                    "timestamp": timestamp.isoformat(),
                    "text": yaml.dump(
                        {
                            "autoTime": 132186924601059151,
                            "moonID": moon_id,
                            "oreVolumeByType": {
                                46300: 1288475.124715103,
                                46301: 544691.7637724016,
                                46302: 526825.4047522942,
                                46303: 528996.6386983792,
                            },
                            "readyTime": 132186816601059151,
                            "solarSystemID": 30002537,
                            "startedBy": 1001,
                            "startedByLink": '<a href="showinfo:1383//1001">Bruce Wayne</a>',
                            "structureID": structure_id,
                            "structureLink": f'<a href="showinfo:35835//{structure_id}">Dummy</a>',
                            "structureName": "Dummy",
                            "structureTypeID": 35835,
                        }
                    ),
                    "is_read": False,
                },
            ],
        )
        _, character_ownership = helpers.create_default_user_from_evecharacter(
            character_id
        )
        owner = OwnerFactory(character_ownership=character_ownership)

        # when
        owner.fetch_notifications_from_esi()

        # then
        self.assertEqual(owner.notifications.count(), 1)
        obj: Notification = owner.notifications.get(notification_id=notification_id)
        self.assertEqual(obj.notif_type, NotificationType.MOONMINING_EXTRACTION_STARTED)
        self.assertEqual(obj.sender.id, sender_id)
        self.assertEqual(obj.timestamp, timestamp)
        self.assertEqual(obj.details["moonID"], moon_id)
        self.assertEqual(obj.details["structureID"], structure_id)


@patch(MODELS_PATH + ".owners.notify_admins_throttled", lambda *args, **kwargs: None)
class TestOwnerUpdateRefineries(helpers.TestCaseWithClearCache):
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
    @pook.on
    def test_should_create_new_refineries_from_scratch(self):
        # given
        corporation_id = self.owner.corporation.corporation_id
        structure_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        solar_system_id = 30002542
        type_id = 35835
        moon_id = 40161708
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "corporation_id": corporation_id,
                    "profile_id": 52436,
                    "reinforce_hour": 19,
                    "services": [
                        {"name": "Reprocessing", "state": "online"},
                        {"name": "Moon Drilling", "state": "online"},
                    ],
                    "state": "shield_vulnerable",
                    "structure_id": structure_id,
                    "system_id": solar_system_id,
                    "type_id": type_id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_name,
                "position": {
                    "x": 55028384780.0,
                    "y": 7310316270.0,
                    "z": -163686684205.0,
                },
                "solar_system_id": solar_system_id,
                "type_id": type_id,
            },
        )

        # when
        self.owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})
        refinery = Refinery.objects.get(id=structure_id)
        self.assertEqual(refinery.name, structure_name)
        self.assertEqual(refinery.moon.eve_moon.id, moon_id)

    @patch(MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial")
    @pook.on
    def test_should_handle_exception_from_nearest_celestial(
        self, mock_nearest_celestial: Mock
    ):
        # given
        mock_nearest_celestial.side_effect = OSError
        corporation_id = self.owner.corporation.corporation_id
        structure_id = 1000000000001
        solar_system_id = 30002542
        type_id = 35835
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "corporation_id": corporation_id,
                    "profile_id": 52436,
                    "reinforce_hour": 19,
                    "services": [
                        {"name": "Reprocessing", "state": "online"},
                        {"name": "Moon Drilling", "state": "online"},
                    ],
                    "state": "shield_vulnerable",
                    "structure_id": structure_id,
                    "system_id": solar_system_id,
                    "type_id": type_id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": "Auga - Paradise Alpha",
                "position": {
                    "x": 55028384780.0,
                    "y": 7310316270.0,
                    "z": -163686684205.0,
                },
                "solar_system_id": solar_system_id,
                "type_id": type_id,
            },
        )

        # when
        self.owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})
        refinery = Refinery.objects.get(id=structure_id)
        self.assertIsNone(refinery.moon)
        self.assertEqual(mock_nearest_celestial.call_count, 1)

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    @pook.on
    def test_should_remove_refineries_that_no_longer_exist(self):
        # given
        RefineryFactory(id=1990000000001, owner=self.owner)
        corporation_id = self.owner.corporation.corporation_id
        structure_id = 1000000000001
        solar_system_id = 30002542
        type_id = 35835
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "corporation_id": corporation_id,
                    "profile_id": 52436,
                    "reinforce_hour": 19,
                    "services": [
                        {"name": "Reprocessing", "state": "online"},
                        {"name": "Moon Drilling", "state": "online"},
                    ],
                    "state": "shield_vulnerable",
                    "structure_id": structure_id,
                    "system_id": solar_system_id,
                    "type_id": type_id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": "Auga - Paradise Alpha",
                "position": {
                    "x": 55028384780.0,
                    "y": 7310316270.0,
                    "z": -163686684205.0,
                },
                "solar_system_id": solar_system_id,
                "type_id": type_id,
            },
        )

        # when
        self.owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    @pook.on
    def test_should_not_remove_refineries_after_http_error_in_corporation_structures(
        self,
    ):
        # given
        RefineryFactory(id=1990000000001, owner=self.owner)
        corporation_id = self.owner.corporation.corporation_id
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=500,
            response_json={"error": "some error"},
        )

        # when
        with self.assertRaises(OSError):
            self.owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {1990000000001})

    @patch(
        MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial",
        new=nearest_celestial_stub,
    )
    @pook.on
    def test_should_continue_with_other_refineries_after_http_error(self):
        structure_1 = RefineryFactory(id=1000000000001, owner=self.owner)
        structure_2 = RefineryFactory(id=1000000000002, owner=self.owner)
        corporation_id = self.owner.corporation.corporation_id
        solar_system_id = 30002542
        type_id = 35835
        structure_2_name = "Auga - Paradise Alpha"
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "corporation_id": corporation_id,
                    "profile_id": 52436,
                    "reinforce_hour": 19,
                    "services": [
                        {"name": "Reprocessing", "state": "online"},
                        {"name": "Moon Drilling", "state": "online"},
                    ],
                    "state": "shield_vulnerable",
                    "structure_id": structure_1.id,
                    "system_id": solar_system_id,
                    "type_id": type_id,
                },
                {
                    "corporation_id": corporation_id,
                    "profile_id": 52436,
                    "reinforce_hour": 19,
                    "services": [
                        {"name": "Reprocessing", "state": "online"},
                        {"name": "Moon Drilling", "state": "online"},
                    ],
                    "state": "shield_vulnerable",
                    "structure_id": structure_2.id,
                    "system_id": solar_system_id,
                    "type_id": type_id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_1.id}"),
            reply=500,
            response_json={"error": "some error"},
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_2.id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_2_name,
                "position": {
                    "x": 55028384780.0,
                    "y": 7310316270.0,
                    "z": -163686684205.0,
                },
                "solar_system_id": solar_system_id,
                "type_id": type_id,
            },
        )
        # when
        self.owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(
            queryset_pks(Refinery.objects.all()), {structure_1.id, structure_2.id}
        )
        structure_2.refresh_from_db()
        self.assertEqual(structure_2.name, structure_2_name)


class TestOwnerUpdateExtractions(helpers.TestCaseWithClearCache):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    @pook.on
    def test_should_create_started_extraction_with_products(self):
        # given
        refinery_id = 1000000000001
        chunk_arrival_at = dt.datetime(2021, 4, 15, 18, 0, tzinfo=dt.timezone.utc)

        owner = OwnerFactory()
        refinery = RefineryFactory(id=refinery_id, owner=owner)
        moon_id = refinery.moon.eve_moon.id
        started_by = EveEntityCharacterFactory()
        calculated_extraction = CalculatedExtractionFactory(
            status=CalculatedExtraction.Status.STARTED,
            chunk_arrival_at=chunk_arrival_at,
            started_by=started_by.id,
            refinery_id=refinery_id,
        )
        NotificationFactory2(
            extraction=calculated_extraction,
            structure_name=refinery.name,
            moon_id=moon_id,
            owner=owner,
        )

        pook.get(
            make_esi_url(
                f"corporation/{owner.corporation.corporation_id}/mining/extractions"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "chunk_arrival_time": chunk_arrival_at.isoformat(),
                    "extraction_start_time": "2021-04-01T12:00:00Z",
                    "moon_id": moon_id,
                    "natural_decay_time": "2021-04-15T21:00:00Z",
                    "structure_id": refinery_id,
                },
            ],
        )

        # when
        owner.update_extractions()

        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction: Extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(extraction.chunk_arrival_at, chunk_arrival_at)
        self.assertEqual(extraction.started_by, started_by)
        self.assertEqual(
            extraction.products.count(), len(calculated_extraction.products)
        )
        products_want = {
            x.ore_type_id: x.volume for x in calculated_extraction.products
        }
        products_got = {
            x["ore_type_id"]: x["volume"] for x in extraction.products.values()
        }
        self.assertDictEqual(products_got, products_want)
        self.assertIsNotNone(extraction.value)


class TestOwnerUpdateExtractionsFromEsi(helpers.TestCaseWithClearCache):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    @pook.on
    def test_should_create_started_extraction(self):
        class Case(NamedTuple):
            name: str
            started_at: dt.datetime
            chunk_arrival_at: dt.datetime
            auto_fracture_at: dt.datetime
            want: Extraction.Status

        cases = [
            Case(
                name="started",
                started_at=now() - dt.timedelta(hours=1),
                chunk_arrival_at=now() + dt.timedelta(days=3),
                auto_fracture_at=now() + dt.timedelta(days=3, hours=2),
                want=Extraction.Status.STARTED,
            ),
            Case(
                name="ready",
                started_at=now() - dt.timedelta(days=3),
                chunk_arrival_at=now() - dt.timedelta(hours=1),
                auto_fracture_at=now() + dt.timedelta(hours=1),
                want=Extraction.Status.READY,
            ),
            Case(
                name="completed",
                started_at=now() - dt.timedelta(days=3),
                chunk_arrival_at=now() - dt.timedelta(hours=6),
                auto_fracture_at=now() - dt.timedelta(hours=1),
                want=Extraction.Status.COMPLETED,
            ),
        ]
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        moon_id = refinery.moon.eve_moon.id

        for tc in cases:
            with self.subTest(name=tc.name):
                # given
                refinery.extractions.all().delete()
                pook.get(
                    make_esi_url(
                        f"corporation/{owner.corporation.corporation_id}/mining/extractions"
                    ),
                    reply=200,
                    response_headers={"X-Pages": "1"},
                    response_json=[
                        {
                            "chunk_arrival_time": tc.chunk_arrival_at.isoformat(),
                            "extraction_start_time": tc.started_at.isoformat(),
                            "moon_id": moon_id,
                            "natural_decay_time": tc.auto_fracture_at.isoformat(),
                            "structure_id": refinery.id,
                        },
                    ],
                )

                # when
                owner.update_extractions_from_esi()

                # then
                self.assertEqual(refinery.extractions.count(), 1)
                extraction: Extraction = refinery.extractions.first()
                self.assertEqual(extraction.status_2, tc.want)
                self.assertEqual(extraction.auto_fracture_at, tc.auto_fracture_at)
                self.assertEqual(extraction.chunk_arrival_at, tc.chunk_arrival_at)
                self.assertEqual(extraction.started_at, tc.started_at)

    @pook.on
    def test_should_identify_canceled_extractions_1(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        started_extraction = ExtractionFactory(
            refinery=refinery,
            started_at=now() - dt.timedelta(hours=2),
            chunk_arrival_at=now() + dt.timedelta(days=4),
            auto_fracture_at=now() + dt.timedelta(days=4, hours=2),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        pook.get(
            make_esi_url(
                f"corporation/{owner.corporation.corporation_id}/mining/extractions"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[],
        )
        # when
        owner.update_extractions_from_esi()

        # then
        started_extraction.refresh_from_db()
        self.assertEqual(started_extraction.status_2, Extraction.Status.CANCELED)
        self.assertTrue(started_extraction.canceled_at)

    @pook.on
    def test_should_identify_canceled_extractions_2(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, owner=owner)
        moon_id = refinery.moon.eve_moon.id
        started_extraction = ExtractionFactory(
            refinery=refinery,
            started_at=now() - dt.timedelta(hours=2),
            chunk_arrival_at=now() + dt.timedelta(days=4),
            auto_fracture_at=now() + dt.timedelta(days=4, hours=2),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        pook.get(
            make_esi_url(
                f"corporation/{owner.corporation.corporation_id}/mining/extractions"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "chunk_arrival_time": (now() + dt.timedelta(days=4)).isoformat(),
                    "extraction_start_time": (
                        now() - dt.timedelta(hours=1)
                    ).isoformat(),
                    "moon_id": moon_id,
                    "natural_decay_time": (
                        now() + dt.timedelta(days=4, hours=2)
                    ).isoformat(),
                    "structure_id": refinery.id,
                },
            ],
        )
        # when
        owner.update_extractions_from_esi()

        # then
        started_extraction.refresh_from_db()
        self.assertEqual(started_extraction.status_2, Extraction.Status.CANCELED)
        self.assertTrue(started_extraction.canceled_at)


class TestOwnerUpdateExtractionsFromNotifications(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_update_started_extraction(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.STARTED
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertEqual(extraction.started_by.id, notif.details["startedBy"])

    def test_should_cancel_extraction_and_update_products(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.STARTED
        )
        notif_started = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        notif_canceled = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_CANCELLED,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.CANCELED)
        self.assertEqual(
            extraction.canceled_by.id, notif_canceled.details["cancelledBy"]
        )
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif_started.details["oreVolumeByType"])

    def test_should_update_ready_extraction(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.READY
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_FINISHED,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.READY)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])

    def test_should_update_completed_extraction_when_laser_fired(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.COMPLETED
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_FINISHED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_LASER_FIRED,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertEqual(extraction.fractured_by.id, notif.details["firedBy"])

    def test_should_update_completed_extraction_when_auto_fracture(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.COMPLETED
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_FINISHED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_AUTOMATIC_FRACTURE,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertIsNone(extraction.fractured_by)

    def test_should_cancel_extraction_and_update_another(self):
        # given
        owner = OwnerFactory()
        refinery_1 = RefineryFactory(owner=owner)
        extraction_1 = ExtractionFactory(
            refinery=refinery_1, create_products=False, status=Extraction.Status.STARTED
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction_1.auto_fracture_at,
            chunk_arrival_at=extraction_1.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery_1,
            started_at=extraction_1.started_at,
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction_1.auto_fracture_at,
            chunk_arrival_at=extraction_1.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_CANCELLED,
            refinery=refinery_1,
            started_at=extraction_1.started_at,
        )
        refinery_2 = RefineryFactory(owner=owner)
        extraction_2 = ExtractionFactory(
            refinery=refinery_2, create_products=False, status=Extraction.Status.STARTED
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction_2.auto_fracture_at,
            chunk_arrival_at=extraction_2.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery_2,
            started_at=extraction_2.started_at,
        )

        # when
        owner.update_extractions_from_notifications()

        # then
        extraction_1.refresh_from_db()
        self.assertEqual(extraction_1.status, Extraction.Status.CANCELED)
        extraction_2.refresh_from_db()
        self.assertEqual(extraction_2.started_by.id, notif.details["startedBy"])

    def test_should_update_refinery_with_moon_from_notification_when_not_set(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(id=1000000000001, moon=None, owner=owner)
        em = EveMoonFactory()
        MoonNotificationFactory(refinery=refinery, eve_moon=em)

        # when
        owner.update_extractions_from_notifications()

        # then
        refinery.refresh_from_db()
        self.assertEqual(refinery.moon.eve_moon, em)

    def test_should_update_moon_products_when_no_survey_exists(self):
        # given
        moon = MoonFactory()
        moon.products.first().delete()
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner, moon=moon)
        extraction = ExtractionFactory(
            refinery=refinery, create_products=False, status=Extraction.Status.STARTED
        )
        MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )
        # when
        owner.update_extractions_from_notifications()

        # then
        self.assertEqual(moon.products.count(), 3)

    @patch(MODELS_PATH + ".owners.MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", False)
    def test_should_not_update_moon_products_when_survey_exists(self):
        # given
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
    def test_should_update_moon_products_when_survey_exists_alternate(self):
        # given

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


class TestOwnerUpdateMiningLedger(helpers.TestCaseWithClearCache):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    @pook.on
    def test_should_return_observer_ids_from_esi(self):
        # given
        owner = OwnerFactory()
        corporation_id = owner.corporation.corporation_id
        observer_id = 1000000000001
        pook.get(
            make_esi_url(f"corporation/{corporation_id}/mining/observers"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "last_updated": now().date().isoformat(),
                    "observer_id": observer_id,
                    "observer_type": "structure",
                }
            ],
        )

        # when
        result = owner.fetch_mining_ledger_observers_from_esi()

        # then
        self.assertSetEqual(result, {observer_id})

    @pook.on
    def test_should_create_new_mining_ledger(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        corporation_id = owner.corporation.corporation_id
        miner_character = EveEntityCharacterFactory()
        miner_corporation = EveEntityCorporationFactory()
        last_updated = now().date()
        quantity = 500
        ore_type = MoonAsteroidsTypeFactory()
        pook.get(
            make_esi_url(
                f"corporation/{corporation_id}/mining/observers/{refinery.id}"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "character_id": miner_character.id,
                    "last_updated": last_updated.isoformat(),
                    "quantity": quantity,
                    "recorded_corporation_id": miner_corporation.id,
                    "type_id": ore_type.id,
                },
            ],
        )

        # when
        refinery.update_mining_ledger_from_esi()

        # then
        refinery.refresh_from_db()
        self.assertTrue(refinery.ledger_last_update_ok)
        self.assertTrue(refinery.ledger_last_update_at)
        self.assertEqual(refinery.mining_ledger.count(), 1)
        obj: MiningLedgerRecord = refinery.mining_ledger.get(
            character_id=miner_character.id
        )
        self.assertEqual(obj.day, last_updated)
        self.assertEqual(obj.quantity, quantity)
        self.assertEqual(obj.corporation, miner_corporation)
        self.assertEqual(obj.ore_type, ore_type)

    @pook.on
    def test_should_update_existing_mining_ledger(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        corporation_id = owner.corporation.corporation_id
        miner_character = EveEntityCharacterFactory()
        miner_corporation = EveEntityCorporationFactory()
        last_updated = now().date()
        ore_type_1 = MoonAsteroidsTypeFactory()
        MiningLedgerRecordFactory(
            refinery=refinery,
            day=last_updated,
            character_id=miner_character.id,
            corporation=miner_corporation,
            ore_type_id=ore_type_1.id,
            quantity=199,
        )
        quantity_1 = 500
        ore_type_2 = MoonAsteroidsTypeFactory()
        quantity_2 = 888
        pook.get(
            make_esi_url(
                f"corporation/{corporation_id}/mining/observers/{refinery.id}"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "character_id": miner_character.id,
                    "last_updated": last_updated.isoformat(),
                    "quantity": quantity_1,
                    "recorded_corporation_id": miner_corporation.id,
                    "type_id": ore_type_1.id,
                },
                {
                    "character_id": miner_character.id,
                    "last_updated": last_updated.isoformat(),
                    "quantity": quantity_2,
                    "recorded_corporation_id": miner_corporation.id,
                    "type_id": ore_type_2.id,
                },
            ],
        )
        # when
        refinery.update_mining_ledger_from_esi()

        # then
        qs: QuerySet[MiningLedgerRecord] = refinery.mining_ledger.filter(
            day=last_updated, character_id=miner_character.id
        )
        got = {x.ore_type.id: x.quantity for x in qs}
        want = {ore_type_1.id: quantity_1, ore_type_2.id: quantity_2}
        self.assertDictEqual(got, want)


class TestRefinery(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    def test_should_cancel_extraction_when_start_time_not_given(self):
        # given
        refinery = RefineryFactory()
        started_1 = now() - dt.timedelta(hours=2)
        ex_1 = ExtractionFactory(
            refinery=refinery,
            started_at=started_1,
            status=Extraction.Status.STARTED,
        )
        started_2 = now() - dt.timedelta(hours=2)
        ex_2 = ExtractionFactory(
            refinery=refinery,
            started_at=started_2,
            status=Extraction.Status.STARTED,
        )

        # when
        refinery.cancel_started_extractions_missing_from_list([started_1])

        # then
        ex_1.refresh_from_db()
        self.assertEqual(ex_1.status_2, Extraction.Status.STARTED)
        ex_2.refresh_from_db()
        self.assertEqual(ex_2.status_2, Extraction.Status.CANCELED)


class TestPlayground(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    def test_playground(self):
        notif = MoonNotificationFactory()
        self.assertTrue(notif)
