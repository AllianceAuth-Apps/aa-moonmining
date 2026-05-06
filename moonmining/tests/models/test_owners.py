import datetime as dt
from typing import NamedTuple
from unittest.mock import Mock, patch

import pook
import yaml

from django.db.models import QuerySet
from django.utils.timezone import now
from esi.exceptions import HTTPError
from esi.models import Token
from eveuniverse.models import EveSolarSystem
from eveuniverse.tests.testdata.factories_2 import (
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    EveMoonFactory,
)

from app_utils.testing import NoSocketsTestCase, queryset_pks

from moonmining.models import (
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    MoonProduct,
    Notification,
    NotificationType,
    Owner,
    Refinery,
)
from moonmining.tests import helpers
from moonmining.tests.helpers import datetime_to_ldap
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    MiningLedgerRecordFactory,
    MoonAsteroidsTypeFactory,
    MoonFactory,
    MoonNotificationFactory,
    MoonTypeFactory,
    OwnerFactory,
    PositionFactory,
    RefineryFactory,
    RefineryTypeFactory,
    make_esi_url,
)

MODELS_PATH = "moonmining.models"


class TestOwner(NoSocketsTestCase):
    def test_should_return_token(self):
        # given
        owner = OwnerFactory()

        # when
        result = owner.fetch_token()

        # then
        self.assertIsInstance(result, Token)

    def test_should_raise_error_when_no_character_ownership(self):
        # given
        owner: Owner = OwnerFactory()
        owner.character_ownership = None
        owner.save()

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


class TestOwner_FetchNotifications(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_create_new_notifications_from_esi(self):
        # given
        owner = OwnerFactory()
        character_id = owner.character_ownership.character.character_id
        moon = EveMoonFactory()
        notification_id = 1005000101
        sender = EveEntityCorporationFactory()
        started_by = EveEntityCharacterFactory()
        structure_id = 1000000000001
        structureType = RefineryTypeFactory()
        timestamp = now()
        autoTime = datetime_to_ldap(now() + dt.timedelta(days=10))
        readyTime = datetime_to_ldap(now() + dt.timedelta(hours=3))
        oreVolumeByType = {
            "46300": 1288475.124715103,
            "46301": 544691.7637724016,
            "46302": 526825.4047522942,
            "46303": 528996.6386983792,
        }

        pook.get(
            make_esi_url(f"characters/{character_id}/notifications"),
            reply=200,
            response_json=[
                {
                    "notification_id": notification_id,
                    "type": "MoonminingExtractionStarted",
                    "sender_id": sender.id,
                    "sender_type": "corporation",
                    "timestamp": timestamp.isoformat(),
                    "text": yaml.dump(
                        {
                            "autoTime": autoTime,
                            "moonID": moon.id,
                            "oreVolumeByType": oreVolumeByType,
                            "readyTime": readyTime,
                            "solarSystemID": moon.eve_planet.eve_solar_system.id,
                            "startedBy": started_by.id,
                            "startedByLink": '<a href="showinfo:1383//1001">Bruce Wayne</a>',
                            "structureID": structure_id,
                            "structureLink": f'<a href="showinfo:35835//{structure_id}">Dummy</a>',
                            "structureName": "Dummy",
                            "structureTypeID": structureType.id,
                        }
                    ),
                    "is_read": False,
                },
            ],
        )

        # when
        owner.fetch_notifications_from_esi()

        # then
        self.assertEqual(owner.notifications.count(), 1)
        obj: Notification = owner.notifications.get(notification_id=notification_id)
        self.assertEqual(obj.notif_type, NotificationType.MOONMINING_EXTRACTION_STARTED)
        self.assertEqual(obj.sender, sender)
        self.assertEqual(obj.timestamp, timestamp)
        self.assertEqual(obj.details["autoTime"], autoTime)
        self.assertEqual(obj.details["moonID"], moon.id)
        self.assertEqual(obj.details["oreVolumeByType"], oreVolumeByType)
        self.assertEqual(obj.details["readyTime"], readyTime)
        self.assertEqual(obj.details["startedBy"], started_by.id)
        self.assertEqual(obj.details["structureID"], structure_id)
        self.assertEqual(obj.details["structureTypeID"], structureType.id)


@patch(MODELS_PATH + ".owners.notify_admins_throttled", lambda *args, **kwargs: None)
@patch(MODELS_PATH + ".owners.EveSolarSystem.nearest_celestial")
class TestOwner_UpdateRefineries(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_create_new_refineries_from_scratch(
        self, mock_nearest_celestial: Mock
    ):
        # given
        owner = OwnerFactory()
        corporation_id = owner.corporation.corporation_id
        structure_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        structure_type = RefineryTypeFactory()
        eve_moon = EveMoonFactory()
        mock_nearest_celestial.return_value = EveSolarSystem.NearestCelestial(
            eve_type=MoonTypeFactory(),
            eve_object=eve_moon,
            distance=123,
        )
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
                    "system_id": eve_moon.eve_planet.eve_solar_system.id,
                    "type_id": structure_type.id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_name,
                "position": PositionFactory(),
                "solar_system_id": eve_moon.eve_planet.eve_solar_system.id,
                "type_id": structure_type.id,
            },
        )

        # when
        owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})
        refinery = Refinery.objects.get(id=structure_id)
        self.assertEqual(refinery.name, structure_name)
        self.assertEqual(refinery.moon.eve_moon, eve_moon)

    @pook.on
    def test_should_handle_exception_from_nearest_celestial(
        self, mock_nearest_celestial: Mock
    ):
        # given
        owner = OwnerFactory()
        corporation_id = owner.corporation.corporation_id
        structure_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        structure_type = RefineryTypeFactory()
        eve_moon = EveMoonFactory()
        mock_nearest_celestial.side_effect = OSError
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
                    "system_id": eve_moon.eve_planet.eve_solar_system.id,
                    "type_id": structure_type.id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_name,
                "position": PositionFactory(),
                "solar_system_id": eve_moon.eve_planet.eve_solar_system.id,
                "type_id": structure_type.id,
            },
        )

        # when
        owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})
        refinery = Refinery.objects.get(id=structure_id)
        self.assertIsNone(refinery.moon)

    @pook.on
    def test_should_remove_refineries_that_no_longer_exist(
        self, mock_nearest_celestial: Mock
    ):
        # given
        owner = OwnerFactory()
        RefineryFactory(owner=owner)  # should be deleted
        corporation_id = owner.corporation.corporation_id
        structure_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        structure_type = RefineryTypeFactory()
        eve_moon = EveMoonFactory()
        mock_nearest_celestial.return_value = EveSolarSystem.NearestCelestial(
            eve_type=MoonTypeFactory(),
            eve_object=eve_moon,
            distance=123,
        )
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
                    "system_id": eve_moon.eve_planet.eve_solar_system.id,
                    "type_id": structure_type.id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{structure_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_name,
                "position": PositionFactory(),
                "solar_system_id": eve_moon.eve_planet.eve_solar_system.id,
                "type_id": structure_type.id,
            },
        )

        # when
        owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {structure_id})

    @pook.on
    def test_should_not_remove_refineries_after_http_error_in_corporation_structures(
        self, mock_nearest_celestial: Mock
    ):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        corporation_id = owner.corporation.corporation_id
        pook.get(
            make_esi_url(f"corporations/{corporation_id}/structures"),
            reply=500,
            response_json={"error": "some error"},
        )

        # when
        with self.assertRaises(HTTPError):
            owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {refinery.id})

    @pook.on
    def test_should_continue_with_other_refineries_after_http_error(
        self, mock_nearest_celestial: Mock
    ):
        owner = OwnerFactory()
        structure_1 = RefineryFactory(owner=owner)
        structure_2 = RefineryFactory(owner=owner)
        mock_nearest_celestial.return_value = EveSolarSystem.NearestCelestial(
            eve_type=MoonTypeFactory(),
            eve_object=structure_2.moon.eve_moon,
            distance=123,
        )
        corporation_id = owner.corporation.corporation_id
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
                    "system_id": structure_1.moon.solar_system().id,
                    "type_id": structure_1.eve_type.id,
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
                    "system_id": structure_2.moon.solar_system().id,
                    "type_id": structure_2.eve_type.id,
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
                "position": PositionFactory(),
                "solar_system_id": structure_2.moon.solar_system().id,
                "type_id": structure_2.eve_type.id,
            },
        )
        # when
        owner.update_refineries_from_esi()

        # then
        self.assertSetEqual(
            queryset_pks(Refinery.objects.all()), {structure_1.id, structure_2.id}
        )
        structure_2.refresh_from_db()
        self.assertEqual(structure_2.name, structure_2_name)


class TestOwner_UpdateExtractions(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_create_started_extraction_with_products(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)

        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        started_by = EveEntityCharacterFactory()
        notif = MoonNotificationFactory(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=started_at,
            started_by=started_by,
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
                    "extraction_start_time": started_at.isoformat(),
                    "moon_id": refinery.moon.eve_moon.id,
                    "natural_decay_time": auto_fracture_at.isoformat(),
                    "structure_id": refinery.id,
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
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertEqual(extraction.started_by, started_by)
        self.assertGreater(extraction.value, 0)


class TestOwner_UpdateExtractionsFromEsi(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_create_new_extractions(self):
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
    def test_should_cancel_extractions_when_they_are_no_longer_returned_1(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
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
    def test_should_cancel_extractions_when_they_are_no_longer_returned_2(self):
        # given
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
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


class TestOwner_UpdateExtractionsFromNotifications(NoSocketsTestCase):
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


class TestOwner_UpdateMiningLedger(helpers.TestCaseWithClearCache):
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


class TestRefinery_UpdateExtractionsFromNotifications(NoSocketsTestCase):
    def test_should_update_started_extraction(self):
        # given
        refinery = RefineryFactory()
        extraction = ExtractionFactory(
            refinery=refinery,
            create_products=False,
            status=Extraction.Status.STARTED,
        )
        notif = MoonNotificationFactory(
            auto_fracture_at=extraction.auto_fracture_at,
            chunk_arrival_at=extraction.chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=refinery,
            started_at=extraction.started_at,
        )

        # when
        refinery.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertEqual(extraction.started_by.id, notif.details["startedBy"])

    def test_should_cancel_extraction_and_update_products(self):
        # given
        refinery = RefineryFactory()
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
        refinery.update_extractions_from_notifications()

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
        refinery = RefineryFactory()
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
        refinery.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.READY)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])

    def test_should_update_completed_extraction_when_laser_fired(self):
        # given
        refinery = RefineryFactory()
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
        refinery.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertEqual(extraction.fractured_by.id, notif.details["firedBy"])

    def test_should_update_completed_extraction_when_auto_fracture(self):
        # given
        refinery = RefineryFactory()
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
        refinery.update_extractions_from_notifications()

        # then
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        qs: QuerySet[ExtractionProduct] = extraction.products.all()
        products_got = {str(x.ore_type.id): x.volume for x in qs}
        self.assertDictEqual(products_got, notif.details["oreVolumeByType"])
        self.assertIsNone(extraction.fractured_by)

    def test_should_update_refinery_with_moon_from_notification_when_not_set(self):
        # given
        refinery = RefineryFactory(moon=None)
        em = EveMoonFactory()
        MoonNotificationFactory(refinery=refinery, eve_moon=em)

        # when
        refinery.update_extractions_from_notifications()

        # then
        refinery.refresh_from_db()
        self.assertEqual(refinery.moon.eve_moon, em)

    @patch(MODELS_PATH + ".owners.MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", True)
    def test_should_update_moon_products_when_no_survey_exists(self):
        # given
        moon = MoonFactory()
        moon.products.all().delete()
        refinery = RefineryFactory(moon=moon)
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
        refinery.update_extractions_from_notifications()

        # then
        total = sum(x for x in notif.details["oreVolumeByType"].values())
        want = {
            id: round(volume / total, 2)
            for id, volume in notif.details["oreVolumeByType"].items()
        }
        qs: QuerySet[MoonProduct] = moon.products.all()
        got = {str(x.ore_type.id): round(x.amount, 2) for x in qs}
        self.assertDictEqual(got, want)

    @patch(MODELS_PATH + ".owners.MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", False)
    def test_should_not_update_moon_products_when_survey_exists(self):
        # given
        moon = MoonFactory()
        moon.products.all().delete()
        refinery = RefineryFactory(moon=moon)
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
        refinery.update_extractions_from_notifications()

        # then
        self.assertEqual(moon.products.count(), 0)


class TestRefinery_CancelStartedExtractionsMissingFromList(NoSocketsTestCase):
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
