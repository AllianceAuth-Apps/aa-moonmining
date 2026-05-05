import datetime as dt

from django.utils.timezone import now
from eveuniverse.tests.testdata.factories_2 import EveEntityCharacterFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.core import CalculatedExtraction, CalculatedExtractionProduct
from moonmining.models import NotificationType
from moonmining.tests.testdata.factories_2 import (
    MoonNotificationFactory2,
    RefineryFactory2,
)


class TestNotification_ToCalculatedExtraction(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.refinery = RefineryFactory2()

    def test_should_convert_started_notification(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)
        started_by = EveEntityCharacterFactory()
        notif = MoonNotificationFactory2(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_STARTED,
            refinery=self.refinery,
            started_at=started_at,
            started_by=started_by,
        )

        # when
        extraction = notif.to_calculated_extraction()

        # then
        self.assertEqual(extraction.refinery_id, self.refinery.id)
        self.assertEqual(extraction.auto_fracture_at, auto_fracture_at)
        self.assertEqual(extraction.chunk_arrival_at, chunk_arrival_at)
        self.assertEqual(extraction.started_at, started_at)
        self.assertEqual(extraction.started_by, started_by.id)
        self.assertEqual(extraction.status, CalculatedExtraction.Status.STARTED)

        want = CalculatedExtractionProduct.create_list_from_dict(
            notif.details["oreVolumeByType"]
        )
        self.assertEqual(extraction.products, want)

    def test_should_convert_canceled_notification(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)
        canceled_by = EveEntityCharacterFactory()
        notif = MoonNotificationFactory2(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_CANCELLED,
            refinery=self.refinery,
            started_at=started_at,
            canceled_by=canceled_by,
        )

        # when
        extraction = notif.to_calculated_extraction()

        # then
        self.assertEqual(extraction.refinery_id, self.refinery.id)
        self.assertEqual(extraction.canceled_at, notif.timestamp)
        self.assertEqual(extraction.canceled_by, canceled_by.id)
        self.assertEqual(extraction.status, CalculatedExtraction.Status.CANCELED)

    def test_should_convert_finished_notification(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)
        notif = MoonNotificationFactory2(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_EXTRACTION_FINISHED,
            refinery=self.refinery,
            started_at=started_at,
        )

        # when
        extraction = notif.to_calculated_extraction()

        # then
        self.assertEqual(extraction.refinery_id, self.refinery.id)
        self.assertEqual(extraction.auto_fracture_at, auto_fracture_at)
        self.assertEqual(extraction.status, CalculatedExtraction.Status.READY)

        want = CalculatedExtractionProduct.create_list_from_dict(
            notif.details["oreVolumeByType"]
        )
        self.assertEqual(extraction.products, want)

    def test_should_convert_laser_fired_notification(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)
        fractured_by = EveEntityCharacterFactory()
        notif = MoonNotificationFactory2(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_LASER_FIRED,
            refinery=self.refinery,
            started_at=started_at,
            fired_by=fractured_by,
        )

        # when
        extraction = notif.to_calculated_extraction()

        # then
        self.assertEqual(extraction.refinery_id, self.refinery.id)
        self.assertEqual(extraction.fractured_at, notif.timestamp)
        self.assertEqual(extraction.fractured_by, fractured_by.id)
        self.assertEqual(extraction.status, CalculatedExtraction.Status.COMPLETED)

        want = CalculatedExtractionProduct.create_list_from_dict(
            notif.details["oreVolumeByType"]
        )
        self.assertEqual(extraction.products, want)

    def test_should_convert_auto_fracture_notification(self):
        # given
        started_at = now().replace(microsecond=0) - dt.timedelta(hours=1)
        chunk_arrival_at = started_at + dt.timedelta(days=3)
        auto_fracture_at = chunk_arrival_at + dt.timedelta(hours=2)
        notif = MoonNotificationFactory2(
            auto_fracture_at=auto_fracture_at,
            chunk_arrival_at=chunk_arrival_at,
            notif_type=NotificationType.MOONMINING_AUTOMATIC_FRACTURE,
            refinery=self.refinery,
            started_at=started_at,
        )

        # when
        extraction = notif.to_calculated_extraction()

        # then
        self.assertEqual(extraction.refinery_id, self.refinery.id)
        self.assertEqual(extraction.fractured_at, auto_fracture_at)
        self.assertEqual(extraction.status, CalculatedExtraction.Status.COMPLETED)

        want = CalculatedExtractionProduct.create_list_from_dict(
            notif.details["oreVolumeByType"]
        )
        self.assertEqual(extraction.products, want)


class TestNotificationType(NoSocketsTestCase):
    def test_str(self):
        # given
        obj = NotificationType.MOONMINING_EXTRACTION_CANCELLED
        # when/then
        self.assertIsInstance(str(obj), str)
