"""Extraction views."""

import datetime as dt
from enum import Enum

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import (
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    QuerySet,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from allianceauth.eveonline.evelinks import dotlan
from app_utils.views import link_html, yesno_str

from moonmining import helpers
from moonmining.app_settings import (
    MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE,
    MOONMINING_REPROCESSING_YIELD,
    MOONMINING_USE_REPROCESS_PRICING,
    MOONMINING_VOLUME_PER_MONTH,
)
from moonmining.constants import DATE_FORMAT, DATETIME_FORMAT
from moonmining.models import Extraction
from moonmining.views._helpers import (
    fontawesome_modal_button_html,
    moon_details_button_html,
)


class ExtractionsCategory(str, helpers.EnumToDict, Enum):
    """A category defining which extractions to show in data view."""

    UPCOMING = "upcoming"
    PAST = "past"


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extractions(request):
    """Render extractions page."""
    context = {
        "page_title": _("Extractions"),
        "ExtractionsCategory": ExtractionsCategory.to_dict(),
        "ExtractionsStatus": Extraction.Status,
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
        "stale_hours": MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE,
    }
    return render(request, "moonmining/extractions.html", context)


def extraction_ledger_button_html(extraction: Extraction) -> str:
    """Return HTML to render extraction ledger button."""
    new_var = fontawesome_modal_button_html(
        modal_id="modalExtractionLedger",
        fa_code="fas fa-table",
        ajax_url=reverse("moonmining:extraction_ledger", args=[extraction.pk]),
        tooltip="Extraction ledger",
    )
    return new_var


def extraction_details_button_html(extraction_pk: int) -> str:
    """Return HTML to render extraction details button."""
    html = fontawesome_modal_button_html(
        modal_id="modalExtractionDetails",
        fa_code="fas fa-hammer",
        ajax_url=reverse("moonmining:extraction_details", args=[extraction_pk]),
        tooltip=_("Extraction details"),
    )
    return html


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extractions_data(request: HttpRequest, category: str):
    """Render extraction data."""
    data = []
    can_see_ledger = request.user.has_perm("moonmining.view_moon_ledgers")
    extractions_qs = _calc_extractions_qs(ExtractionsCategory(category))
    for extraction in extractions_qs:
        moon = extraction.refinery.moon
        moon_name = str(moon)
        refinery_name = str(extraction.refinery.name)
        solar_system = moon.eve_moon.eve_planet.eve_solar_system
        location = format_html(
            "{}<br><i>{}</i>",
            link_html(dotlan.solar_system_url(solar_system.name), moon_name),
            solar_system.eve_constellation.eve_region.name,
        )

        if (
            extraction.status == Extraction.Status.COMPLETED
            and extraction.ledger.exists()
        ):
            mined_value = extraction.ledger.aggregate(Sum(F("total_price")))[
                "total_price__sum"
            ]
            actions_html = (
                extraction_ledger_button_html(extraction) + "&nbsp;"
                if can_see_ledger
                else ""
            )
        else:
            actions_html = ""
            mined_value = None

        actions_html += extraction_details_button_html(extraction.pk)
        actions_html += "&nbsp;" + moon_details_button_html(extraction.refinery.moon)
        status_html = format_html(
            "{}<br>{}",
            extraction.chunk_arrival_at.strftime(DATETIME_FORMAT),
            extraction.status_enum.bootstrap_tag_html,
        )
        data.append(
            {
                "id": extraction.pk,
                "chunk_arrival_at": {
                    "display": status_html,
                    "sort": extraction.chunk_arrival_at,
                },
                "refinery": {
                    "display": extraction.refinery.name_html(),
                    "sort": refinery_name,
                },
                "location": {
                    "display": location,
                    "sort": moon_name,
                },
                "labels": moon.labels_html(),
                "volume": extraction.volume,
                "value": extraction.value if extraction.value else None,
                "mined_value": mined_value,
                "details": actions_html,
                "corporation_name": extraction.refinery.owner.name,
                "alliance_name": extraction.refinery.owner.alliance_name,
                "moon_name": moon_name,
                "region_name": solar_system.eve_constellation.eve_region.name,
                "constellation_name": solar_system.eve_constellation.name,
                "rarity_class": moon.get_rarity_class_display(),
                "is_jackpot_str": yesno_str(extraction.is_jackpot),
                "is_ready": extraction.chunk_arrival_at <= now(),
                "status": extraction.status,
                "status_str": Extraction.Status(extraction.status).label,
            }
        )
    return JsonResponse(data, safe=False)


def _calc_extractions_qs(category: ExtractionsCategory) -> QuerySet[Extraction]:
    stale_cutoff = now() - dt.timedelta(
        hours=MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE
    )
    extractions_qs = (
        Extraction.objects.exclude(refinery__moon__isnull=True)
        .annotate_volume()
        .selected_related_defaults()
        .select_related(
            "refinery__moon__eve_moon__eve_planet__eve_solar_system",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        )
    )
    if category is ExtractionsCategory.UPCOMING:
        extractions_qs = extractions_qs.filter(
            auto_fracture_at__gte=stale_cutoff
        ).exclude(status=Extraction.Status.CANCELED)

    elif category is ExtractionsCategory.PAST:
        extractions_qs = extractions_qs.filter(
            auto_fracture_at__lt=stale_cutoff
        ) | extractions_qs.filter(status=Extraction.Status.CANCELED)

    else:
        extractions_qs = Extraction.objects.none()
    return extractions_qs


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extraction_details(request, extraction_pk: int):
    """Render a details view for an extraction."""
    extraction = get_object_or_404(
        Extraction.objects.annotate_volume().select_related(
            "refinery",
            "refinery__moon",
            "refinery__moon__eve_moon",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
            "canceled_by",
            "fractured_by",
            "started_by",
        ),
        pk=extraction_pk,
    )
    context = {
        "page_title": (
            f"{extraction.refinery.moon} "
            f"| {extraction.chunk_arrival_at.strftime(DATE_FORMAT)}"
        ),
        "extraction": extraction,
    }
    if request.GET.get("new_page"):
        context["title"] = _("Extraction")
        context["content_file"] = "moonmining/partials/extraction_details.html"
        return render(request, "moonmining/_generic_modal_page.html", context)

    return render(request, "moonmining/modals/extraction_details.html", context)


@login_required
@permission_required(
    [
        "moonmining.extractions_access",
        "moonmining.basic_access",
        "moonmining.view_moon_ledgers",
    ]
)
def extraction_ledger(request, extraction_pk: int):
    """Render extraction ledger page."""
    extraction = get_object_or_404(
        Extraction.objects.all().select_related(
            "refinery",
            "refinery__moon",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        ),
        pk=extraction_pk,
    )
    ledger = extraction.ledger.select_related(
        "character", "corporation", "user__profile__main_character", "ore_type"
    )
    total_value = ledger.aggregate(Sum(F("total_price")))["total_price__sum"]
    total_volume = ledger.aggregate(Sum(F("total_volume")))["total_volume__sum"]
    sum_price = ExpressionWrapper(
        F("quantity") * Coalesce(F("unit_price"), 0), output_field=FloatField()
    )
    sum_volume = ExpressionWrapper(
        F("quantity") * F("ore_type__volume"), output_field=IntegerField()
    )
    character_totals = (
        ledger.values(
            character_name=F("character__name"),
            main_name=F("user__profile__main_character__character_name"),
            corporation_name=F("user__profile__main_character__corporation_name"),
        )
        .annotate(character_total_price=Sum(sum_price, distinct=True))
        .annotate(character_total_volume=Sum(sum_volume, distinct=True))
        .annotate(
            character_percent_value=ExpressionWrapper(
                F("character_total_price") / Value(total_value) * Value(100),
                output_field=IntegerField(),
            )
        )
        .annotate(
            character_percent_volume=F("character_total_volume")
            / Value(total_volume)
            * Value(100)
        )
    )
    context = {
        "page_title": (
            f"{extraction.refinery.moon} "
            f"| {extraction.chunk_arrival_at.strftime(DATE_FORMAT)}"
        ),
        "extraction": extraction,
        "total_value": total_value,
        "total_volume": total_volume,
        "ledger": ledger,
        "character_totals": character_totals,
    }
    if request.GET.get("new_page"):
        context["title"] = _("Extraction Ledger")
        context["content_file"] = "moonmining/partials/extraction_ledger.html"
        return render(request, "moonmining/_generic_modal_page.html", context)
    return render(request, "moonmining/modals/extraction_ledger.html", context)
