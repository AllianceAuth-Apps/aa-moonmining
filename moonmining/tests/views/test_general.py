from unittest.mock import Mock, patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from esi.models import Token

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

from moonmining.models import Owner
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    MoonFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse
from moonmining.views import general

MODULE_PATH = "moonmining.views.general"


class TestOwner(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_allianceauth()
        load_eveuniverse()
        cls.factory = RequestFactory()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001, permissions=["moonmining.add_refinery_owner"]
        )

    @patch(MODULE_PATH + ".notify_admins")
    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_should_add_new_owner(
        self, mock_messages, mock_update_owner, mock_notify_admins
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_owner.delay.called)
        self.assertTrue(mock_notify_admins.called)
        obj = Owner.objects.get(corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_should_update_existing_owner(self, mock_messages, mock_update_owner):
        # given
        Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=None,
        )
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = general.add_owner.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_owner.delay.called)
        obj = Owner.objects.get(corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages")
    def test_should_raise_404_if_character_ownership_not_found(
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
        with self.assertRaises(Http404):
            orig_view(request, token)


class TestViewsAreWorking(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.reports_access",
                "moonmining.view_all_moons",
                "moonmining.upload_moon_scan",
                "moonmining.add_refinery_owner",
            ],
            scopes=[
                "esi-industry.read_corporation_mining.v1",
                "esi-universe.read_structures.v1",
                "esi-characters.read_notifications.v1",
                "esi-corporations.read_structures.v1",
            ],
        )
        cls.moon = MoonFactory()

    def test_should_redirect_to_extractions_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/")
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/moonmining/extractions")

    def test_should_open_extractions_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")

    def test_should_open_moon_details_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get(f"/moonmining/moon/{self.moon.pk}?new_page=yes")
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_extraction_details_page(self):
        # given
        refinery = RefineryFactory(moon=self.moon)
        extraction = ExtractionFactory(refinery=refinery)
        self.client.force_login(self.user)
        # when
        response = self.client.get(
            f"/moonmining/extraction/{extraction.pk}?new_page=yes"
        )
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_add_moon_scan_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/upload_survey")
        # then
        self.assertTemplateUsed(response, "moonmining/modals/upload_survey.html")

    def test_should_open_moons_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/moons")
        # then
        self.assertTemplateUsed(response, "moonmining/moons.html")

    def test_should_open_reports_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/reports")
        # then
        self.assertTemplateUsed(response, "moonmining/reports.html")

    def test_should_handle_empty_refineries_extractions_page(self):
        # given
        refinery = RefineryFactory()
        ExtractionFactory(refinery=refinery)
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")
