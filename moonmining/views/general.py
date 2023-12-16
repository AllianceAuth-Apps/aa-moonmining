"""General views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_admins
from app_utils.logging import LoggerAddTag

from moonmining import __title__, tasks
from moonmining.app_settings import MOONMINING_ADMIN_NOTIFICATIONS_ENABLED
from moonmining.models import Owner

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("moonmining.basic_access")
def index(request):
    """Render an index view."""
    if request.user.has_perm("moonmining.extractions_access"):
        return redirect("moonmining:extractions")
    return redirect("moonmining:moons")


@permission_required(["moonmining.add_refinery_owner", "moonmining.basic_access"])
@token_required(scopes=Owner.esi_scopes())  # type: ignore
@login_required
def add_owner(request, token):
    """Render view to add an owner."""
    character_ownership = get_object_or_404(
        request.user.character_ownerships.select_related("character"),
        character__character_id=token.character_id,
    )
    try:
        corporation = EveCorporationInfo.objects.get(
            corporation_id=character_ownership.character.corporation_id
        )
    except EveCorporationInfo.DoesNotExist:
        corporation = EveCorporationInfo.objects.create_corporation(
            corp_id=character_ownership.character.corporation_id
        )
        corporation.save()

    owner = Owner.objects.update_or_create(
        corporation=corporation,
        defaults={"character_ownership": character_ownership},
    )[0]
    tasks.update_owner.delay(owner.pk)
    messages.success(request, f"Update of refineries started for {owner}.")
    if MOONMINING_ADMIN_NOTIFICATIONS_ENABLED:
        notify_admins(
            message=_(
                "%(corporation)s was added as new owner by %(user)s."
                % {"corporation": owner, "user": request.user}
            ),
            title=f"{__title__}: Owner added: {owner}",
        )
    return redirect("moonmining:index")


@cache_page(3600)
def modal_loader_body(request):
    """Draw the loader body. Useful for showing a spinner while loading a modal."""
    return render(request, "moonmining/modals/loader_body.html")


def tests(request):
    """Render page with JS tests."""
    return render(request, "moonmining/tests.html")
