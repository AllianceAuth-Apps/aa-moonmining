from django.test import RequestFactory, TestCase
from eveuniverse.models import EveMoon

from app_utils.testing import create_user_from_evecharacter

from moonmining.models import Label, Moon, Owner
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import MoonFactory, RefineryFactory
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse
from moonmining.views import moons

MODULE_PATH = "moonmining.views.moons"


class TestMoonsData(TestCase):
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

    @staticmethod
    def _response_to_dict(response):
        data = helpers.json_response_to_python_2(response)
        return {int(obj[0]): obj for obj in data}

    def test_should_return_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.view_all_moons"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.ALL)

        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695, 40161708, 40161709})
        obj = data[40161708]
        self.assertEqual(obj[1], "Auga V - 1")

    def test_should_return_our_moons_only(self):
        # given
        moon = Moon.objects.get(pk=40131695)
        RefineryFactory(moon=moon)
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.OURS)

        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_return_our_moons_when_all_moons_perm(self):
        # given
        moon = Moon.objects.get(pk=40131695)
        RefineryFactory(moon=moon)
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()

        # when
        response = my_view(request, category=moons.MoonsCategory.OURS)

        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_handle_empty_refineries(self):
        # given
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        moon = Moon.objects.get(pk=40131695)
        refinery = RefineryFactory(moon=moon)
        RefineryFactory(owner=refinery.owner, moon=None)
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()
        # when
        response = my_view(request, category=moons.MoonsCategory.OURS)
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_return_uploaded_moons_only(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.upload_moon_scan"],
            scopes=Owner.esi_scopes(),
        )
        self.moon.products_updated_by = user
        self.moon.save()
        request = self.factory.get("/")
        request.user = user
        my_view = moons.MoonListJson.as_view()
        # when
        response = my_view(request, category=moons.MoonsCategory.UPLOADS)
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40161708})


class TestMoonInfo(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    def test_should_open_page(self):
        # given
        moon = MoonFactory()
        user, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
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
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moon/{moon.pk}")
        # then
        self.assertTemplateUsed(response, "moonmining/modals/moon_details.html")
