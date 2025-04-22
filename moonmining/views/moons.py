"""Moon views."""

from enum import Enum
from typing import Union

from django_datatables_view.base_datatable_view import BaseDatatableView

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Case, F, OuterRef, Q, QuerySet, Subquery, Value, When
from django.db.models.functions import Concat
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from allianceauth.eveonline.evelinks import dotlan
from app_utils.views import link_html

from moonmining import helpers, tasks
from moonmining.app_settings import (
    MOONMINING_REPROCESSING_YIELD,
    MOONMINING_USE_REPROCESS_PRICING,
    MOONMINING_VOLUME_PER_MONTH,
)
from moonmining.forms import MoonScanForm
from moonmining.helpers import user_perms_lookup
from moonmining.models import Extraction, Moon, MoonProduct
from moonmining.views._helpers import moon_details_button_html
from moonmining.views.extractions import extraction_details_button_html


class MoonsCategory(str, helpers.EnumToDict, Enum):
    """A category defining which moons to show in data view."""

    ALL = "all_moons"
    UPLOADS = "uploads"
    OURS = "our_moons"


# pylint: disable = too-many-ancestors
class MoonListJson(PermissionRequiredMixin, LoginRequiredMixin, BaseDatatableView):
    """A datatable view for rendering a moons list."""

    model = Moon
    permission_required = "moonmining.basic_access"
    columns = [
        "id",
        "moon_name",
        "rarity_class_str",
        "refinery",
        "labels",
        "solar_system_link",
        "location_html",
        "region_name",
        "constellation_name",
        "value",
        "details",
        "has_refinery_str",
        "has_extraction_str",
        "solar_system_name",
        "corporation_name",
        "alliance_name",
        "has_refinery",
        "label_name",
        "ore_type_dummy",
    ]

    # define column names that will be used in sorting
    # order is important and should be same as order of columns
    # displayed by datatables. For non sortable columns use empty
    # value like ''
    order_columns = [
        "eve_moon__name",
        "eve_moon__eve_planet__eve_solar_system__name",
        "eve_moon__eve_planet__eve_solar_system__eve_constellation__name",
        "refinery__name",
        "",
        "value",
        "",
    ]

    def get_initial_queryset(self) -> QuerySet:
        return self.initial_queryset(
            category=self.kwargs["category"], user=self.request.user
        )

    @classmethod
    def initial_queryset(cls, category: str, user: User) -> QuerySet:
        """Return initial queryset."""
        current_extraction_qs = Extraction.objects.filter(
            refinery__moon=OuterRef("pk"),
            status__in=[Extraction.Status.STARTED, Extraction.Status.READY],
        )
        moon_query = (
            Moon.objects.selected_related_defaults()
            .annotate(extraction_pk=Subquery(current_extraction_qs.values("pk")[:1]))
            .annotate(
                has_refinery=Case(
                    When(refinery__isnull=True, then=Value(False)), default=Value(True)
                )
            )
            .annotate(
                has_refinery_str=Case(
                    When(has_refinery=False, then=Value("no")), default=Value("yes")
                )
            )
            .annotate(
                has_extraction=Case(
                    When(extraction_pk__isnull=True, then=Value(False)),
                    default=Value(True),
                )
            )
            .annotate(
                has_extraction_str=Case(
                    When(has_extraction=False, then=Value("no")), default=Value("yes")
                )
            )
            .annotate(
                rarity_class_str=Concat(
                    Value("R"), F("rarity_class"), output_field=models.CharField()
                )
            )
        )

        moons_category = MoonsCategory(category)
        if moons_category is MoonsCategory.ALL and user.has_perm(
            "moonmining.view_all_moons"
        ):
            return moon_query

        if (
            moons_category is MoonsCategory.OURS
            and user.has_perm("moonmining.extractions_access")
            or user.has_perm("moonmining.view_all_moons")
        ):
            return moon_query.filter(refinery__isnull=False)

        if moons_category is MoonsCategory.UPLOADS and user.has_perm(
            "moonmining.upload_moon_scan"
        ):
            return moon_query.filter(products_updated_by=user)

        return Moon.objects.none()

    def filter_queryset(self, qs: QuerySet) -> QuerySet:
        """use parameters passed in GET request to filter queryset"""

        qs = self._apply_search_filter(
            qs, 7, "eve_moon__eve_planet__eve_solar_system__name"
        )
        qs = self._apply_search_filter(qs, 8, "has_refinery_str")
        qs = self._apply_search_filter(
            qs, 9, "refinery__owner__corporation__corporation_name"
        )
        qs = self._apply_search_filter(
            qs, 10, "refinery__owner__corporation__alliance__alliance_name"
        )
        qs = self._apply_search_filter(qs, 11, "rarity_class_str")
        qs = self._apply_search_filter(qs, 12, "has_extraction_str")
        qs = self._apply_search_filter(
            qs, 13, "eve_moon__eve_planet__eve_solar_system__eve_constellation__name"
        )
        qs = self._apply_search_filter(qs, 14, "label__name")
        qs = self._apply_search_filter(
            qs,
            15,
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region__name",
        )

        if ore_type_name := self.request.GET.get("columns[16][search][value]"):
            if ore_type_name := ore_type_name.removeprefix("^").removesuffix("$"):
                qs = qs.filter(products__ore_type__name__in=[ore_type_name])

        if search := self.request.GET.get("search[value]", None):
            qs = qs.filter(
                Q(eve_moon__name__istartswith=search)
                | Q(refinery__name__istartswith=search)
            )
        return qs

        # qs = self._apply_search_filter(qs, 4, "user__profile__state__name")
        # qs = self._apply_search_filter(qs, 6, "character__alliance_name")
        # qs = self._apply_search_filter(qs, 7, "character__corporation_name")
        # qs = self._apply_search_filter(
        #     qs, 8, "user__profile__main_character__alliance_name"
        # )
        # qs = self._apply_search_filter(
        #     qs, 9, "user__profile__main_character__corporation_name"
        # )
        # qs = self._apply_search_filter(
        #     qs, 10, "user__profile__main_character__character_name"
        # )
        # qs = self._apply_search_filter(qs, 11, "unregistered")

        # return qs

    def _apply_search_filter(
        self, qs: QuerySet, column_num: int, field: str
    ) -> QuerySet:
        my_filter = self.request.GET.get(f"columns[{column_num}][search][value]", None)
        if not my_filter:
            return qs

        if self.request.GET.get(f"columns[{column_num}][search][regex]", False):
            kwargs = {f"{field}__iregex": my_filter}
        else:
            kwargs = {f"{field}__istartswith": my_filter}
        return qs.filter(**kwargs)

    # pylint: disable = too-many-return-statements
    def render_column(self, row, column) -> Union[str, dict]:
        if column == "id":
            return row.pk

        if column == "moon_name":
            return row.name

        if result := self._render_location(row, column):
            return result

        if column == "labels":
            return row.labels_html()

        if column == "label_name":
            return row.label.name if row.label else ""

        if column == "details":
            return self._render_details(row)

        if result := self._render_refinery(row, column):
            return result

        if column == "ore_type_dummy":
            return ""

        return super().render_column(row, column)

    def _render_location(self, row, column):
        solar_system = row.eve_moon.eve_planet.eve_solar_system
        if solar_system.is_high_sec:
            sec_class = "text-high-sec"
        elif solar_system.is_low_sec:
            sec_class = "text-low-sec"
        else:
            sec_class = "text-null-sec"

        solar_system_link = format_html(
            '{}&nbsp;<span class="{}">{}</span>',
            link_html(dotlan.solar_system_url(solar_system.name), solar_system.name),
            sec_class,
            round(solar_system.security_status, 1),
        )
        constellation = row.eve_moon.eve_planet.eve_solar_system.eve_constellation
        region = constellation.eve_region
        location_html = format_html(
            "{}<br><em>{}</em>", constellation.name, region.name
        )
        if column == "solar_system_name":
            return solar_system.name

        if column == "solar_system_link":
            return solar_system_link

        if column == "location_html":
            return location_html

        if column == "region_name":
            return region.name

        if column == "constellation_name":
            return constellation.name

        return None

    def _render_details(self, row):
        details_html = ""
        if self.request.user.has_perm("moonmining.extractions_access"):
            details_html = (
                extraction_details_button_html(row.extraction_pk) + " "
                if row.extraction_pk
                else ""
            )
        details_html += moon_details_button_html(row)
        return details_html

    def _render_refinery(self, row, column) -> Union[str, dict]:
        if row.has_refinery:
            refinery = row.refinery
            refinery_html = refinery.name_html()
            refinery_name = refinery.name
            corporation_name = refinery.owner.name
            alliance_name = refinery.owner.alliance_name
        else:
            refinery_html = "?"
            refinery_name = ""
            corporation_name = alliance_name = ""

        if column == "corporation_name":
            return corporation_name

        if column == "alliance_name":
            return alliance_name

        if column == "refinery":
            return {"display": refinery_html, "sort": refinery_name}

        return ""


@login_required
@permission_required("moonmining.basic_access")
def moons_fdd_data(request: HttpRequest, category: str) -> JsonResponse:
    """Provide lists for drop down fields."""
    qs = MoonListJson.initial_queryset(category=category, user=request.user)
    result = {}
    if columns := request.GET.get("columns"):
        for column in columns.split(","):
            options = _calc_options(request, qs, column)
            result[column] = sorted(list(set(options)), key=str.casefold)
    return JsonResponse(result, safe=False)


# pylint: disable = too-many-return-statements
def _calc_options(request: HttpRequest, qs: QuerySet, column: str) -> QuerySet:
    if column == "alliance_name":
        return qs.exclude(
            refinery__owner__corporation__alliance__isnull=True,
        ).values_list(
            "refinery__owner__corporation__alliance__alliance_name", flat=True
        )

    if column == "corporation_name":
        return qs.exclude(refinery__isnull=True).values_list(
            "refinery__owner__corporation__corporation_name", flat=True
        )

    if column == "region_name":
        return qs.values_list(
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region__name",
            flat=True,
        )

    if column == "constellation_name":
        return qs.values_list(
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__name",
            flat=True,
        )

    if column == "solar_system_name":
        return qs.values_list(
            "eve_moon__eve_planet__eve_solar_system__name",
            flat=True,
        )

    if column == "rarity_class_str":
        return qs.values_list("rarity_class_str", flat=True)

    if column == "label_name":
        return qs.exclude(label__isnull=True).values_list("label__name", flat=True)

    if column == "has_refinery_str":
        return qs.values_list("has_refinery_str", flat=True)

    if column == "has_extraction_str":
        if request.user.has_perm("moonmining.extractions_access"):
            return qs.values_list("has_extraction_str", flat=True)
        return []

    if column == "ore_type_dummy":
        moon_ids = set(qs.values_list("eve_moon_id", flat=True))
        return (
            MoonProduct.objects.filter(moon_id__in=moon_ids)
            .select_related("ore_type")
            .values_list("ore_type__name", flat=True)
        )

    return [f"** ERROR: No options defined for column name '{column}' **"]


@login_required()
@permission_required("moonmining.basic_access")
def moons(request):
    """Render moons page."""
    user_perms = user_perms_lookup(
        request.user, ["moonmining.extractions_access", "moonmining.view_all_moons"]
    )
    context = {
        "page_title": _("Moons"),
        "MoonsCategory": MoonsCategory.to_dict(),
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
        "user_perms": user_perms,
    }
    return render(request, "moonmining/moons.html", context)


@login_required
@permission_required("moonmining.basic_access")
def moon_details(request, moon_pk: int):
    """Render moon details page."""
    moon = get_object_or_404(Moon.objects.selected_related_defaults(), pk=moon_pk)
    context = {
        "page_title": moon.name,
        "moon": moon,
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
    }
    if request.GET.get("new_page"):
        context["title"] = _("Moon")
        context["content_file"] = "moonmining/partials/moon_details.html"
        return render(request, "moonmining/_generic_modal_page.html", context)
    return render(request, "moonmining/modals/moon_details.html", context)


@permission_required(["moonmining.basic_access", "moonmining.upload_moon_scan"])
@login_required()
def upload_survey(request):
    """Render upload survey page."""
    context = {"page_title": _("Upload Moon Surveys")}
    if request.method == "POST":
        form = MoonScanForm(request.POST)
        if form.is_valid():
            scans = request.POST["scan"]
            tasks.process_survey_input.delay(scans, request.user.pk)
            messages.success(
                request,
                _(
                    "Your scan has been submitted for processing. "
                    "You will receive a notification once processing is complete."
                ),
            )
        else:
            messages.error(
                request,
                _(
                    "Oh No! Something went wrong with your moon scan submission. "
                    "Please try again."
                ),
            )
        return redirect("moonmining:moons")
    return render(request, "moonmining/modals/upload_survey.html", context=context)
