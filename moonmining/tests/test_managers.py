import datetime as dt
from unittest.mock import patch

from django.test import TestCase
from django.utils.timezone import now
from eveuniverse.tests.testdata.factories_2 import EveMarketPriceFactory, EveMoonFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.models import EveOreType, Extraction, Moon
from moonmining.tests.testdata.factories_2 import (
    EveOreTypeFactory,
    ExtractionFactory2,
    OreTypeMaterialFactory,
    RefineryFactory2,
    UserMainMemberFactory,
)
from moonmining.tests.testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonmining.managers"


class TestEveOreTypeManager(NoSocketsTestCase):
    @patch(MANAGERS_PATH + ".MOONMINING_USE_REPROCESS_PRICING", False)
    def test_should_update_current_prices_with_market_price(self):
        # given
        ore_type = EveOreTypeFactory(create_price=False)
        average_price = 42
        EveMarketPriceFactory(eve_type=ore_type, average_price=average_price)

        # when
        EveOreType.objects.update_current_prices()

        # then
        self.assertEqual(ore_type.extras.current_price, average_price)

    @patch(MANAGERS_PATH + ".MOONMINING_REPROCESSING_YIELD", 0.7)
    @patch(MANAGERS_PATH + ".MOONMINING_USE_REPROCESS_PRICING", True)
    def test_should_update_current_prices_with_reprocessed_value(self):
        # given
        cinnabar: EveOreType = EveOreTypeFactory(
            create_price=False, create_type_materials=False
        )
        tungsten = OreTypeMaterialFactory(eve_type=cinnabar, quantity=10)
        mercury = OreTypeMaterialFactory(eve_type=cinnabar, quantity=50)
        evaporite_deposits = OreTypeMaterialFactory(eve_type=cinnabar, quantity=15)
        EveMarketPriceFactory(eve_type=tungsten.material_eve_type, average_price=7000)
        EveMarketPriceFactory(eve_type=mercury.material_eve_type, average_price=9750)
        EveMarketPriceFactory(
            eve_type=evaporite_deposits.material_eve_type, average_price=950
        )

        # when
        EveOreType.objects.update_current_prices()

        # then
        self.assertEqual(cinnabar.extras.current_price, 4002.25)


class TestExtractionManager(TestCase):
    def test_should_update_completed(self):
        # given
        refinery = RefineryFactory2()
        extraction_1 = ExtractionFactory2(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 1, 0, tzinfo=dt.timezone.utc),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 12, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=dt.timezone.utc),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_2 = ExtractionFactory2(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 2, 0, tzinfo=dt.timezone.utc),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=dt.timezone.utc),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_3 = ExtractionFactory2(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 3, 0, tzinfo=dt.timezone.utc),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2021, 1, 1, 21, 0, tzinfo=dt.timezone.utc),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_4 = ExtractionFactory2(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=dt.timezone.utc),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=dt.timezone.utc),
            auto_fracture_at=dt.datetime(2021, 1, 1, 7, 0, tzinfo=dt.timezone.utc),
            status=Extraction.Status.CANCELED,
            create_products=False,
        )

        # when
        with patch(MANAGERS_PATH + ".now") as mock_now:
            mock_now.return_value = dt.datetime(
                2021, 1, 1, 15, 30, tzinfo=dt.timezone.utc
            )
            Extraction.objects.all().update_status()

        # then
        extraction_1.refresh_from_db()
        self.assertEqual(extraction_1.status, Extraction.Status.COMPLETED)
        extraction_2.refresh_from_db()
        self.assertEqual(extraction_2.status, Extraction.Status.READY)
        extraction_3.refresh_from_db()
        self.assertEqual(extraction_3.status, Extraction.Status.STARTED)
        extraction_4.refresh_from_db()
        self.assertEqual(extraction_4.status, Extraction.Status.CANCELED)


class TestProcessSurveyInput(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey_data = fetch_survey_data()

    @patch(MANAGERS_PATH + ".notify", new=lambda *args, **kwargs: None)
    def test_should_process_survey_normally(self):
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
        result = Moon.objects.update_moons_from_survey(self.survey_data.get(2), user)

        # then
        self.assertTrue(result)
        m1 = Moon.objects.get(pk=40161708)
        self.assertEqual(m1.products_updated_by, user)
        self.assertAlmostEqual(m1.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2 = Moon.objects.get(pk=40161709)
        self.assertEqual(m2.products_updated_by, user)
        self.assertAlmostEqual(m2.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)
