from eveuniverse.models import EveMarketPrice, EveType

from app_utils.testing import NoSocketsTestCase

from moonmining.constants import EveTypeId
from moonmining.core import CalculatedExtraction
from moonmining.models import EveOreType, OreQualityClass
from moonmining.tests.testdata.factories import (
    Extraction,
    ExtractionFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse


class TestEveOreTypeCalcRefinedValues(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def setUp(self) -> None:
        self.cinnebar = EveOreType.objects.get(id=45506)
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)

    def test_should_return_value_per_unit(self):
        self.assertEqual(self.cinnebar.calc_refined_value_per_unit(0.7), 4002.25)


class TestEveOreTypeProfileUrl(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_value(self):
        # given
        cinnebar = EveOreType.objects.get(id=45506)
        # when
        result = cinnebar.profile_url
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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

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
