"""Tasks."""

from celery import Task, chain, shared_task

from django.contrib.auth.models import User
from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice
from eveuniverse.tasks import update_unresolved_eve_entities

from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from app_utils.esi import retry_task_on_esi_error_and_offline
from app_utils.logging import LoggerAddTag

from . import __title__
from .models import EveOreType, Extraction, Moon, Owner, Refinery

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

TASK_PRIORITY_LOWER = 6


@shared_task
def process_survey_input(scans, user_pk=None) -> bool:
    """Update moons from survey input."""
    user = User.objects.get(pk=user_pk) if user_pk else None
    return Moon.objects.update_moons_from_survey(scans, user)


@shared_task
def run_regular_updates():
    """Run main tasks for regular updates."""
    owners_to_update = Owner.objects.filter(is_enabled=True)
    owner_pks = owners_to_update.values_list("pk", flat=True)
    logger.info("Updating %d owners...", len(owner_pks))
    owners_to_update.update(last_update_ok=None, last_update_at=now())
    for owner_pk in owner_pks:
        update_owner.delay(owner_pk)


@shared_task(base=QueueOnce, once={"keys": ["owner_pk"], "graceful": True})
def update_owner(owner_pk: int):
    """Update refineries and extractions for given owner."""
    chain(
        update_refineries_from_esi_for_owner.si(owner_pk),
        fetch_notifications_from_esi_for_owner.si(owner_pk),
        update_extractions_for_owner.si(owner_pk),
        mark_successful_update_for_owner.si(owner_pk),
    ).delay()


@shared_task(bind=True, base=QueueOnce, once={"keys": ["owner_pk"], "graceful": True})
def update_refineries_from_esi_for_owner(self: Task, owner_pk: int):
    """Update refineries for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    with retry_task_on_esi_error_and_offline(self):
        owner.update_refineries_from_esi()


@shared_task(bind=True, base=QueueOnce, once={"keys": ["owner_pk"], "graceful": True})
def fetch_notifications_from_esi_for_owner(self: Task, owner_pk: int):
    """Update extractions for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    with retry_task_on_esi_error_and_offline(self):
        owner.fetch_notifications_from_esi()


@shared_task(bind=True, base=QueueOnce, once={"keys": ["owner_pk"], "graceful": True})
def update_extractions_for_owner(self: Task, owner_pk: int):
    """Update extractions for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    with retry_task_on_esi_error_and_offline(self):
        owner.update_extractions()


@shared_task
def mark_successful_update_for_owner(owner_pk: int):
    """Mark a successful update for this corporation."""
    owner = Owner.objects.get(pk=owner_pk)
    owner.last_update_ok = True
    owner.save()


@shared_task
def run_report_updates():
    """Run tasks for updating reports and related data."""
    owners_to_update = Owner.objects.filter(is_enabled=True)
    owner_pks = owners_to_update.values_list("pk", flat=True)
    logger.info("Updating mining ledgers for %d owners...", len(owner_pks))
    for owner_pk in owner_pks:
        update_mining_ledger_for_owner.delay(owner_pk)


@shared_task(bind=True, base=QueueOnce, once={"keys": ["owner_pk"], "graceful": True})
def update_mining_ledger_for_owner(self: Task, owner_pk: int):
    """Update mining ledger for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    with retry_task_on_esi_error_and_offline(self):
        observer_ids = owner.fetch_mining_ledger_observers_from_esi()

    for refinery_id in owner.refineries.filter(id__in=observer_ids).values_list(
        "id", flat=True
    ):
        update_mining_ledger_for_refinery.apply_async(
            kwargs={"refinery_id": refinery_id}, priority=TASK_PRIORITY_LOWER
        )


@shared_task(
    bind=True,
    base=QueueOnce,
    once={"keys": ["refinery_id"], "graceful": True},
)
def update_mining_ledger_for_refinery(self: Task, refinery_id: int):
    """Update mining ledger for a refinery from ESI."""
    refinery = Refinery.objects.get(id=refinery_id)
    with retry_task_on_esi_error_and_offline(self):
        refinery.update_mining_ledger_from_esi()


@shared_task
def run_calculated_properties_update():
    """Update the calculated properties of all moons and all extractions."""
    chain(
        update_market_prices.si().set(priority=TASK_PRIORITY_LOWER),
        update_current_ore_prices.si().set(priority=TASK_PRIORITY_LOWER),
        update_moons.si().set(priority=TASK_PRIORITY_LOWER),
        update_extractions.si().set(priority=TASK_PRIORITY_LOWER),
        update_unresolved_eve_entities.si().set(priority=TASK_PRIORITY_LOWER),
    ).delay()


@shared_task(bind=True, base=QueueOnce)
def update_market_prices(self):
    """Update all market prices."""
    with retry_task_on_esi_error_and_offline(self):
        EveMarketPrice.objects.update_from_esi()


@shared_task
def update_current_ore_prices():
    """Update current prices for all ore types."""
    EveOreType.objects.update_current_prices()


@shared_task
def update_moons():
    """Update the calculated properties of all moons."""
    moon_pks = Moon.objects.values_list("pk", flat=True)
    logger.info("Updating calculated properties for %d moons ...", len(moon_pks))
    for moon_pk in moon_pks:
        update_moon_calculated_properties.apply_async(
            kwargs={"moon_pk": moon_pk}, priority=TASK_PRIORITY_LOWER
        )


@shared_task
def update_moon_calculated_properties(moon_pk):
    """Update all calculated properties for given moon."""
    moon = Moon.objects.get(pk=moon_pk)
    moon.update_calculated_properties()


@shared_task
def update_moon_products_from_latest_extraction(moon_pk: int):
    """Update moon products from latest extraction."""
    moon = Moon.objects.get(pk=moon_pk)
    result = moon.update_products_from_latest_extraction(overwrite_survey=True)
    if result is True:
        logger.info("%s: Updated moon products from latest extraction", moon)
    elif result is None:
        logger.info(
            "%s: Failed to update moon products from latest extraction, "
            "because this moon has no extractions.",
            moon,
        )
    else:
        logger.info("%s: Failed to update moon products from latest extraction", moon)


@shared_task
def update_extractions():
    """Update the calculated properties of all extractions."""
    extraction_pks = Extraction.objects.values_list("pk", flat=True)
    logger.info(
        "Updating calculated properties for %d extractions ...", len(extraction_pks)
    )
    for extraction_pk in extraction_pks:
        update_extraction_calculated_properties.apply_async(
            kwargs={"extraction_pk": extraction_pk}, priority=TASK_PRIORITY_LOWER
        )


@shared_task
def update_extraction_calculated_properties(extraction_pk: int):
    """Update all calculated properties for given extraction."""
    extraction = Extraction.objects.get(pk=extraction_pk)
    extraction.update_calculated_properties()
