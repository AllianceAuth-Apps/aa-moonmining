import datetime as dt
from unittest.mock import patch

from django.utils.timezone import now
from eveuniverse.tests.testdata.factories_2 import EveTypeFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.constants import EveGroupId
from moonmining.core import CalculatedExtractionProduct
from moonmining.models import OreRarityClass
from moonmining.tests.testdata.factories_2 import (
    EveOreTypeFactory,
    ExtractionFactory2,
    MoonAsteroidsTypeFactory,
    MoonFactory2,
    MoonNotificationFactory2,
    MoonProductFactory2,
    RefineryFactory2,
    UserMainMemberFactory,
)

MODELS_PATH = "moonmining.models"


class TestMoon_CalcValue(NoSocketsTestCase):
    @patch(MODELS_PATH + ".moons.MOONMINING_VOLUME_PER_MONTH", 1000000)
    def test_should_calc_correct_value(self):
        # given
        ore_1 = EveOreTypeFactory(
            create_price__average_price=2400.0, volume=10  # CINNABAR
        )
        ore_2 = EveOreTypeFactory(
            create_price__average_price=609.0, volume=16  # CUBIC_BISTOT
        )
        ore_3 = EveOreTypeFactory(
            create_price__average_price=310.9, volume=16  # FLAWLESS_ARKONOR
        )
        ore_4 = EveOreTypeFactory(
            create_price__average_price=7.7, volume=0.1  # STABLE_VELDSPAR
        )
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=ore_2, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=ore_3, amount=0.25)
        MoonProductFactory2(moon=moon, ore_type=ore_4, amount=0.33)

        # when
        result = moon.calc_value()

        # then
        self.assertEqual(result, 84622187.5)

    def test_should_return_zero_if_prices_are_missing(self):
        # given
        ore_1 = EveOreTypeFactory(create_price=False, volume=10)  # CINNABAR
        ore_2 = EveOreTypeFactory(create_price=False, volume=16)  # CUBIC_BISTOT
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=ore_2, amount=0.23)

        # when
        result = moon.calc_value()

        # then
        self.assertEqual(result, 0)


class TestMoon_CalcRarityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ore_type_r0 = EveTypeFactory()
        cls.ore_type_r4 = MoonAsteroidsTypeFactory(
            eve_group__id=EveGroupId.UBIQUITOUS_MOON_ASTEROIDS
        )
        cls.ore_type_r8 = MoonAsteroidsTypeFactory(
            eve_group__id=EveGroupId.COMMON_MOON_ASTEROIDS
        )
        cls.ore_type_r16 = MoonAsteroidsTypeFactory(
            eve_group__id=EveGroupId.UNCOMMON_MOON_ASTEROIDS
        )
        cls.ore_type_r32 = MoonAsteroidsTypeFactory(
            eve_group__id=EveGroupId.RARE_MOON_ASTEROIDS
        )
        cls.ore_type_r64 = MoonAsteroidsTypeFactory(
            eve_group__id=EveGroupId.EXCEPTIONAL_MOON_ASTEROIDS
        )

    def test_should_return_R4(self):
        # given
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R4)

    def test_should_return_R8(self):
        # given
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R8)

    def test_should_return_R16(self):
        # given
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R16)

    def test_should_return_R32(self):
        # given
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R32)

    def test_should_return_R64(self):
        # given
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=self.ore_type_r64, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R64)

    def test_should_handle_moon_without_products(self):
        # given
        moon = MoonFactory2(create_products=False)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.NONE)


class TestMoon_ProductsSorted(NoSocketsTestCase):
    def test_should_return_moon_products_in_order(self):
        # given
        ore_1 = EveOreTypeFactory(name="Xenotime")
        ore_2 = EveOreTypeFactory(name="Chromite")
        ore_3 = EveOreTypeFactory(name="Euxenite")
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1)
        MoonProductFactory2(moon=moon, ore_type=ore_2)
        MoonProductFactory2(moon=moon, ore_type=ore_3)

        # when
        result = moon.products_sorted()

        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_price(self):
        # given
        ore_1 = EveOreTypeFactory(name="Xenotime", create_price=False)
        ore_2 = EveOreTypeFactory(name="Chromite", create_price=False)
        ore_3 = EveOreTypeFactory(name="Euxenite", create_price=False)
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1)
        MoonProductFactory2(moon=moon, ore_type=ore_2)
        MoonProductFactory2(moon=moon, ore_type=ore_3)

        # when
        result = moon.products_sorted()

        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_amount(self):
        # given
        ore_1 = EveOreTypeFactory(name="Xenotime", create_price=False)
        ore_2 = EveOreTypeFactory(name="Chromite", create_price=False)
        ore_3 = EveOreTypeFactory(name="Euxenite", create_price=False)
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0)
        MoonProductFactory2(moon=moon, ore_type=ore_2)
        MoonProductFactory2(moon=moon, ore_type=ore_3)

        # when
        result = moon.products_sorted()

        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_volume(self):
        # given
        ore_1 = EveOreTypeFactory(name="Xenotime", create_price=False, volume=None)
        ore_2 = EveOreTypeFactory(name="Chromite", create_price=False)
        ore_3 = EveOreTypeFactory(name="Euxenite", create_price=False)
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1)
        MoonProductFactory2(moon=moon, ore_type=ore_2)
        MoonProductFactory2(moon=moon, ore_type=ore_3)

        # when
        result = moon.products_sorted()

        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)


@patch(MODELS_PATH + ".moons.MOONMINING_VOLUME_PER_DAY", 960400)
class TestMoon_UpdateProductsFromCalculatedExtraction(NoSocketsTestCase):
    def test_should_overwrite_existing_amounts(self):
        # given
        ore_1 = EveOreTypeFactory()
        ore_2 = EveOreTypeFactory()
        moon = MoonFactory2(create_products=False)
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=ore_2, amount=0.23)
        refinery = RefineryFactory2(moon=moon)
        notif = MoonNotificationFactory2(refinery=refinery)
        extraction = notif.to_calculated_extraction()
        ores = {str(ore_1.id): 7_683_200, str(ore_2.id): 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)

        # when
        result = moon.update_products_from_calculated_extraction(extraction)

        # then
        self.assertTrue(result)
        self.assertAlmostEqual(
            moon.products.get(ore_type_id=ore_1.id).amount, 0.4, places=2
        )
        self.assertAlmostEqual(
            moon.products.get(ore_type_id=ore_2.id).amount, 0.5, places=2
        )
        self.assertIsNone(moon.products_updated_by)
        self.assertIsNotNone(moon.products_updated_at)
        self.assertAlmostEqual(
            moon.products_updated_at, now(), delta=dt.timedelta(minutes=1)
        )

    def test_should_not_overwrite_existing_survey(self):
        # given
        ore_1 = EveOreTypeFactory()
        ore_2 = EveOreTypeFactory()
        moon = MoonFactory2(
            create_products=False, products_updated_by=UserMainMemberFactory()
        )
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=ore_2, amount=0.23)
        refinery = RefineryFactory2(moon=moon)
        notif = MoonNotificationFactory2(refinery=refinery)
        extraction = notif.to_calculated_extraction()
        ores = {str(ore_1.id): 7_683_200, str(ore_2.id): 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)

        # when
        result = moon.update_products_from_calculated_extraction(extraction)

        # then
        self.assertFalse(result)

    def test_should_overwrite_existing_survey_when_requested(self):
        ore_1 = EveOreTypeFactory()
        ore_2 = EveOreTypeFactory()
        moon = MoonFactory2(
            create_products=False, products_updated_by=UserMainMemberFactory()
        )
        MoonProductFactory2(moon=moon, ore_type=ore_1, amount=0.19)
        MoonProductFactory2(moon=moon, ore_type=ore_2, amount=0.23)
        refinery = RefineryFactory2(moon=moon)
        notif = MoonNotificationFactory2(refinery=refinery)
        extraction = notif.to_calculated_extraction()
        ores = {str(ore_1.id): 7_683_200, str(ore_2.id): 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)

        # when
        result = moon.update_products_from_calculated_extraction(
            extraction, overwrite_survey=True
        )
        # then
        self.assertTrue(result)

    def test_should_not_overwrite_from_calculated_extraction_without_products(self):
        # given
        moon = MoonFactory2()
        refinery = RefineryFactory2(moon=moon)
        notif = MoonNotificationFactory2(refinery=refinery)
        extraction = notif.to_calculated_extraction()
        extraction.products = []

        # when
        result = moon.update_products_from_calculated_extraction(extraction)

        # then
        self.assertFalse(result)
        self.assertTrue(moon.products.exists())


class TestMoon_UpdateProductsFromLatestExtraction(NoSocketsTestCase):
    def test_should_overwrite_products_from_latest_extraction(self):
        # given
        moon = MoonFactory2()
        refinery = RefineryFactory2(moon=moon)
        ExtractionFactory2(refinery=refinery)
        moon.products.all().delete()

        # when
        moon.update_products_from_latest_extraction()

        # then
        self.assertGreater(moon.products.count(), 0)
