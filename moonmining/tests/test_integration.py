import datetime as dt
from http import HTTPStatus
from unittest.mock import Mock, patch

import pook
import yaml

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from eveuniverse.models import EveSolarSystem
from eveuniverse.tests.testdata.factories_2 import (
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    EveMoonFactory,
    MoonTypeFactory,
)

from app_utils.testing import NoSocketsTestCase, queryset_pks

from moonmining import tasks
from moonmining.models import Refinery
from moonmining.tests import helpers
from moonmining.tests.helpers import datetime_to_ldap
from moonmining.tests.testdata.factories_2 import (
    EveOreTypeFactory,
    ExtractionFactory2,
    MoonAsteroidsTypeFactory,
    OwnerFactory2,
    RefineryFactory2,
    RefineryTypeFactory,
    UserMainMemberFactory,
    UserMainOwnerFactory,
    make_esi_url,
)
from moonmining.tests.testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonmining.managers"
MODELS_PATH = "moonmining.models.owners"
TASKS_PATH = "moonmining.tasks"


class TestUI(TestCase):
    def test_should_open_extractions(self):
        # given
        user = UserMainOwnerFactory()
        self.client.force_login(user)
        # when
        index = self.client.get(reverse("moonmining:extractions"))
        # then
        self.assertEqual(index.status_code, HTTPStatus.OK)

    # TODO: Add more UI tests


@patch(MODELS_PATH + ".EveSolarSystem.nearest_celestial")
@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestRunRegularUpdates(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_update_all_from_esi(self, mock_nearest_celestial: Mock):
        # given
        owner = OwnerFactory2()
        corporation_id = owner.corporation.corporation_id
        character_id = owner.character_ownership.character.character_id
        eve_moon = EveMoonFactory()
        mock_nearest_celestial.return_value = EveSolarSystem.NearestCelestial(
            eve_type=MoonTypeFactory(),
            eve_object=eve_moon,
            distance=123,
        )
        refinery_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        structure_type = RefineryTypeFactory()
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
                    "structure_id": refinery_id,
                    "system_id": eve_moon.eve_planet.eve_solar_system.id,
                    "type_id": structure_type.id,
                },
            ],
        )
        pook.get(
            make_esi_url(f"universe/structures/{refinery_id}"),
            reply=200,
            response_json={
                "owner_id": corporation_id,
                "name": structure_name,
                "position": {
                    "x": 55028384780.0,
                    "y": 7310316270.0,
                    "z": -163686684205.0,
                },
                "solar_system_id": eve_moon.eve_planet.eve_solar_system.id,
                "type_id": structure_type.id,
            },
        )
        timestamp = now()
        readyTime = timestamp + dt.timedelta(days=30)
        autoTime = readyTime + dt.timedelta(hours=4)
        refinery_id = 1000000000001
        notification_id = 1005000101
        started_by = EveEntityCharacterFactory()
        pook.get(
            make_esi_url(f"characters/{character_id}/notifications"),
            reply=200,
            response_json=[
                {
                    "notification_id": notification_id,
                    "type": "MoonminingExtractionStarted",
                    "sender_id": EveEntityCorporationFactory().id,
                    "sender_type": "corporation",
                    "timestamp": timestamp.isoformat(),
                    "text": yaml.dump(
                        {
                            "autoTime": datetime_to_ldap(autoTime),
                            "moonID": eve_moon.id,
                            "oreVolumeByType": {
                                EveOreTypeFactory().id: 1288475.124715103,
                                EveOreTypeFactory().id: 544691.7637724016,
                                EveOreTypeFactory().id: 526825.4047522942,
                                EveOreTypeFactory().id: 528996.6386983792,
                            },
                            "readyTime": datetime_to_ldap(readyTime),
                            "solarSystemID": eve_moon.eve_planet.eve_solar_system.id,
                            "startedBy": started_by.id,
                            "startedByLink": f'<a href="showinfo:1383//{started_by.id}">{started_by.name}</a>',
                            "structureID": refinery_id,
                            "structureLink": f'<a href="showinfo:{structure_type.id}//{refinery_id}">Dummy</a>',
                            "structureName": "Dummy",
                            "structureTypeID": structure_type.id,
                        }
                    ),
                    "is_read": False,
                },
            ],
        )
        pook.get(
            make_esi_url(
                f"corporation/{owner.corporation.corporation_id}/mining/extractions"
            ),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "chunk_arrival_time": readyTime.isoformat(),
                    "extraction_start_time": timestamp.isoformat(),
                    "moon_id": eve_moon.id,
                    "natural_decay_time": autoTime.isoformat(),
                    "structure_id": refinery_id,
                },
            ],
        )

        # when
        tasks.run_regular_updates.delay()

        # then
        self.assertSetEqual(queryset_pks(Refinery.objects.all()), {refinery_id})
        refinery = Refinery.objects.get(id=refinery_id)
        self.assertEqual(refinery.extractions.count(), 1)
        owner.refresh_from_db()
        self.assertAlmostEqual(
            owner.last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
        self.assertTrue(owner.last_update_ok)

        # TODO: add more tests

    @pook.on
    def test_should_not_update_disabled_owner(self, mock_nearest_celestial: Mock):
        # given
        last_update_at = now() - dt.timedelta(hours=1)
        owner = OwnerFactory2(
            is_enabled=False, last_update_at=last_update_at, last_update_ok=None
        )

        # when
        tasks.run_regular_updates.delay()

        # then
        owner.refresh_from_db()
        self.assertEqual(owner.last_update_at, last_update_at)
        self.assertIsNone(owner.last_update_ok)


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestUpdateOtherTasks(helpers.TestCaseWithClearCache):
    @pook.on
    def test_should_update_mining_ledgers(self):
        # given
        owner = OwnerFactory2()
        corporation_id = owner.corporation.corporation_id
        refinery = RefineryFactory2(owner=owner)
        pook.get(
            make_esi_url(f"corporation/{corporation_id}/mining/observers"),
            reply=200,
            response_headers={"X-Pages": "1"},
            response_json=[
                {
                    "last_updated": now().date().isoformat(),
                    "observer_id": refinery.id,
                    "observer_type": "structure",
                }
            ],
        )
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
        tasks.run_report_updates()

        # then
        self.assertEqual(refinery.mining_ledger.count(), 1)

    @patch(TASKS_PATH + ".update_unresolved_eve_entities", spec=True)
    @patch(TASKS_PATH + ".EveMarketPrice.objects.update_from_esi", spec=True)
    def test_should_update_all_calculated_values(
        self, mock_update_prices, mock_eve_entities_task
    ):
        # given
        mock_update_prices.return_value = None
        owner = OwnerFactory2()
        refinery = RefineryFactory2(owner=owner)
        extraction = ExtractionFactory2(refinery=refinery)

        # when
        tasks.run_calculated_properties_update.delay()

        # then
        refinery.moon.refresh_from_db()
        extraction.refresh_from_db()
        self.assertIsNotNone(refinery.moon.value)
        self.assertIsNotNone(extraction.value)
        ore = extraction.products.first().ore_type
        self.assertIsNotNone(ore.extras.current_price)
        self.assertTrue(mock_eve_entities_task.si.called)


class TestProcessSurveyInput(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey_data = fetch_survey_data()

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_success(self, mock_notify: Mock):
        # given
        user = UserMainMemberFactory()
        EveMoonFactory(
            id=40161708,
            name="Auga V - Moon 1",
            eve_planet__id=40161707,
            eve_planet__name="Auga V",
            eve_planet__eve_solar_system__id=30002542,
            eve_planet__eve_solar_system__name="Auga",
        )
        EveMoonFactory(
            id=40161709,
            name="Auga V - Moon 2",
            eve_planet__id=40161708,
            eve_planet__name="Auga V",
            eve_planet__eve_solar_system__id=30002542,
            eve_planet__eve_solar_system__name="Auga",
        )
        EveOreTypeFactory(id=45492, name="Bitumens")
        EveOreTypeFactory(id=45494, name="Cobaltite")
        EveOreTypeFactory(id=45506, name="Cinnabar")
        EveOreTypeFactory(id=46676, name="Cubic Bistot")
        EveOreTypeFactory(id=46678, name="Flawless Arkonor")
        EveOreTypeFactory(id=46689, name="Stable Veldspar")

        # when
        result = tasks.process_survey_input(self.survey_data.get(2), user.pk)

        # then
        self.assertTrue(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], user)
        self.assertEqual(kwargs["level"], "success")

    @patch(MANAGERS_PATH + ".notify", new=lambda *args, **kwargs: None)
    def test_should_handle_bad_data_orderly(self):
        # given
        EveMoonFactory(
            id=40131695,
            name="Helgatild IX - Moon 12",
            eve_planet__id=40131683,
            eve_planet__name="Helgatild IX",
            eve_planet__eve_solar_system__id=30002063,
            eve_planet__eve_solar_system__name="Helgatild",
        )
        EveOreTypeFactory(id=45495, name="Euxenite")
        EveOreTypeFactory(id=45491, name="Sylvite")
        EveOreTypeFactory(id=45510, name="Xenotime")

        # when
        result = tasks.process_survey_input(self.survey_data.get(3))
        # then
        self.assertFalse(result)

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_error_1(self, mock_notify: Mock):
        # given
        user = UserMainMemberFactory()

        # when
        result = tasks.process_survey_input("invalid input", user.pk)

        # then
        self.assertFalse(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], user)
        self.assertEqual(kwargs["level"], "danger")
