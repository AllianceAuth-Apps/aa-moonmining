from app_utils.testing import NoSocketsTestCase

from moonmining.core import CalculatedExtraction
from moonmining.models import Extraction, NotificationType
from moonmining.tests.testdata.factories import (
    ExtractionFactory,
    NotificationFactory,
    RefineryFactory,
)
from moonmining.tests.testdata.load_allianceauth import load_allianceauth
from moonmining.tests.testdata.load_eveuniverse import load_eveuniverse


class TestNotification(NoSocketsTestCase):
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
                notification = NotificationFactory(extraction=extraction)
                # when
                obj = notification.to_calculated_extraction()
                # then
                self.assertEqual(obj.status, out_status)


class TestNotificationType(NoSocketsTestCase):
    def test_str(self):
        # given
        obj = NotificationType.MOONMINING_EXTRACTION_CANCELLED
        # when/then
        self.assertIsInstance(str(obj), str)
