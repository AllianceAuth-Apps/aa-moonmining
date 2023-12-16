import datetime as dt
from unittest.mock import patch

from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice

from app_utils.testdata_factories import UserFactory
from app_utils.testing import NoSocketsTestCase

from moonmining.constants import EveTypeId
from moonmining.core import CalculatedExtractionProduct
from moonmining.models import EveOreType, OreRarityClass
from moonmining.tests import helpers
from moonmining.tests.testdata.factories import (
    CalculatedExtractionFactory,
    ExtractionFactory,
    MoonFactory,
    MoonProductFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse

MODELS_PATH = "moonmining.models"


class TestMoonUpdateValue(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    @patch(MODELS_PATH + ".moons.MOONMINING_VOLUME_PER_MONTH", 1000000)
    @patch(MODELS_PATH + ".extractions.MOONMINING_REPROCESSING_YIELD", 0.7)
    def test_should_calc_correct_value(self):
        # given
        moon = MoonFactory(create_products=False)
        helpers.generate_market_prices(use_process_pricing=False)
        MoonProductFactory(moon=moon, ore_type_id=EveTypeId.CINNABAR, amount=0.19)
        MoonProductFactory(moon=moon, ore_type_id=EveTypeId.CUBIC_BISTOT, amount=0.23)
        MoonProductFactory(
            moon=moon, ore_type_id=EveTypeId.FLAWLESS_ARKONOR, amount=0.25
        )
        MoonProductFactory(
            moon=moon, ore_type_id=EveTypeId.STABLE_VELDSPAR, amount=0.33
        )
        # when
        result = moon.calc_value()
        # then
        self.assertEqual(result, 84622187.5)

    def test_should_return_zero_if_prices_are_missing(self):
        # given
        moon = MoonFactory()
        # when
        result = moon.calc_value()
        # then
        self.assertEqual(result, 0)


class TestMoonCalcRarityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.ore_type_r0 = EveOreType.objects.get(id=EveTypeId.CUBIC_BISTOT)
        cls.ore_type_r4 = EveOreType.objects.get(id=EveTypeId.BITUMENS)
        cls.ore_type_r8 = EveOreType.objects.get(id=EveTypeId.EUXENITE)
        cls.ore_type_r16 = EveOreType.objects.get(id=EveTypeId.CHROMITE)
        cls.ore_type_r32 = EveOreType.objects.get(id=EveTypeId.CINNABAR)
        cls.ore_type_r64 = EveOreType.objects.get(id=EveTypeId.XENOTIME)

    def test_should_return_R4(self):
        # given
        moon = MoonFactory(create_products=False)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R4)

    def test_should_return_R8(self):
        # given
        moon = MoonFactory(create_products=False)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R8)

    def test_should_return_R16(self):
        # given
        moon = MoonFactory(create_products=False)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R16)

    def test_should_return_R32(self):
        # given
        moon = MoonFactory(create_products=False)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R32)

    def test_should_return_R64(self):
        # given
        moon = MoonFactory(create_products=False)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProductFactory(moon=moon, ore_type=self.ore_type_r64, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R64)

    def test_should_handle_moon_without_products(self):
        # given
        moon = MoonFactory(create_products=False)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.NONE)


class TestMoonProductsSorted(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def setUp(self) -> None:
        helpers.generate_market_prices(use_process_pricing=False)

    def test_should_return_moon_products_in_order(self):
        # given
        moon = MoonFactory()
        # when
        result = moon.products_sorted()
        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_price(self):
        # given
        moon = MoonFactory()
        moon_product = moon.products.first()
        EveMarketPrice.objects.filter(
            eve_type_id=moon_product.ore_type_id
        ).average_price = None
        # when
        result = moon.products_sorted()
        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_amount(self):
        # given
        moon = MoonFactory()
        moon_product = moon.products.first()
        moon_product.amount = 0
        moon_product.save()
        # when
        result = moon.products_sorted()
        # then
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)

    def test_should_handle_products_without_volume(self):
        # given
        moon = MoonFactory()
        moon_product = moon.products.first()
        volume_backup = moon_product.ore_type.volume
        moon_product.ore_type.volume = None
        moon_product.ore_type.save()
        # when
        result = moon.products_sorted()
        # then
        moon_product.ore_type.volume = volume_backup
        moon_product.ore_type.save()
        ore_types = list(result.values_list("ore_type__name", flat=True))
        self.assertListEqual(["Chromite", "Euxenite", "Xenotime"], ore_types)


class TestMoonOverwriteProducts(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        helpers.generate_market_prices()
        load_allianceauth()

    def test_should_overwrite_existing_estimates(self):
        # given
        moon = MoonFactory()
        extraction = CalculatedExtractionFactory()
        ores = {"45506": 7_683_200, "46676": 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when
        result = moon.update_products_from_calculated_extraction(extraction)
        # then
        self.assertTrue(result)
        self.assertAlmostEqual(
            moon.products.get(ore_type_id=45506).amount, 0.4, places=2
        )
        self.assertAlmostEqual(
            moon.products.get(ore_type_id=46676).amount, 0.5, places=2
        )
        self.assertIsNone(moon.products_updated_by)
        self.assertIsNotNone(moon.products_updated_at)
        self.assertAlmostEqual(
            moon.products_updated_at, now(), delta=dt.timedelta(minutes=1)
        )

    def test_should_not_overwrite_existing_survey(self):
        # given
        moon = MoonFactory(products_updated_by=UserFactory())
        extraction = CalculatedExtractionFactory()
        ores = {"45506": 7_683_200, "46676": 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when
        result = moon.update_products_from_calculated_extraction(extraction)
        # then
        self.assertFalse(result)

    def test_should_overwrite_existing_survey_when_requested(self):
        # given
        moon = MoonFactory(products_updated_by=UserFactory())
        extraction = CalculatedExtractionFactory()
        ores = {"45506": 7_683_200, "46676": 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when
        result = moon.update_products_from_calculated_extraction(
            extraction, overwrite_survey=True
        )
        # then
        self.assertTrue(result)

    def test_should_not_overwrite_from_calculated_extraction_without_products(self):
        # given
        moon = MoonFactory()
        extraction = CalculatedExtractionFactory(products=[])
        # when
        result = moon.update_products_from_calculated_extraction(extraction)
        # then
        self.assertFalse(result)
        self.assertTrue(moon.products.exists())

    def test_should_overwrite_products_from_latest_extraction(self):
        # given
        moon = MoonFactory()
        refinery = RefineryFactory(moon=moon)
        ExtractionFactory(refinery=refinery)
        moon.products.all().delete()
        # when
        moon.update_products_from_latest_extraction()
        # then
        self.assertGreater(moon.products.count(), 0)
