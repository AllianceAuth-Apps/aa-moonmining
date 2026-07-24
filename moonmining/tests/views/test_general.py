from http import HTTPStatus
from unittest.mock import Mock, patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from esi.models import Token

from app_utils.testdata_factories import (
    EveCharacterFactory,
    EveCorporationInfoFactory,
    UserMainFactory,
)
from app_utils.testing import NoSocketsTestCase, add_character_to_user

from moonmining.models import Owner
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    MoonFactory,
    OwnerFactory,
    RefineryFactory,
)
from moonmining.views import general

MODULE_PATH = "moonmining.views.general"


class TestUserWithAddOwnerPermission(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.add_refinery_owner"],
        )
        cls.character = cls.user.profile.main_character

    @patch(MODULE_PATH + ".notify_admins")
    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_can_add_new_owner(
        self, mock_messages, mock_update_owner, mock_notify_admins
    ):
        # given
        token = self.user.token_set.first()
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__

        # when
        response: HttpResponse = orig_view(request, token)

        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_owner.delay.called)
        self.assertTrue(mock_notify_admins.called)
        obj = Owner.objects.get(
            corporation__corporation_id=self.character.corporation_id
        )
        self.assertEqual(obj.character_ownership, self.character.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_can_update_existing_owner(self, mock_messages, mock_update_owner):
        # given
        owner = OwnerFactory(user=self.user)
        owner.character_ownership = None
        owner.save()
        token = self.user.token_set.first()
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__

        # when
        response = orig_view(request, token)

        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_owner.delay.called)
        owner.refresh_from_db()
        self.assertEqual(owner.character_ownership, self.character.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_should_abort_when_character_ownership_not_found(
        self, mock_messages, mock_update_owner
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = 1099
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__

        # when
        response = orig_view(request, token)

        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertTrue(mock_messages.error.called)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_should_abort_when_character_in_npc_corp(
        self, mock_messages, mock_update_owner
    ):
        # given
        user = UserMainFactory()
        npc_corporation = EveCorporationInfoFactory(
            corporation_id=1000115, corporation_name="University of Caille"
        )
        character = EveCharacterFactory(corporation=npc_corporation)
        add_character_to_user(user, character)
        token = user.token_set.get(character_id=character.character_id)
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__

        # when
        response = orig_view(request, token)

        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertTrue(mock_messages.error.called)


class TestViewsAreWorking(NoSocketsTestCase):
    def test_should_redirect_to_moons_page(self):
        # given
        MoonFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/")
        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(response.url, "/moonmining/moons")

    def test_should_redirect_to_extractions_page(self):
        # given
        ExtractionFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/")
        # then
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(response.url, "/moonmining/extractions")

    def test_should_open_extractions_page(self):
        # given
        ExtractionFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")

    def test_should_open_moon_details_page(self):
        # given
        moon = MoonFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moon/{moon.pk}?new_page=yes")
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_extraction_details_page(self):
        # given
        extraction = ExtractionFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get(
            f"/moonmining/extraction/{extraction.pk}?new_page=yes"
        )
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_add_moon_scan_page(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.upload_moon_scan"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/upload_survey")
        # then
        self.assertTemplateUsed(response, "moonmining/modals/upload_survey.html")

    def test_should_open_moons_page(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/moons")
        # then
        self.assertTemplateUsed(response, "moonmining/moons.html")

    def test_should_open_reports_page(self):
        # given
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.reports_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/reports")
        # then
        self.assertTemplateUsed(response, "moonmining/reports.html")

    def test_should_handle_empty_refineries_extractions_page(self):
        # given
        RefineryFactory()
        user = UserMainFactory(
            main_character__scopes=Owner.esi_scopes(),
            permissions__=["moonmining.basic_access", "moonmining.extractions_access"],
        )
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")
