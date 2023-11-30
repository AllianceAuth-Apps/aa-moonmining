"""Helpers for views."""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from app_utils.views import fontawesome_modal_button_html

from moonmining.models import Moon


def moon_details_button_html(moon: Moon) -> str:
    return fontawesome_modal_button_html(
        modal_id="modalMoonDetails",
        fa_code="fas fa-moon",
        ajax_url=reverse("moonmining:moon_details", args=[moon.pk]),
        tooltip=_("Moon details"),
    )
