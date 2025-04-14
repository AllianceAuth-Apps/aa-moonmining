"""Moon models."""

from typing import List, Optional

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from eveuniverse.models import EveMoon, EveRegion, EveSolarSystem

from app_utils.views import BootstrapStyleBS5

from moonmining.app_settings import (
    MOONMINING_VOLUME_PER_DAY,
    MOONMINING_VOLUME_PER_MONTH,
)
from moonmining.core import CalculatedExtraction
from moonmining.helpers import bootstrap5_label_html
from moonmining.managers import MoonManager
from moonmining.models.extractions import EveOreType, OreRarityClass


class Label(models.Model):
    """A custom label for structuring moons."""

    class Style(models.TextChoices):
        """A label style."""

        DARK_BLUE = "primary", _("dark blue")
        GREEN = "success", _("green")
        GREY = "default", _("grey")
        LIGHT_BLUE = "info", _("light blue")
        ORANGE = "warning", _("orange")
        RED = "danger", _("red")

        @property
        def bootstrap_style(self) -> str:
            """Return HTML to render a bootstrap tag."""
            map_to_type = {
                self.DARK_BLUE: BootstrapStyleBS5.PRIMARY,
                self.GREEN: BootstrapStyleBS5.SUCCESS,
                self.LIGHT_BLUE: BootstrapStyleBS5.INFO,
                self.ORANGE: BootstrapStyleBS5.WARNING,
                self.RED: BootstrapStyleBS5.DANGER,
            }
            try:
                return map_to_type[self].value
            except KeyError:
                return BootstrapStyleBS5.DEFAULT

    description = models.TextField(default="", blank=True)
    name = models.CharField(max_length=100, unique=True)
    style = models.CharField(max_length=16, choices=Style.choices, default=Style.GREY)

    class Meta:
        verbose_name = _("label")
        verbose_name_plural = _("labels")

    def __str__(self) -> str:
        return self.name

    @property
    def tag_html(self) -> str:
        """Return tag HTML for this obj."""
        label_style = self.Style(self.style).bootstrap_style
        return bootstrap5_label_html(self.name, label=label_style)


class Moon(models.Model):
    """Known moon through either survey data or anchored refinery.

    "Head" model for many of the other models.
    """

    # pk
    eve_moon = models.OneToOneField(
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    # regular
    label = models.ForeignKey(
        Label, on_delete=models.SET_DEFAULT, default=None, null=True
    )
    products_updated_at = models.DateTimeField(
        null=True, default=None, help_text=_("Time the last moon survey was uploaded")
    )
    products_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        help_text=_("User who uploaded the last moon survey"),
    )
    rarity_class = models.PositiveIntegerField(
        choices=OreRarityClass.choices, default=OreRarityClass.NONE
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        db_index=True,
        help_text=_("Calculated value estimate"),
    )

    objects = MoonManager()

    class Meta:
        verbose_name = _("moon")
        verbose_name_plural = _("moons")

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """Return name of this moon."""
        return self.eve_moon.name.replace("Moon ", "")

    def region(self) -> EveRegion:
        """Return region."""
        return self.solar_system().eve_constellation.eve_region

    def solar_system(self) -> EveSolarSystem:
        """Return solar system."""
        return self.eve_moon.eve_planet.eve_solar_system

    @property
    def is_owned(self) -> bool:
        """Return True when this moon has a known owner, else False."""
        return hasattr(self, "refinery")

    @property
    def rarity_tag_html(self) -> str:
        """Return rarity tag HTML for this moon."""
        return OreRarityClass(self.rarity_class).bootstrap_tag_html

    def labels_html(self) -> str:
        """Generate HTML with all labels."""
        tags = [self.rarity_tag_html]
        if self.label:
            tags.append(self.label.tag_html)
        return format_html(" ".join(tags))

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

    def calc_rarity_class(self) -> Optional[OreRarityClass]:
        """Return rarity class of this moon."""
        try:
            return max(
                OreRarityClass.from_eve_group_id(eve_group_id)
                for eve_group_id in self.products.select_related(
                    "ore_type"
                ).values_list("ore_type__eve_group_id", flat=True)
            )
        except (ObjectDoesNotExist, ValueError):
            return OreRarityClass.NONE

    def calc_value(self) -> Optional[float]:
        """Calculate value estimate."""
        try:
            return self.products.aggregate(total_value=self._total_price_db_func())[
                "total_value"
            ]
        except (ObjectDoesNotExist, KeyError, AttributeError):
            return None

    @staticmethod
    def _total_price_db_func():
        return Sum(
            Coalesce(F("ore_type__extras__current_price"), 0.0)
            * F("amount")
            * Value(float(MOONMINING_VOLUME_PER_MONTH))
            / F("ore_type__volume"),
            output_field=models.FloatField(),
        )

    def update_calculated_properties(self):
        """Update all calculated properties for this moon."""
        self.value = self.calc_value()
        self.rarity_class = self.calc_rarity_class()
        self.save()

    def update_products(
        self, moon_products: List["MoonProduct"], updated_by: Optional[User] = None
    ) -> None:
        """Update products of this moon."""
        with transaction.atomic():
            self.products.all().delete()
            MoonProduct.objects.bulk_create(moon_products, batch_size=500)
        self.products_updated_at = now()
        self.products_updated_by = updated_by
        self.update_calculated_properties()

    def update_products_from_calculated_extraction(
        self, extraction: CalculatedExtraction, overwrite_survey: bool = False
    ) -> bool:
        """Replace moon product with calculated values from this extraction.

        Returns True if update was done, else False
        """
        if extraction.products and (
            overwrite_survey or self.products_updated_by is None
        ):
            moon_products = [
                MoonProduct(
                    moon=self,
                    amount=product.amount,
                    ore_type=EveOreType.objects.get_or_create_esi(
                        id=product.ore_type_id
                    )[0],
                )
                for product in extraction.moon_products_estimated(
                    MOONMINING_VOLUME_PER_DAY
                )
            ]
            self.update_products(moon_products)
            return True
        return False

    def update_products_from_latest_extraction(
        self, overwrite_survey: bool = False
    ) -> Optional[bool]:
        """Update products from latest extractions and return if successful."""
        try:
            extraction = self.refinery.extractions.order_by("-started_at").first()
        except ObjectDoesNotExist:
            return None

        if not extraction:
            return None

        success = self.update_products_from_calculated_extraction(
            extraction.to_calculated_extraction(), overwrite_survey=overwrite_survey
        )
        return success


class MoonProduct(models.Model):
    """A product of a moon, i.e. a specific ore."""

    moon = models.ForeignKey(Moon, on_delete=models.CASCADE, related_name="products")
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")

    amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    def __str__(self):
        return f"{self.ore_type.name} - {self.amount}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["moon", "ore_type"], name="functional_pk_moonproduct"
            )
        ]
        verbose_name = _("moon product")
        verbose_name_plural = _("moons products")

    @property
    def amount_percent(self) -> float:
        """Return the amount of this product as percent"""
        return self.amount * 100
