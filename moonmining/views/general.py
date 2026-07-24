"""General views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as __
from django.views.decorators.cache import cache_page
from esi.decorators import token_required
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_admins

from moonmining import __title__, tasks
from moonmining.app_settings import MOONMINING_ADMIN_NOTIFICATIONS_ENABLED
from moonmining.models import Owner

logger = get_extension_logger(__name__)


@login_required
@permission_required("moonmining.basic_access")
def index(request: HttpRequest):
    """Render an index view."""
    if request.user.has_perm("moonmining.extractions_access"):
        return redirect("moonmining:extractions")
    return redirect("moonmining:moons")


@permission_required(["moonmining.add_refinery_owner", "moonmining.basic_access"])
@token_required(scopes=Owner.esi_scopes())  # type: ignore
@login_required
def add_owner(request: HttpRequest, token: Token):
    """Render view to add an owner."""
    character_ownership: CharacterOwnership = get_object_or_404(
        request.user.character_ownerships.select_related("character"),
        character__character_id=token.character_id,
    )
    character = character_ownership.character
    if EveEntity.is_npc_id(character.corporation_id):
        messages.error(
            request,
            f"Can not add NPC corporation: {character.corporation.corporation_name}",
        )
        return redirect("moonmining:index")

    try:
        corporation = EveCorporationInfo.objects.get(
            corporation_id=character.corporation_id
        )
    except EveCorporationInfo.DoesNotExist:
        corporation = EveCorporationInfo.objects.create_corporation(
            character.corporation_id
        )
        corporation.save()

    owner, _ = Owner.objects.update_or_create(
        corporation=corporation,
        defaults={"character_ownership": character_ownership},
    )
    tasks.update_owner.delay(owner.pk)
    messages.success(request, f"Update of refineries started for {owner}.")
    if MOONMINING_ADMIN_NOTIFICATIONS_ENABLED:
        notify_admins(
            message=__(
                "%(corporation)s was added as new owner by %(user)s."
                % {"corporation": owner, "user": request.user}
            ),
            title=f"{__title__}: Owner added: {owner}",
        )
    return redirect("moonmining:index")


@cache_page(3600)
def modal_loader_body(request: HttpRequest):
    """Draw the loader body. Useful for showing a spinner while loading a modal."""
    return render(request, "moonmining/modals/loader_body.html")


def tests(request: HttpRequest):
    """Render page with JS tests."""
    return render(request, "moonmining/tests.html")
