import datetime as dt
from unittest.mock import patch

import pook
import yaml

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_webtest import WebTest
from eveuniverse.models import EveMoon

from app_utils.testing import (
    create_user_from_evecharacter,
    json_response_to_python,
    queryset_pks,
)

from moonmining import tasks
from moonmining.models import Label, Moon, Owner, Refinery
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    ExtractionFactory,
    MoonAsteroidsTypeFactory,
    MoonFactory,
    OwnerFactory,
    RefineryFactory,
    datetime_to_ldap,
    make_esi_url,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import (
    load_eveuniverse,
    nearest_celestial_stub,
)
from moonmining.tests.testdata.survey_data import fetch_survey_data
from moonmining.views import moons

MANAGERS_PATH = "moonmining.managers"
MODELS_PATH = "moonmining.models.owners"
TASKS_PATH = "moonmining.tasks"
VIEWS_PATH = "moonmining.views.views_all"


class TestUI(WebTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
        )

    def test_should_open_extractions(self):
        # given
        self.app.set_user(self.user)
        # when
        index = self.app.get(reverse("moonmining:extractions"))
        # then
        self.assertEqual(index.status_code, 200)

    # TODO: Add more UI tests


@patch(MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub)
@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestRunRegularUpdates(helpers.TestCaseWithClearCache):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    @pook.on
    def test_should_update_all_from_esi(self):
        # given
        owner = OwnerFactory()
        corporation_id = owner.corporation.corporation_id
        character_id = owner.character_ownership.character.character_id
        refinery_id = 1000000000001
        structure_name = "Auga - Paradise Alpha"
        solar_system_id = 30002542
        structure_type_id = 35835
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
                    "structure_id": refinery_id,
                    "system_id": solar_system_id,
                    "type_id": structure_type_id,
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
                "solar_system_id": solar_system_id,
                "type_id": structure_type_id,
            },
        )
        timestamp = now()
        readyTime = timestamp + dt.timedelta(days=30)
        autoTime = readyTime + dt.timedelta(hours=4)
        moon_id = 40161465
        refinery_id = 1000000000001
        notification_id = 1005000101
        pook.get(
            make_esi_url(f"characters/{character_id}/notifications"),
            reply=200,
            response_json=[
                {
                    "notification_id": notification_id,
                    "type": "MoonminingExtractionStarted",
                    "sender_id": corporation_id,
                    "sender_type": "corporation",
                    "timestamp": timestamp.isoformat(),
                    "text": yaml.dump(
                        {
                            "autoTime": datetime_to_ldap(autoTime),
                            "moonID": moon_id,
                            "oreVolumeByType": {
                                46300: 1288475.124715103,
                                46301: 544691.7637724016,
                                46302: 526825.4047522942,
                                46303: 528996.6386983792,
                            },
                            "readyTime": datetime_to_ldap(readyTime),
                            "solarSystemID": solar_system_id,
                            "startedBy": 1001,
                            "startedByLink": '<a href="showinfo:1383//1001">Bruce Wayne</a>',
                            "structureID": refinery_id,
                            "structureLink": f'<a href="showinfo:{structure_type_id}//{refinery_id}">Dummy</a>',
                            "structureName": "Dummy",
                            "structureTypeID": structure_type_id,
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
                    "moon_id": moon_id,
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
    def test_should_not_update_disabled_owner(self):
        # given
        last_update_at = now() - dt.timedelta(hours=1)
        owner = OwnerFactory(
            is_enabled=False, last_update_at=last_update_at, last_update_ok=None
        )

        # when
        tasks.run_regular_updates.delay()

        # then
        owner.refresh_from_db()
        self.assertEqual(owner.last_update_at, last_update_at)
        self.assertIsNone(owner.last_update_ok)


@patch(MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub)
@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestUpdateOtherTasks(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_market_prices()

    @pook.on
    def test_should_update_mining_ledgers(self):
        # given
        owner = OwnerFactory()
        corporation_id = owner.corporation.corporation_id
        refinery = RefineryFactory(owner=owner)
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
        owner = OwnerFactory()
        refinery = RefineryFactory(owner=owner)
        extraction = ExtractionFactory(refinery=refinery)

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


class TestProcessSurveyInput(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
            ],
            scopes=Owner.esi_scopes(),
        )
        cls.survey_data = fetch_survey_data()

    @patch(MANAGERS_PATH + ".notify", new=lambda *args, **kwargs: None)
    def test_should_handle_bad_data_orderly(self):
        # when
        result = tasks.process_survey_input(self.survey_data.get(3))
        # then
        self.assertFalse(result)

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_success(self, mock_notify):
        result = tasks.process_survey_input(self.survey_data.get(2), self.user.pk)
        self.assertTrue(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "success")

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_error_1(self, mock_notify):
        result = tasks.process_survey_input("invalid input", self.user.pk)
        self.assertFalse(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "danger")


class TestMoonsDataFdd(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_market_prices()
        cls.moon = MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        cls.moon.label = Label.objects.create(name="Dummy")
        cls.moon.save()
        MoonFactory(eve_moon=EveMoon.objects.get(id=40131695))
        MoonFactory(eve_moon=EveMoon.objects.get(id=40161709))

    def test_should_return_fdd_for_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.view_all_moons"],
            scopes=Owner.esi_scopes(),
        )
        moon = Moon.objects.get(pk=40131695)
        RefineryFactory(moon=moon)
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
        self.assertEqual(response.status_code, 200)
        data = json_response_to_python(response)
        self.assertListEqual(data["alliance_name"], ["Wayne Enterprises"])
        self.assertListEqual(data["corporation_name"], ["Wayne Technologies"])
        self.assertListEqual(data["region_name"], ["Heimatar", "Metropolis"])
        self.assertListEqual(data["constellation_name"], ["Aldodan", "Hed"])
        self.assertListEqual(data["solar_system_name"], ["Auga", "Helgatild"])
        self.assertListEqual(data["rarity_class_str"], ["R64"])
        self.assertListEqual(data["label_name"], ["Dummy"])
        self.assertListEqual(data["has_refinery_str"], ["no", "yes"])
        self.assertListEqual(data["has_extraction_str"], [])
        self.assertIn("ERROR", data["invalid_column"][0])
