"""Report views."""

import datetime as dt

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.db.models import Count, ExpressionWrapper, F, FloatField, Min, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html, strip_tags
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from moonmining.app_settings import (
    MOONMINING_REPROCESSING_YIELD,
    MOONMINING_USE_REPROCESS_PRICING,
    MOONMINING_VOLUME_PER_MONTH,
)
from moonmining.constants import EveGroupId
from moonmining.models import EveOreType, Moon, Refinery


def _previous_month(obj: dt.datetime) -> dt.datetime:
    first = obj.replace(day=1)
    return first - dt.timedelta(days=1)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def reports(request):
    """Render reports view."""
    month_minus_1 = _previous_month(now())
    month_minus_2 = _previous_month(month_minus_1)
    month_minus_3 = _previous_month(month_minus_2)
    month_format = "%b '%y"
    if (
        Refinery.objects.filter(
            owner__is_enabled=True, ledger_last_update_at__isnull=False
        )
        .exclude(ledger_last_update_ok=True)
        .exists()
    ):
        ledger_last_updated = None
    else:
        try:
            ledger_last_updated = Refinery.objects.filter(
                owner__is_enabled=True
            ).aggregate(Min("ledger_last_update_at"))["ledger_last_update_at__min"]
        except KeyError:
            ledger_last_updated = None
    context = {
        "page_title": _("Reports"),
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
        "month_minus_3": month_minus_3.strftime(month_format),
        "month_minus_2": month_minus_2.strftime(month_format),
        "month_minus_1": month_minus_1.strftime(month_format),
        "month_current": now().strftime(month_format),
        "ledger_last_updated": ledger_last_updated,
    }
    return render(request, "moonmining/reports.html", context)


def _moon_link_html(moon: Moon) -> str:
    return format_html(
        '<a href="#" data-bs-toggle="modal" '
        'data-bs-target="#modalMoonDetails" '
        'title="{}" '
        "data-ajax_url={}>"
        "{}</a>",
        _("Show details for this moon."),
        reverse("moonmining:moon_details", args=[moon.pk]),
        moon.name,
    )


def _default_if_none(value, default):
    """Return given default if value is None"""
    if value is None:
        return default
    return value


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_owned_value_data(request):
    """Render data view for owner value report."""
    moon_query = Moon.objects.select_related(
        "eve_moon",
        "eve_moon__eve_planet__eve_solar_system",
        "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        "refinery",
        "refinery__owner",
        "refinery__owner__corporation",
        "refinery__owner__corporation__alliance",
    ).filter(refinery__isnull=False)
    corporation_moons = {}
    for moon in moon_query.order_by("eve_moon__name"):
        corporation_name = moon.refinery.owner.name
        if corporation_name not in corporation_moons:
            corporation_moons[corporation_name] = {"moons": [], "total": 0}
        corporation_moons[corporation_name]["moons"].append(moon)
        corporation_moons[corporation_name]["total"] += _default_if_none(moon.value, 0)

    moon_ranks = {
        moon_pk: rank
        for rank, moon_pk in enumerate(
            moon_query.filter(value__isnull=False)
            .order_by("-value")
            .values_list("pk", flat=True)
        )
    }
    grand_total = sum(
        corporation["total"] for corporation in corporation_moons.values()
    )
    data = []
    for corporation_name, details in corporation_moons.items():
        corporation = f"{corporation_name} ({len(details['moons'])})"
        counter = 0
        for moon in details["moons"]:
            grand_total_percent = (
                _default_if_none(moon.value, 0) / grand_total * 100
                if grand_total > 0
                else None
            )
            rank = moon_ranks[moon.pk] + 1 if moon.pk in moon_ranks else None
            data.append(
                {
                    "corporation": corporation,
                    "moon": {"display": _moon_link_html(moon), "sort": counter},
                    "region": moon.region().name,
                    "rarity_class": moon.rarity_tag_html,
                    "value": moon.value,
                    "rank": rank,
                    "total": None,
                    "is_total": False,
                    "grand_total_percent": grand_total_percent,
                }
            )
            counter += 1
        data.append(
            {
                "corporation": corporation,
                "moon": {"display": _("Total"), "sort": counter},
                "region": None,
                "rarity_class": None,
                "value": None,
                "rank": None,
                "total": details["total"],
                "is_total": True,
                "grand_total_percent": None,
            }
        )
    return JsonResponse(data, safe=False)


def _default_if_false(value, default):
    """Return given default if value is False"""
    if not value:
        return default
    return value


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_user_mining_data(request):
    """Render data view for user mining report."""
    sum_volume = ExpressionWrapper(
        F("mining_ledger__quantity") * F("mining_ledger__ore_type__volume"),
        output_field=FloatField(),
    )
    sum_price = ExpressionWrapper(
        F("mining_ledger__quantity")
        * Coalesce(F("mining_ledger__ore_type__extras__current_price"), 0),
        output_field=FloatField(),
    )
    today = now()
    months_1 = today.replace(day=1) - dt.timedelta(days=1)
    months_2 = months_1.replace(day=1) - dt.timedelta(days=1)
    months_3 = months_2.replace(day=1) - dt.timedelta(days=1)
    users_mining_totals = (
        User.objects.filter(profile__main_character__isnull=False)
        .select_related("profile__main_character", "profile__state")
        .annotate(
            volume_month_0=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=today.month,
                    mining_ledger__day__year=today.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_1=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_1.month,
                    mining_ledger__day__year=months_1.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_2=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_2.month,
                    mining_ledger__day__year=months_2.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_3=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_3.month,
                    mining_ledger__day__year=months_3.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_0=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=today.month,
                    mining_ledger__day__year=today.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_1=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_1.month,
                    mining_ledger__day__year=months_1.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_2=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_2.month,
                    mining_ledger__day__year=months_2.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_3=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_3.month,
                    mining_ledger__day__year=months_3.year,
                ),
                distinct=True,
            )
        )
    )
    data = []
    for user in users_mining_totals:
        corporation_name = user.profile.main_character.corporation_name
        if user.profile.main_character.alliance_ticker:
            corporation_name += f" [{user.profile.main_character.alliance_ticker}]"
        if any(
            [
                user.volume_month_0,
                user.volume_month_1,
                user.volume_month_2,
                user.volume_month_3,
            ]
        ):
            data.append(
                {
                    "id": user.id,
                    "name": str(user.profile.main_character),
                    "corporation": corporation_name,
                    "state": str(user.profile.state),
                    "volume_month_0": _default_if_false(user.volume_month_0, 0),
                    "volume_month_1": _default_if_false(user.volume_month_1, 0),
                    "volume_month_2": _default_if_false(user.volume_month_2, 0),
                    "volume_month_3": _default_if_false(user.volume_month_3, 0),
                    "price_month_0": _default_if_false(user.price_month_0, 0),
                    "price_month_1": _default_if_false(user.price_month_1, 0),
                    "price_month_2": _default_if_false(user.price_month_2, 0),
                    "price_month_3": _default_if_false(user.price_month_3, 0),
                }
            )
    return JsonResponse(data, safe=False)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_user_uploaded_data(request) -> JsonResponse:
    """Render data view for user upload report."""
    data = list(
        Moon.objects.values(
            name=F("products_updated_by__profile__main_character__character_name"),
            corporation=F(
                "products_updated_by__profile__main_character__corporation_name"
            ),
            state=F("products_updated_by__profile__state__name"),
        ).annotate(num_moons=Count("eve_moon_id"))
    )
    for row in data:
        if row["name"] is None:
            row["name"] = "?"
        if row["corporation"] is None:
            row["corporation"] = "?"
        if row["state"] is None:
            row["state"] = "?"
    return JsonResponse(data, safe=False)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_ore_prices_data(request) -> JsonResponse:
    """Render data view for ore prices report."""
    moon_ore_group_ids = [
        EveGroupId.UNCOMMON_MOON_ASTEROIDS,
        EveGroupId.UBIQUITOUS_MOON_ASTEROIDS,
        EveGroupId.EXCEPTIONAL_MOON_ASTEROIDS,
        EveGroupId.COMMON_MOON_ASTEROIDS,
        EveGroupId.RARE_MOON_ASTEROIDS,
    ]
    qs = (
        EveOreType.objects.filter(
            eve_group_id__in=moon_ore_group_ids,
            published=True,
            extras__isnull=False,
            extras__current_price__isnull=False,
        )
        .exclude(name__icontains=" ")
        .select_related("eve_group", "extras")
    )
    data = [
        {
            "id": obj.id,
            "name": obj.name,
            "description": strip_tags(obj.description),
            "price": obj.extras.current_price,
            "group": obj.eve_group.name,
            "rarity_html": {
                "display": obj.rarity_class.bootstrap_tag_html,
                "sort": obj.rarity_class.label,
            },
            "rarity_str": obj.rarity_class.label,
        }
        for obj in qs
    ]
    return JsonResponse(data, safe=False)
