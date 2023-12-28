"""Owner models."""

import datetime as dt
from collections import defaultdict
from typing import List, Optional, Tuple

import yaml

from django.contrib.auth.models import User
from django.db import models
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from esi.models import Token
from eveuniverse.models import EveEntity, EveMoon, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_admins_throttled
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from moonmining import __title__
from moonmining.app_settings import MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES
from moonmining.constants import EveGroupId, EveTypeId, IconSize
from moonmining.core import CalculatedExtraction, CalculatedExtractionProduct
from moonmining.managers import MiningLedgerRecordManager, RefineryManager
from moonmining.models.extractions import EveOreType, Extraction
from moonmining.models.moons import Moon
from moonmining.models.notifications import Notification, NotificationType
from moonmining.providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class MiningLedgerRecord(models.Model):
    """A recorded mining activity in the vicinity of a refinery."""

    refinery = models.ForeignKey(
        "Refinery",
        on_delete=models.CASCADE,
        related_name="mining_ledger",
        help_text=_("Refinery this mining activity was observed at"),
    )
    day = models.DateField(db_index=True, help_text=_("last_updated in ESI"))
    character = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("character that did the mining"),
    )
    ore_type = models.ForeignKey(
        EveOreType, on_delete=models.CASCADE, related_name="mining_ledger"
    )
    # regular
    corporation = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("corporation of the character at time data was recorded"),
    )
    quantity = models.PositiveBigIntegerField()
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        default=None,
        null=True,
        related_name="mining_ledger",
    )

    objects = MiningLedgerRecordManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refinery", "day", "character", "ore_type"],
                name="functional_pk_mining_activity",
            )
        ]
        verbose_name = _("ledger record")
        verbose_name_plural = _("ledger records")


class Owner(models.Model):
    """A EVE Online corporation owning refineries."""

    ESI_SERVICE_NAME_MOON_DRILLING = "Moon Drilling"

    # pk
    corporation = models.OneToOneField(
        EveCorporationInfo, on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    # regular
    character_ownership = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="+",
        help_text=_("Character used to sync this corporation from ESI"),
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Disabled corporations are excluded from the update process"),
    )
    last_update_at = models.DateTimeField(
        null=True, default=None, help_text=_("Time of last successful update")
    )
    last_update_ok = models.BooleanField(
        null=True, default=None, help_text=_("True if the last update was successful")
    )

    class Meta:
        verbose_name = _("owner")
        verbose_name_plural = _("owners")

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """Return name."""
        alliance_ticker_str = (
            f" [{self.corporation.alliance.alliance_ticker}]"
            if self.corporation.alliance
            else ""
        )
        return f"{self.corporation}{alliance_ticker_str}"

    @property
    def alliance_name(self) -> str:
        """Return alliance name."""
        return (
            self.corporation.alliance.alliance_name if self.corporation.alliance else ""
        )

    @property
    def name_html(self):
        """Return name as HTML."""
        return bootstrap_icon_plus_name_html(
            self.corporation.logo_url(size=IconSize.SMALL),
            self.name,
            size=IconSize.SMALL,
        )

    def fetch_token(self) -> Token:
        """Return valid token for this mining corp or raise exception on any error."""
        if not self.character_ownership:
            raise RuntimeError("This owner has no character configured.")
        token = (
            Token.objects.filter(
                character_id=self.character_ownership.character.character_id
            )
            .require_scopes(self.esi_scopes())
            .require_valid()
            .first()
        )
        if not token:
            raise Token.DoesNotExist(f"{self}: No valid token found.")
        return token

    def update_refineries_from_esi(self):
        """Update all refineries from ESI."""
        logger.info("%s: Updating refineries...", self)
        refineries = self._fetch_refineries_from_esi()
        for structure_id in refineries:
            try:
                self._update_or_create_refinery_from_esi(structure_id)
            except OSError as exc:
                exc_name = type(exc).__name__
                msg = (
                    f"{self}: Failed to fetch refinery with ID {structure_id} from ESI"
                )
                message_id = (
                    f"{__title__}-update_refineries_from_esi-"
                    f"{structure_id}-{exc_name}"
                )
                notify_admins_throttled(
                    message_id=message_id,
                    message=f"{msg}: {exc_name}: {exc}.",
                    title=f"{__title__}: Failed to fetch refinery",
                    level="warning",
                )
                logger.warning(msg, exc_info=True)
        # remove refineries that no longer exist
        self.refineries.exclude(id__in=refineries).delete()

        self.last_update_at = now()
        self.save()

    def _fetch_refineries_from_esi(self) -> dict:
        """Return current refineries with moon drills from ESI for this owner."""
        logger.info("%s: Fetching refineries from ESI...", self)
        structures = esi.client.Corporation.get_corporations_corporation_id_structures(
            corporation_id=self.corporation.corporation_id,
            token=self.fetch_token().valid_access_token(),
        ).results()
        refineries = {}
        for structure_info in structures:
            eve_type, _ = EveType.objects.get_or_create_esi(
                id=structure_info["type_id"]
            )
            structure_info["_eve_type"] = eve_type
            service_names = (
                {row["name"] for row in structure_info["services"]}
                if structure_info.get("services")
                else set()
            )
            if (
                eve_type.eve_group_id == EveGroupId.REFINERY
                and self.ESI_SERVICE_NAME_MOON_DRILLING in service_names
            ):
                refineries[structure_info["structure_id"]] = structure_info
        return refineries

    def _update_or_create_refinery_from_esi(self, structure_id: int):
        """Update or create a refinery with universe data from ESI."""
        logger.info("%s: Fetching details for refinery #%d", self, structure_id)
        structure_info = esi.client.Universe.get_universe_structures_structure_id(
            structure_id=structure_id, token=self.fetch_token().valid_access_token()
        ).results()
        refinery, _ = Refinery.objects.update_or_create(
            id=structure_id,
            defaults={
                "name": structure_info["name"],
                "eve_type": EveType.objects.get(id=structure_info["type_id"]),
                "owner": self,
            },
        )
        if not refinery.moon:
            refinery.update_moon_from_structure_info(structure_info)
        return True

    def fetch_notifications_from_esi(self) -> None:
        """fetches notification for the current owners and process them"""
        notifications = self._fetch_moon_notifications_from_esi()
        self._store_notifications(notifications)

    def _fetch_moon_notifications_from_esi(self) -> List[dict]:
        """Fetch all notifications from ESI for current owner."""
        logger.info("%s: Fetching notifications from ESI...", self)
        all_notifications = (
            esi.client.Character.get_characters_character_id_notifications(
                character_id=self.character_ownership.character.character_id,
                token=self.fetch_token().valid_access_token(),
            ).results()
        )
        moon_notifications = [
            notif
            for notif in all_notifications
            if notif["type"] in NotificationType.all_moon_mining()
        ]
        return moon_notifications

    def _store_notifications(self, notifications: list) -> int:
        """Store new notifications in database and return count of new objects."""
        # identify new notifications
        existing_notification_ids = set(
            self.notifications.values_list("notification_id", flat=True)
        )
        new_notifications = [
            obj
            for obj in notifications
            if obj["notification_id"] not in existing_notification_ids
        ]
        # create new notif objects
        sender_type_map = {
            "character": EveEntity.CATEGORY_CHARACTER,
            "corporation": EveEntity.CATEGORY_CORPORATION,
            "alliance": EveEntity.CATEGORY_ALLIANCE,
        }
        new_notification_objects = []
        for notification in new_notifications:
            known_sender_type = sender_type_map.get(notification["sender_type"])
            if known_sender_type:
                sender, _ = EveEntity.objects.get_or_create_esi(
                    id=notification["sender_id"]
                )
            else:
                sender = None
            text = notification["text"] if "text" in notification else None
            is_read = notification["is_read"] if "is_read" in notification else None
            new_notification_objects.append(
                Notification(
                    notification_id=notification["notification_id"],
                    owner=self,
                    created=now(),
                    details=yaml.safe_load(text) if text else {},
                    is_read=is_read,
                    last_updated=now(),
                    # at least one type has a trailing white space
                    # which we need to remove
                    notif_type=notification["type"].strip(),
                    sender=sender,
                    timestamp=notification["timestamp"],
                )
            )

        Notification.objects.bulk_create(new_notification_objects)
        if len(new_notification_objects) > 0:
            logger.info(
                "%s: Received %d new notifications from ESI",
                self,
                len(new_notification_objects),
            )
        else:
            logger.info("%s: No new notifications received from ESI", self)
        return len(new_notification_objects)

    def update_extractions(self):
        """Update extractions fro ESI."""
        self.update_extractions_from_esi()
        Extraction.objects.all().update_status()
        self.update_extractions_from_notifications()

    def update_extractions_from_esi(self):
        """Creates new extractions from ESI for current owner."""
        extractions_by_refinery = self._fetch_extractions_from_esi()
        self._update_or_create_extractions(extractions_by_refinery)

    def _fetch_extractions_from_esi(self):
        logger.info("%s: Fetching extractions from ESI...", self)
        extractions = (
            esi.client.Industry.get_corporation_corporation_id_mining_extractions(
                corporation_id=self.corporation.corporation_id,
                token=self.fetch_token().valid_access_token(),
            ).results()
        )
        logger.info("%s: Received %d extractions from ESI.", self, len(extractions))
        extractions_by_refinery = defaultdict(list)
        for row in extractions:
            extractions_by_refinery[row["structure_id"]].append(row)
        return extractions_by_refinery

    def _update_or_create_extractions(self, extractions_by_refinery: dict) -> None:
        new_extractions_count = 0
        for refinery_id, refinery_extractions in extractions_by_refinery.items():
            try:
                refinery = self.refineries.get(pk=refinery_id)
            except Refinery.DoesNotExist:
                continue
            new_extractions_count += refinery.create_extractions_from_esi_response(
                refinery_extractions
            )
            refinery.cancel_started_extractions_missing_from_list(
                [row["extraction_start_time"] for row in refinery_extractions]
            )
        if new_extractions_count:
            logger.info("%s: Created %d new extractions.", self, new_extractions_count)

    def update_extractions_from_notifications(self):
        """Create or update extractions from notifications."""
        logger.info("%s: Updating extractions from notifications...", self)
        notifications_count = self.notifications.count()
        if not notifications_count:
            logger.info("%s: No moon notifications.", self)
            return

        logger.info("%s: Processing %d moon notifications.", self, notifications_count)
        for refinery in self.refineries.all():
            _update_extractions_for_refinery(self, refinery)

    def fetch_mining_ledger_observers_from_esi(self) -> set:
        """Fetch mining ledger observers from ESI and return them."""
        logger.info("%s: Fetching mining observers from ESI...", self)
        observers = esi.client.Industry.get_corporation_corporation_id_mining_observers(
            corporation_id=self.corporation.corporation_id,
            token=self.fetch_token().valid_access_token(),
        ).results()
        logger.info("%s: Received %d observers from ESI.", self, len(observers))
        return {
            row["observer_id"]
            for row in observers
            if row["observer_type"] == "structure"
        }

    @classmethod
    def esi_scopes(cls):
        """Return list of all required esi scopes."""
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-universe.read_structures.v1",
            "esi-characters.read_notifications.v1",
            "esi-corporations.read_structures.v1",
            "esi-industry.read_corporation_mining.v1",
        ]


class Refinery(models.Model):
    """An Eve Online refinery structure."""

    # pk
    id = models.PositiveBigIntegerField(primary_key=True)
    # regular
    eve_type = models.ForeignKey(EveType, on_delete=models.CASCADE, related_name="+")
    moon = models.OneToOneField(
        Moon,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="refinery",
        help_text=_("The moon this refinery is anchored at (if any)"),
    )
    name = models.CharField(max_length=150, db_index=True)
    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="refineries",
        help_text=_("Corporation that owns this refinery"),
    )
    ledger_last_update_at = models.DateTimeField(
        null=True, default=None, help_text=_("last successful update of mining ledger")
    )
    ledger_last_update_ok = models.BooleanField(
        null=True,
        default=None,
        help_text=_("True if the last update of the mining ledger was successful"),
    )

    objects = RefineryManager()

    class Meta:
        verbose_name = _("refinery")
        verbose_name_plural = _("refineries")

    def __str__(self):
        return self.name

    def name_html(self) -> str:
        """Return name as HTML."""
        return format_html("{}<br>{}", self.name, self.owner.name)

    def update_moon_from_structure_info(self, structure_info: dict) -> bool:
        """Find moon based on location in space and update the object.
        Returns True when successful, else false
        """
        solar_system, _ = EveSolarSystem.objects.get_or_create_esi(
            id=structure_info["solar_system_id"]
        )
        try:
            nearest_celestial = solar_system.nearest_celestial(
                x=structure_info["position"]["x"],
                y=structure_info["position"]["y"],
                z=structure_info["position"]["z"],
                group_id=EveGroupId.MOON,
            )
        except OSError:
            logger.exception("%s: Failed to fetch nearest celestial ", self)
            return False
        if not nearest_celestial or nearest_celestial.eve_type.id != EveTypeId.MOON:
            return False
        eve_moon = nearest_celestial.eve_object
        moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
        self.moon = moon
        self.save()
        return True

    def update_moon_from_eve_id(self, eve_moon_id: int):
        """Update moon from ESI."""
        eve_moon, _ = EveMoon.objects.get_or_create_esi(id=eve_moon_id)
        moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
        self.moon = moon
        self.save()

    def update_mining_ledger_from_esi(self):
        """Update mining ledger from ESI."""
        self._reset_update_status()
        records = self._fetch_ledger_from_esi()
        self._preload_missing_ore_types(records)
        self._store_ledger(records)
        self._record_successful_update()

    def _reset_update_status(self):
        self.ledger_last_update_at = now()
        self.ledger_last_update_ok = None
        self.save()

    def _fetch_ledger_from_esi(self):
        logger.debug("%s: Fetching mining observer records from ESI...", self)
        token = self.owner.fetch_token().valid_access_token()
        records = esi.client.Industry.get_corporation_corporation_id_mining_observers_observer_id(
            corporation_id=self.owner.corporation.corporation_id,
            observer_id=self.id,
            token=token,
        ).results()
        logger.info(
            "%s: Received %d mining observer records from ESI", self, len(records)
        )

        return records

    def _preload_missing_ore_types(self, records):
        EveOreType.objects.bulk_get_or_create_esi(
            ids=[record["type_id"] for record in records]
        )

    def _store_ledger(self, records):
        character_2_user = {
            obj[0]: obj[1]
            for obj in CharacterOwnership.objects.values_list(
                "character__character_id",
                "user_id",
            )
        }
        entity_ids = set()
        for record in records:
            character, _ = EveEntity.objects.get_or_create(id=record["character_id"])
            corporation, _ = EveEntity.objects.get_or_create(
                id=record["recorded_corporation_id"]
            )
            entity_ids.add(character.id)
            entity_ids.add(corporation.id)
            MiningLedgerRecord.objects.update_or_create(
                refinery=self,
                character=character,
                day=record["last_updated"],
                ore_type_id=record["type_id"],
                defaults={
                    "corporation": corporation,
                    "quantity": record["quantity"],
                    "user_id": character_2_user.get(character.id),
                },
            )

        try:
            EveEntity.objects.bulk_resolve_ids(entity_ids)
        except OSError:
            logger.warning(
                "%s: Failed to resolve entity IDs for mining ledger: %s",
                self,
                entity_ids,
                exc_info=True,
            )

    def _record_successful_update(self):
        self.ledger_last_update_ok = True
        self.save()

    def create_extractions_from_esi_response(self, esi_extractions: List[dict]) -> int:
        """Create extractions from an ESI repose and return number of created objs."""
        existing_extractions = set(
            self.extractions.values_list("started_at", flat=True)
        )
        new_extractions = []
        for esi_extraction in esi_extractions:
            extraction_start_time = esi_extraction["extraction_start_time"]
            if extraction_start_time not in existing_extractions:
                chunk_arrival_time = esi_extraction["chunk_arrival_time"]
                auto_fracture_at = esi_extraction["natural_decay_time"]
                if now() > auto_fracture_at:
                    status = Extraction.Status.COMPLETED
                elif now() > chunk_arrival_time:
                    status = Extraction.Status.READY
                else:
                    status = Extraction.Status.STARTED
                new_extractions.append(
                    Extraction(
                        refinery=self,
                        chunk_arrival_at=esi_extraction["chunk_arrival_time"],
                        started_at=extraction_start_time,
                        status=status,
                        auto_fracture_at=auto_fracture_at,
                    )
                )
        if new_extractions:
            Extraction.objects.bulk_create(new_extractions, batch_size=500)
        return len(new_extractions)

    def cancel_started_extractions_missing_from_list(
        self, started_at_list: List[dt.datetime]
    ) -> int:
        """Cancel started extractions that are not included in given list."""
        canceled_extractions_qs = self.extractions.filter(
            status=Extraction.Status.STARTED
        ).exclude(started_at__in=started_at_list)
        canceled_extractions_count = canceled_extractions_qs.count()
        if canceled_extractions_count:
            logger.info(
                "%s: Found %d likely canceled extractions.",
                self,
                canceled_extractions_count,
            )
            canceled_extractions_qs.update(
                status=Extraction.Status.CANCELED, canceled_at=now()
            )
        return canceled_extractions_count


def _update_extractions_for_refinery(owner: Owner, refinery: Refinery):
    notifications_for_refinery = owner.notifications.filter(
        details__structureID=refinery.id
    )
    if not refinery.moon and notifications_for_refinery.exists():
        # Update the refinery's moon from notification in case
        # it was not found by nearest_celestial.
        notif = notifications_for_refinery.first()
        refinery.update_moon_from_eve_id(notif.details["moonID"])

    extraction, updated_count = _find_extraction_for_refinery(
        refinery, notifications_for_refinery
    )
    if extraction:
        updated = Extraction.objects.update_from_calculated(extraction)
        updated_count += 1 if updated else 0

    if updated_count:
        logger.info(
            "%s: %s: Updated %d extractions from notifications",
            owner,
            refinery,
            updated_count,
        )


def _find_extraction_for_refinery(
    refinery: Refinery,
    notifications_for_refinery: models.QuerySet["Notification"],
) -> Tuple[Optional[CalculatedExtraction], int]:
    extraction: Optional[CalculatedExtraction] = None
    updated_count = 0
    for notif in notifications_for_refinery.order_by("timestamp"):
        if notif.notif_type == NotificationType.MOONMINING_EXTRACTION_STARTED:
            extraction = notif.to_calculated_extraction()
            if refinery.moon.update_products_from_calculated_extraction(
                extraction,
                overwrite_survey=MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES,
            ):
                logger.info("%s: Products updated from extraction", refinery.moon)

        elif extraction:
            if extraction.status == CalculatedExtraction.Status.STARTED:
                if notif.notif_type == NotificationType.MOONMINING_EXTRACTION_CANCELLED:
                    extraction.status = CalculatedExtraction.Status.CANCELED
                    extraction.canceled_at = notif.timestamp
                    extraction.canceled_by = notif.details.get("cancelledBy")
                    updated = Extraction.objects.update_from_calculated(extraction)
                    updated_count += 1 if updated else 0
                    extraction = None

                elif (
                    notif.notif_type == NotificationType.MOONMINING_EXTRACTION_FINISHED
                ):
                    extraction.status = CalculatedExtraction.Status.READY
                    extraction.products = (
                        CalculatedExtractionProduct.create_list_from_dict(
                            notif.details["oreVolumeByType"]
                        )
                    )

            elif extraction.status == CalculatedExtraction.Status.READY:
                if notif.notif_type == NotificationType.MOONMINING_LASER_FIRED:
                    extraction.status = CalculatedExtraction.Status.COMPLETED
                    extraction.fractured_at = notif.timestamp
                    extraction.fractured_by = notif.details.get("firedBy")
                    extraction.products = (
                        CalculatedExtractionProduct.create_list_from_dict(
                            notif.details["oreVolumeByType"]
                        )
                    )
                    updated = Extraction.objects.update_from_calculated(extraction)
                    updated_count += 1 if updated else 0
                    extraction = None

                elif notif.notif_type == NotificationType.MOONMINING_AUTOMATIC_FRACTURE:
                    extraction.status = CalculatedExtraction.Status.COMPLETED
                    extraction.fractured_at = notif.timestamp
                    extraction.products = (
                        CalculatedExtractionProduct.create_list_from_dict(
                            notif.details["oreVolumeByType"]
                        )
                    )
                    updated = Extraction.objects.update_from_calculated(extraction)
                    updated_count += 1 if updated else 0
                    extraction = None
        else:
            if notif.notif_type == NotificationType.MOONMINING_EXTRACTION_FINISHED:
                extraction = notif.to_calculated_extraction()

    return extraction, updated_count
