"""Extraction models."""

import datetime as dt
from typing import Iterable, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from eveuniverse.models import EveEntity, EveType

from app_utils.views import BootstrapStyleBS5

from moonmining.app_settings import MOONMINING_REPROCESSING_YIELD
from moonmining.constants import EveDogmaAttributeId, EveGroupId
from moonmining.core import CalculatedExtraction, CalculatedExtractionProduct
from moonmining.helpers import bootstrap5_label_html
from moonmining.managers import EveOreTypeManger, ExtractionManager
from moonmining.models.notifications import NotificationType


class OreQualityClass(models.TextChoices):
    """Quality class of an ore"""

    UNDEFINED = "UN", _("undefined")
    REGULAR = "RE", _("regular")
    IMPROVED = "IM", _("improved")
    EXCELLENT = "EX", _("excellent")

    @property
    def bootstrap_tag_html(self) -> str:
        """Return bootstrap tag."""
        map_quality_to_label_def = {
            self.IMPROVED: {"text": "+15%", "label": BootstrapStyleBS5.SUCCESS},
            self.EXCELLENT: {"text": "+100%", "label": BootstrapStyleBS5.WARNING},
        }
        try:
            label_def = map_quality_to_label_def[self]
            return bootstrap5_label_html(label_def["text"], label=label_def["label"])
        except KeyError:
            return ""

    @classmethod
    def from_eve_type(cls, eve_type: EveType) -> "OreQualityClass":
        """Create object from given eve type."""
        map_value_2_quality_class = {
            1: cls.REGULAR,
            3: cls.IMPROVED,
            5: cls.EXCELLENT,
        }
        try:
            dogma_attribute = eve_type.dogma_attributes.get(
                eve_dogma_attribute_id=EveDogmaAttributeId.ORE_QUALITY
            )
        except ObjectDoesNotExist:
            return cls.UNDEFINED
        try:
            return map_value_2_quality_class[int(dogma_attribute.value)]
        except KeyError:
            return cls.UNDEFINED


class Extraction(models.Model):
    """A mining extraction."""

    class Status(models.TextChoices):
        """An extraction status."""

        STARTED = "ST", _("started")  # has been started
        CANCELED = "CN", _("canceled")  # has been canceled
        READY = "RD", _("ready")  # has finished extraction and is ready to be fractured
        COMPLETED = "CP", _("completed")  # has been fractured
        UNDEFINED = "UN", _("undefined")  # unclear status

        @property
        def bootstrap_tag_html(self) -> str:
            """Return HTML to render as bootstrap tag."""
            map_to_type = {
                self.STARTED: BootstrapStyleBS5.SUCCESS,
                self.CANCELED: BootstrapStyleBS5.DANGER,
                self.READY: BootstrapStyleBS5.WARNING,
                self.COMPLETED: BootstrapStyleBS5.PRIMARY,
                self.UNDEFINED: "",
            }
            try:
                return bootstrap5_label_html(self.label, label=map_to_type[self].value)
            except KeyError:
                return ""

        @property
        def to_notification_type(self) -> NotificationType:
            """Return notification type."""
            map_to_type = {
                self.STARTED: NotificationType.MOONMINING_EXTRACTION_STARTED,
                self.CANCELED: NotificationType.MOONMINING_EXTRACTION_CANCELLED,
                self.READY: NotificationType.MOONMINING_EXTRACTION_FINISHED,
                self.COMPLETED: NotificationType.MOONMINING_LASER_FIRED,
            }
            try:
                return map_to_type[self]
            except KeyError:
                raise ValueError("Invalid status for notification type") from None

        @classmethod
        def considered_active(cls):
            """Return enums considered active."""
            return [cls.STARTED, cls.READY]

        @classmethod
        def considered_inactive(cls):
            """Return enums considered inactive."""
            return [cls.CANCELED, cls.COMPLETED]

        @classmethod
        def from_calculated(cls, calculated: CalculatedExtraction):
            """Create new eum from calculated status."""
            map_from_calculated = {
                CalculatedExtraction.Status.STARTED: cls.STARTED,
                CalculatedExtraction.Status.CANCELED: cls.CANCELED,
                CalculatedExtraction.Status.READY: cls.READY,
                CalculatedExtraction.Status.COMPLETED: cls.COMPLETED,
                CalculatedExtraction.Status.UNDEFINED: cls.UNDEFINED,
            }
            try:
                return map_from_calculated[calculated.status]
            except KeyError:
                return cls.UNDEFINED

    # PK
    refinery = models.ForeignKey(
        "Refinery", on_delete=models.CASCADE, related_name="extractions"
    )
    started_at = models.DateTimeField(
        db_index=True, help_text=_("When this extraction was started")
    )
    # normal properties
    auto_fracture_at = models.DateTimeField(
        help_text=_("When this extraction will be automatically fractured"),
    )
    canceled_at = models.DateTimeField(
        null=True, default=None, help_text=_("When this extraction was canceled")
    )
    canceled_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who canceled this extraction"),
    )
    chunk_arrival_at = models.DateTimeField(
        db_index=True, help_text=_("When this extraction is ready to be fractured")
    )
    fractured_at = models.DateTimeField(
        null=True, default=None, help_text=_("When this extraction was fractured")
    )
    fractured_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who fractured this extraction (if any)"),
    )
    is_jackpot = models.BooleanField(
        default=None,
        null=True,
        help_text=_("Whether this is a jackpot extraction (calculated)"),
    )
    started_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who started this extraction"),
    )
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.UNDEFINED, db_index=True
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        help_text=_("Estimated value of this extraction (calculated)"),
    )

    objects = ExtractionManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refinery", "started_at"], name="functional_pk_extraction"
            )
        ]
        verbose_name = _("extraction")
        verbose_name_plural = _("extractions")

    def __str__(self) -> str:
        return f"{self.refinery} - {self.started_at} - {self.status}"

    @property
    def duration(self) -> dt.timedelta:
        """Duration of this extraction."""
        return self.chunk_arrival_at - self.started_at

    @property
    def duration_in_days(self) -> float:
        """Duration of this extraction in days."""
        return self.duration.total_seconds() / (60 * 60 * 24)

    @property
    def status_enum(self) -> "Extraction.Status":
        """Return current status as enum type."""
        return self.Status(self.status)

    def products_sorted(self) -> models.QuerySet:
        """Return current products."""
        try:
            return (
                self.products.select_related(
                    "ore_type", "ore_type__eve_group", "ore_type__extras"
                )
                .annotate(total_price=self._total_price_db_func())
                .order_by("ore_type__name")
            )
        except (ObjectDoesNotExist, AttributeError):
            return type(self).objects.none()

    @cached_property
    def ledger(self) -> models.QuerySet:
        """Return ledger for this extraction."""
        max_day = self.chunk_arrival_at + dt.timedelta(days=6)
        return self.refinery.mining_ledger.filter(
            day__gte=self.chunk_arrival_at,
            day__lte=max_day,
        )

    def calc_value(self) -> Optional[float]:
        """Calculate value estimate."""
        try:
            return self.products.select_related(
                "ore_type", "ore_type__extras"
            ).aggregate(total_price=self._total_price_db_func())["total_price"]
        except (ObjectDoesNotExist, KeyError, AttributeError):
            return None

    @staticmethod
    def _total_price_db_func():
        return Sum(
            Coalesce(F("ore_type__extras__current_price"), 0.0)
            * F("volume")
            / F("ore_type__volume"),
            output_field=models.FloatField(),
        )

    def calc_is_jackpot(self) -> Optional[bool]:
        """Calculate if extraction is jackpot and return result.
        Return None if extraction has no products.
        """
        try:
            products_qualities = [
                product.ore_type.quality_class == OreQualityClass.EXCELLENT
                for product in self.products.select_related("ore_type").all()
            ]
        except (ObjectDoesNotExist, AttributeError):
            return None

        if not products_qualities:
            return None
        return all(products_qualities)

    def update_calculated_properties(self) -> None:
        """Update calculated properties for this extraction."""
        self.value = self.calc_value()
        self.is_jackpot = self.calc_is_jackpot()
        self.save()

    def to_calculated_extraction(self) -> CalculatedExtraction:
        """Generate a calculated extraction from this extraction."""

        def _products_to_calculated_products():
            return [
                CalculatedExtractionProduct(
                    ore_type_id=obj.ore_type_id, volume=obj.volume
                )
                for obj in self.products.all()
            ]

        params = {"refinery_id": self.refinery_id}
        if self.status == self.Status.STARTED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.STARTED,
                    "chunk_arrival_at": self.chunk_arrival_at,
                    "auto_fracture_at": self.auto_fracture_at,
                    "started_at": self.started_at,
                    "started_by": self.started_by,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.READY:
            params.update(
                {
                    "status": CalculatedExtraction.Status.READY,
                    "auto_fracture_at": self.auto_fracture_at,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.COMPLETED:
            params.update(
                {
                    "fractured_by": self.fractured_by,
                    "fractured_at": self.fractured_at,
                    "status": CalculatedExtraction.Status.COMPLETED,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.CANCELED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.CANCELED,
                    "canceled_at": self.canceled_at,
                    "canceled_by": self.canceled_by,
                }
            )
        return CalculatedExtraction(**params)


class OreRarityClass(models.IntegerChoices):
    """Rarity class of an ore"""

    NONE = 0, ""
    R4 = 4, _("R 4")
    R8 = 8, _("R 8")
    R16 = 16, _("R16")
    R32 = 32, _("R32")
    R64 = 64, _("R64")

    @property
    def bootstrap_tag_html(self) -> str:
        """Return as bootstrap tag HTML."""
        map_rarity_to_type = {
            self.R4: BootstrapStyleBS5.PRIMARY,
            self.R8: BootstrapStyleBS5.INFO,
            self.R16: BootstrapStyleBS5.SUCCESS,
            self.R32: BootstrapStyleBS5.WARNING,
            self.R64: BootstrapStyleBS5.DANGER,
        }
        try:
            return bootstrap5_label_html(
                f"R{self.value}", label=map_rarity_to_type[self].value
            )
        except KeyError:
            return ""

    @classmethod
    def from_eve_group_id(cls, eve_group_id: int) -> "OreRarityClass":
        """Create object from eve group ID"""
        map_group_2_rarity = {
            EveGroupId.UBIQUITOUS_MOON_ASTEROIDS.value: cls.R4,
            EveGroupId.COMMON_MOON_ASTEROIDS.value: cls.R8,
            EveGroupId.UNCOMMON_MOON_ASTEROIDS.value: cls.R16,
            EveGroupId.RARE_MOON_ASTEROIDS.value: cls.R32,
            EveGroupId.EXCEPTIONAL_MOON_ASTEROIDS.value: cls.R64,
        }
        try:
            return map_group_2_rarity[eve_group_id]
        except KeyError:
            return cls.NONE

    @classmethod
    def from_eve_type(cls, eve_type: EveType) -> "OreRarityClass":
        """Create object from eve type"""
        return cls.from_eve_group_id(eve_type.eve_group_id)


class EveOreType(EveType):
    """Subset of EveType for all ore types.

    Ensures TYPE_MATERIALS and DOGMAS is always enabled and allows adding methods to types.
    """

    class Meta:
        proxy = True
        verbose_name = _("ore type")
        verbose_name_plural = _("ore types")

    objects = EveOreTypeManger()

    @property
    def icon_url_32(self) -> str:
        """Return icon URL with 32 pixel width."""
        return self.icon_url(32)

    @property
    def rarity_class(self) -> OreRarityClass:
        """Return rarity class."""
        return OreRarityClass.from_eve_type(self)

    @cached_property
    def quality_class(self) -> OreQualityClass:
        """Return quality class."""
        return OreQualityClass.from_eve_type(self)

    @cached_property
    def price(self) -> float:
        """Return calculated price estimate in ISK per unit."""
        result = self.extras.current_price
        return result if result is not None else 0.0

    def price_by_volume(self, volume: int) -> Optional[float]:
        """Return calculated price estimate in ISK for volume in m3."""
        return self.price_by_units(int(volume // self.volume)) if self.volume else None

    def price_by_units(self, units: int) -> float:
        """Return calculated price estimate in ISK for units."""
        return self.price * units

    def calc_refined_value_per_unit(
        self, reprocessing_yield: Optional[float] = None
    ) -> float:
        """Calculate the refined total value per unit and return it."""
        if not reprocessing_yield:
            reprocessing_yield = MOONMINING_REPROCESSING_YIELD
        units = 10000
        r_units = units / 100
        value = 0
        for type_material in self.materials.select_related(
            "material_eve_type__market_price"
        ):
            try:
                price = type_material.material_eve_type.market_price.average_price
            except (ObjectDoesNotExist, AttributeError):
                continue
            if price:
                value += price * type_material.quantity * r_units * reprocessing_yield
        return value / units

    @classmethod
    def _enabled_sections_union(cls, enabled_sections: Iterable[str]) -> set:
        """Return enabled sections with TYPE_MATERIALS and DOGMAS always enabled."""
        enabled_sections = super()._enabled_sections_union(
            enabled_sections=enabled_sections
        )
        enabled_sections.add(cls.Section.TYPE_MATERIALS)
        enabled_sections.add(cls.Section.DOGMAS)
        return enabled_sections


class ExtractionProduct(models.Model):
    """A product within a mining extraction."""

    extraction = models.ForeignKey(
        Extraction, on_delete=models.CASCADE, related_name="products"
    )
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")

    volume = models.FloatField(validators=[MinValueValidator(0.0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["extraction", "ore_type"],
                name="functional_pk_extractionproduct",
            )
        ]
        verbose_name = _("extraction product")
        verbose_name_plural = _("extractions products")

    def __str__(self) -> str:
        return f"{self.extraction} - {self.ore_type}"


class EveOreTypeExtras(models.Model):
    """Extra fields for an EveOreType, e.g. for pricing calculations."""

    class PricingMethod(models.TextChoices):
        """A pricing method."""

        UNKNOWN = "UN", _("Undefined")
        EVE_CLIENT = "EC", _("Eve client")
        REPROCESSED_MATERIALS = "RP", _("Reprocessed materials")

    ore_type = models.OneToOneField(
        EveOreType, on_delete=models.CASCADE, related_name="extras"
    )
    current_price = models.FloatField(
        default=None,
        null=True,
        help_text=_("Price used by all price calculations with this type"),
    )
    pricing_method = models.CharField(
        max_length=2, choices=PricingMethod.choices, default=PricingMethod.UNKNOWN
    )

    class Meta:
        verbose_name = _("ore type extra")
        verbose_name_plural = _("ore type extras")

    def __str__(self) -> str:
        return str(self.ore_type)
