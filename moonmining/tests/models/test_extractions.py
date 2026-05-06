from eveuniverse.tests.testdata.factories_2 import EveMarketPriceFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.core import CalculatedExtraction
from moonmining.models import EveOreType, Extraction, OreQualityClass
from moonmining.tests.testdata.factories import (
    EveOreTypeFactory,
    ExtractionFactory,
    OreTypeMaterialFactory,
    RefineryFactory,
)


class TestEveOreTypeCalcRefinedValues(NoSocketsTestCase):
    def test_with_factories(self) -> None:
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
        got = cinnabar.calc_refined_value_per_unit(0.7)

        # then
        self.assertEqual(got, 4002.25)


class TestEveOreTypeProfileUrl(NoSocketsTestCase):
    def test_should_return_correct_value(self):
        # given
        cinnabar = EveOreTypeFactory(id=45506)
        # when
        result = cinnabar.profile_url
        # then
        self.assertEqual(result, "https://www.kalkoken.org/apps/eveitems/?typeId=45506")


class TestExtraction(NoSocketsTestCase):
    def test_should_convert_to_calculated_extraction(self):
        # given
        refinery = RefineryFactory()
        my_map = [
            (Extraction.Status.STARTED, CalculatedExtraction.Status.STARTED),
            (Extraction.Status.CANCELED, CalculatedExtraction.Status.CANCELED),
            (Extraction.Status.READY, CalculatedExtraction.Status.READY),
            (Extraction.Status.COMPLETED, CalculatedExtraction.Status.COMPLETED),
        ]
        for in_status, out_status in my_map:
            with self.subTest(status=in_status):
                extraction = ExtractionFactory(status=in_status, refinery=refinery)
                # when
                obj = extraction.to_calculated_extraction()
                # then
                self.assertEqual(obj.status, out_status)


class TestOreQualityClass2(NoSocketsTestCase):
    def test_from_eve_type(self):
        cases = [
            (
                "regular",
                EveOreTypeFactory(ore_quality_class=OreQualityClass.REGULAR),
                OreQualityClass.REGULAR,
            ),
            (
                "improved",
                EveOreTypeFactory(ore_quality_class=OreQualityClass.IMPROVED),
                OreQualityClass.IMPROVED,
            ),
            (
                "excellent",
                EveOreTypeFactory(ore_quality_class=OreQualityClass.EXCELLENT),
                OreQualityClass.EXCELLENT,
            ),
            (
                "undefined",
                EveOreTypeFactory(ore_quality_class=False),
                OreQualityClass.UNDEFINED,
            ),
        ]
        for name, ot, want in cases:
            with self.subTest(name=name):
                got = OreQualityClass.from_eve_type(ot)
                self.assertEqual(got, want)

    def test_should_return_correct_tag(self):
        self.assertIn("+100%", OreQualityClass.EXCELLENT.bootstrap_tag_html)
