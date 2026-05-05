from eveuniverse.tests.testdata.factories_2 import EveMarketPriceFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.constants import EveTypeId
from moonmining.core import CalculatedExtraction
from moonmining.models import EveOreType, OreQualityClass
from moonmining.tests.testdata.factories import Extraction
from moonmining.tests.testdata.factories_2 import (
    EveOreTypeFactory,
    ExtractionFactory2,
    OreTypeMaterialFactory,
    RefineryFactory2,
)
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse


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


# class TestExtractionIsJackpot(NoSocketsTestCase):
#     @classmethod
#     def setUpClass(cls):
#         super().setUpClass()
#         load_eveuniverse()
#         load_allianceauth()
#         moon = helpers.create_moon_40161708()
#         owner = Owner.objects.create(
#             corporation=EveCorporationInfo.objects.get(corporation_id=2001)
#         )
#         cls.refinery = Refinery.objects.create(
#             id=40161708, moon=moon, owner=owner, eve_type_id=35835
#         )
#         cls.ore_quality_regular = EveOreType.objects.get(id=45490)
#         cls.ore_quality_improved = EveOreType.objects.get(id=46280)
#         cls.ore_quality_excellent = EveOreType.objects.get(id=46281)
#         cls.ore_quality_excellent_2 = EveOreType.objects.get(id=46283)

#     def test_should_be_jackpot(self):
#         # given
#         extraction = ExtractionFactory(
#             refinery=self.refinery,
#             chunk_arrival_at=now() + dt.timedelta(days=3),
#             auto_fracture_at=now() + dt.timedelta(days=4),
#             started_at=now() - dt.timedelta(days=3),
#             status=Extraction.Status.STARTED,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_excellent,
#             volume=1000000 * 0.1,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_excellent_2,
#             volume=1000000 * 0.1,
#         )
#         # when
#         result = extraction.calc_is_jackpot()
#         # then
#         self.assertTrue(result)

#     def test_should_not_be_jackpot_1(self):
#         # given
#         extraction = ExtractionFactory(
#             refinery=self.refinery,
#             chunk_arrival_at=now() + dt.timedelta(days=3),
#             auto_fracture_at=now() + dt.timedelta(days=4),
#             started_at=now() - dt.timedelta(days=3),
#             status=Extraction.Status.STARTED,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_excellent,
#             volume=1000000 * 0.1,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_improved,
#             volume=1000000 * 0.1,
#         )
#         # when
#         result = extraction.calc_is_jackpot()
#         # then
#         self.assertFalse(result)

#     def test_should_not_be_jackpot_2(self):
#         # given
#         extraction = ExtractionFactory(
#             refinery=self.refinery,
#             chunk_arrival_at=now() + dt.timedelta(days=3),
#             auto_fracture_at=now() + dt.timedelta(days=4),
#             started_at=now() - dt.timedelta(days=3),
#             status=Extraction.Status.STARTED,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_improved,
#             volume=1000000 * 0.1,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_excellent,
#             volume=1000000 * 0.1,
#         )
#         # when
#         result = extraction.calc_is_jackpot()
#         # then
#         self.assertFalse(result)

#     def test_should_not_be_jackpot_3(self):
#         # given
#         extraction = ExtractionFactory(
#             refinery=self.refinery,
#             chunk_arrival_at=now() + dt.timedelta(days=3),
#             auto_fracture_at=now() + dt.timedelta(days=4),
#             started_at=now() - dt.timedelta(days=3),
#             status=Extraction.Status.STARTED,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_regular,
#             volume=1000000 * 0.1,
#         )
#         ExtractionProductFactory(
#             extraction=extraction,
#             ore_type=self.ore_quality_improved,
#             volume=1000000 * 0.1,
#         )
#         # when
#         result = extraction.calc_is_jackpot()
#         # then
#         self.assertFalse(result)

#     def test_should_not_be_jackpot_4(self):
#         # given
#         extraction = ExtractionFactory(
#             refinery=self.refinery,
#             chunk_arrival_at=now() + dt.timedelta(days=3),
#             auto_fracture_at=now() + dt.timedelta(days=4),
#             started_at=now() - dt.timedelta(days=3),
#             status=Extraction.Status.STARTED,
#         )
#         # when
#         result = extraction.calc_is_jackpot()
#         # then
#         self.assertFalse(result)


class TestExtraction(NoSocketsTestCase):
    def test_should_convert_to_calculated_extraction(self):
        # given
        refinery = RefineryFactory2()
        my_map = [
            (Extraction.Status.STARTED, CalculatedExtraction.Status.STARTED),
            (Extraction.Status.CANCELED, CalculatedExtraction.Status.CANCELED),
            (Extraction.Status.READY, CalculatedExtraction.Status.READY),
            (Extraction.Status.COMPLETED, CalculatedExtraction.Status.COMPLETED),
        ]
        for in_status, out_status in my_map:
            with self.subTest(status=in_status):
                extraction = ExtractionFactory2(status=in_status, refinery=refinery)
                # when
                obj = extraction.to_calculated_extraction()
                # then
                self.assertEqual(obj.status, out_status)


class TestOreQualityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_quality(self):
        # given
        ore_quality_regular = EveOreType.objects.get(id=EveTypeId.ZEOLITES)
        ore_quality_improved = EveOreType.objects.get(id=EveTypeId.BRIMFUL_ZEOLITES)
        ore_quality_excellent = EveOreType.objects.get(id=EveTypeId.GLISTENING_ZEOLITES)
        # when/then
        self.assertEqual(ore_quality_regular.quality_class, OreQualityClass.REGULAR)
        self.assertEqual(ore_quality_improved.quality_class, OreQualityClass.IMPROVED)
        self.assertEqual(ore_quality_excellent.quality_class, OreQualityClass.EXCELLENT)

    def test_should_return_correct_tag(self):
        self.assertIn("+100%", OreQualityClass.EXCELLENT.bootstrap_tag_html)
