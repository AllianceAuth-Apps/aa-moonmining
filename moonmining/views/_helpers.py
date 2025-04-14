"""Helpers for views."""

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from app_utils.views import BootstrapStyleBS5

from moonmining.models import Moon


def moon_details_button_html(moon: Moon) -> str:
    """Return HTML to render a moon details button."""
    return fontawesome_modal_button_html(
        modal_id="modalMoonDetails",
        fa_code="fas fa-moon",
        ajax_url=reverse("moonmining:moon_details", args=[moon.pk]),
        tooltip=_("Moon details"),
    )


def fontawesome_modal_button_html(
    modal_id: str,
    fa_code: str,
    ajax_url: str = "",
    tooltip: str = "",
    style=BootstrapStyleBS5.DEFAULT,
) -> str:
    """Return HTML for a modal button with fontawesome symbols.

    Args:
        modal_id: DOM ID of modal to invoke
        fa_code: fontawesome code, e.g. "fas fa-moon"
        ajax_url: URL to invoke via AJAX for loading modal content
        tooltip: text to appear as tooltip
        style: Bootstrap context style for the button
    """
    return format_html(
        '<button type="button" '
        'class="btn btn-{}" '
        'data-bs-toggle="modal" '
        'data-bs-target="#{}" '
        "{}"
        "{}>"
        '<i class="{}"></i>'
        "</button>",
        BootstrapStyleBS5(style),
        modal_id,
        mark_safe(f'title="{tooltip}" ') if tooltip else "",
        mark_safe(f'data-ajax_url="{ajax_url}" ') if ajax_url else "",
        fa_code,
    )
