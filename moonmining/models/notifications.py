"""Notification models."""

from enum import Enum

from django.db import models
from django.utils.translation import gettext_lazy as _
from eveuniverse.models import EveEntity

from app_utils.datetime import ldap_time_2_datetime

from moonmining.core import CalculatedExtraction, CalculatedExtractionProduct

# MAX_DISTANCE_TO_MOON_METERS = 3000000


class NotificationType(str, Enum):
    """ESI notification types used in this app."""

    MOONMINING_AUTOMATIC_FRACTURE = "MoonminingAutomaticFracture"
    MOONMINING_EXTRACTION_CANCELLED = "MoonminingExtractionCancelled"
    MOONMINING_EXTRACTION_FINISHED = "MoonminingExtractionFinished"
    MOONMINING_EXTRACTION_STARTED = "MoonminingExtractionStarted"
    MOONMINING_LASER_FIRED = "MoonminingLaserFired"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def all_moon_mining(cls) -> set:
        """Return all moon mining notifications"""
        return {
            cls.MOONMINING_AUTOMATIC_FRACTURE,
            cls.MOONMINING_EXTRACTION_CANCELLED,
            cls.MOONMINING_EXTRACTION_FINISHED,
            cls.MOONMINING_EXTRACTION_STARTED,
            cls.MOONMINING_LASER_FIRED,
        }

    @classmethod
    def with_products(cls) -> set:
        """Return all notification types with have products."""
        return {
            cls.MOONMINING_AUTOMATIC_FRACTURE,
            cls.MOONMINING_EXTRACTION_FINISHED,
            cls.MOONMINING_EXTRACTION_STARTED,
            cls.MOONMINING_LASER_FIRED,
        }


class Notification(models.Model):
    """An EVE Online notification about structures."""

    # pk
    owner = models.ForeignKey(
        "Owner",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text=_("Corporation that received this notification"),
    )
    notification_id = models.PositiveBigIntegerField(verbose_name="id")
    # regular
    created = models.DateTimeField(
        null=True,
        default=None,
        help_text=_("Date when this notification was first received from ESI"),
    )
    details = models.JSONField(default=dict)
    notif_type = models.CharField(
        max_length=100,
        default="",
        db_index=True,
        verbose_name="type",
        help_text=_("type of this notification as reported by ESI"),
    )
    is_read = models.BooleanField(
        null=True,
        default=None,
        help_text=_("True when this notification has read in the eve client"),
    )
    last_updated = models.DateTimeField(
        help_text=_("Date when this notification has last been updated from ESI")
    )
    sender = models.ForeignKey(
        EveEntity, on_delete=models.CASCADE, null=True, default=None, related_name="+"
    )
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "notification_id"], name="functional_pk_notification"
            )
        ]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")

    def __str__(self) -> str:
        return str(self.notification_id)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(notification_id={self.notification_id}, "
            f"owner='{self.owner}', notif_type='{self.notif_type}')"
        )

    def to_calculated_extraction(self) -> CalculatedExtraction:
        """Generate a calculated extraction from this notification."""
        params = {"refinery_id": self.details["structureID"]}
        if self.notif_type == NotificationType.MOONMINING_EXTRACTION_STARTED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.STARTED,
                    "chunk_arrival_at": ldap_time_2_datetime(self.details["readyTime"]),
                    "auto_fracture_at": ldap_time_2_datetime(self.details["autoTime"]),
                    "started_at": self.timestamp,
                    "started_by": self.details.get("startedBy"),
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif self.notif_type == NotificationType.MOONMINING_EXTRACTION_FINISHED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.READY,
                    "auto_fracture_at": ldap_time_2_datetime(self.details["autoTime"]),
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif self.notif_type in {
            NotificationType.MOONMINING_LASER_FIRED,
            NotificationType.MOONMINING_AUTOMATIC_FRACTURE,
        }:
            params.update(
                {
                    "fractured_by": self.details.get("firedBy"),
                    "fractured_at": self.timestamp,
                    "status": CalculatedExtraction.Status.COMPLETED,
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif self.notif_type == NotificationType.MOONMINING_EXTRACTION_CANCELLED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.CANCELED,
                    "canceled_at": self.timestamp,
                    "canceled_by": self.details.get("cancelledBy"),
                }
            )
        return CalculatedExtraction(**params)
