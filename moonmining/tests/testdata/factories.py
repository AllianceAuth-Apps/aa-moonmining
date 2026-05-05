import datetime as dt
import random
from typing import Generic, List, TypeVar

import factory
import factory.fuzzy

from django.utils.timezone import now
from eveuniverse.models import EveMoon, EveType
from eveuniverse.tests.testdata.factories_2 import (
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
)

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

from moonmining.app_settings import MOONMINING_VOLUME_PER_DAY
from moonmining.constants import EveTypeId
from moonmining.core import CalculatedExtraction, CalculatedExtractionProduct
from moonmining.models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Owner,
    Refinery,
)

T = TypeVar("T")

_FUZZY_START_YEAR = 2008


class BaseMetaFactory(Generic[T], factory.base.FactoryMetaClass):
    def __call__(cls, *args, **kwargs) -> T:
        return super().__call__(*args, **kwargs)


# moonmining


def random_percentages(num_parts: int) -> List[float]:
    percentages = []
    total = 0
    for _ in range(num_parts - 1):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append((100 - total) / 100)
    return percentages


def _generate_calculated_extraction_products(
    started_at: dt.datetime,
    chunk_arrival_at: dt.datetime,
) -> List[CalculatedExtractionProduct]:
    if not chunk_arrival_at:
        raise ValueError("missing chunk_arrival_at")
    if not started_at:
        raise ValueError("missing started_at")

    ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
    percentages = random_percentages(3)
    duration = (chunk_arrival_at - started_at).total_seconds() / 3600 / 24
    products = [
        CalculatedExtractionProductFactory(
            ore_type_id=ore_type_id,
            volume=percentages.pop() * MOONMINING_VOLUME_PER_DAY * duration,
        )
        for ore_type_id in ore_type_ids
    ]
    return products


class CalculatedExtractionProductFactory(factory.Factory):
    class Meta:
        model = CalculatedExtractionProduct


class CalculatedExtractionFactory(
    factory.Factory, metaclass=BaseMetaFactory[CalculatedExtraction]
):
    class Meta:
        model = CalculatedExtraction

    auto_fracture_at = factory.LazyAttribute(
        lambda o: o.chunk_arrival_at + dt.timedelta(hours=3)
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda o: o.started_at + dt.timedelta(days=20)
    )
    refinery_id = factory.Sequence(lambda n: n + 1800000000001)
    status = CalculatedExtraction.Status.STARTED
    started_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(_FUZZY_START_YEAR, 1, 1, tzinfo=dt.timezone.utc),
        force_microsecond=0,
    )

    @factory.lazy_attribute
    def started_by(self):
        character = EveEntityCharacterFactory(name="Bruce Wayne")
        return character.id

    @factory.lazy_attribute
    def products(self):
        return _generate_calculated_extraction_products(
            self.started_at, self.chunk_arrival_at
        )


class MiningLedgerRecordFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[MiningLedgerRecord]
):
    class Meta:
        model = MiningLedgerRecord

    day = factory.fuzzy.FuzzyDate((now() - dt.timedelta(days=120)).date())
    character = factory.SubFactory(EveEntityCharacterFactory)
    corporation = factory.SubFactory(EveEntityCorporationFactory)
    ore_type = factory.LazyFunction(lambda: EveOreType.objects.order_by("?").first())
    quantity = factory.fuzzy.FuzzyInteger(10000)


class MoonFactory(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Moon]):
    class Meta:
        model = Moon
        exclude = ("create_products",)

    products_updated_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(_FUZZY_START_YEAR, 1, 1, tzinfo=dt.timezone.utc),
        force_microsecond=0,
    )

    @factory.lazy_attribute
    def eve_moon(self):
        return EveMoon.objects.exclude(
            id__in=list(Moon.objects.values_list("eve_moon_id", flat=True))
        ).first()

    @factory.post_generation
    def create_products(obj, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return
        ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
        percentages = random_percentages(3)
        for ore_type_id in ore_type_ids:
            ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
            MoonProductFactory(moon=obj, ore_type=ore_type, amount=percentages.pop())
        obj.update_calculated_properties()


class MoonProductFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[MoonProduct]
):
    class Meta:
        model = MoonProduct


class OwnerFactory(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Owner]):
    class Meta:
        model = Owner

    last_update_at = factory.LazyFunction(now)
    last_update_ok = True

    @factory.lazy_attribute
    def character_ownership(self):
        _, obj = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.upload_moon_scan",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
            ],
            scopes=Owner.esi_scopes(),
        )
        return obj

    @factory.lazy_attribute
    def corporation(self):
        corporation_id = (
            self.character_ownership.character.corporation_id
            if self.character_ownership
            else 2001
        )
        return EveCorporationInfo.objects.get(corporation_id=corporation_id)


class RefineryFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Refinery]
):
    class Meta:
        model = Refinery

    id = factory.Sequence(lambda n: n + 1900000000001)
    name = factory.Faker("city")
    moon = factory.SubFactory(MoonFactory)
    owner = factory.SubFactory(OwnerFactory)

    @factory.lazy_attribute
    def eve_type(self):
        return EveType.objects.get(id=EveTypeId.ATHANOR)


class ExtractionFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Extraction]
):
    class Meta:
        model = Extraction

    started_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(_FUZZY_START_YEAR, 1, 1, tzinfo=dt.timezone.utc),
        force_microsecond=0,
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda obj: obj.started_at + dt.timedelta(days=20)
    )
    auto_fracture_at = factory.LazyAttribute(
        lambda obj: obj.chunk_arrival_at + dt.timedelta(hours=3)
    )
    refinery = factory.SubFactory(RefineryFactory)
    status = Extraction.Status.STARTED

    @factory.post_generation
    def create_products(obj, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return
        if not obj.refinery.moon:
            return
        for product in obj.refinery.moon.products.all():
            ExtractionProductFactory(
                extraction=obj,
                ore_type=product.ore_type,
                volume=MOONMINING_VOLUME_PER_DAY
                * obj.duration_in_days
                * product.amount,
            )
        obj.update_calculated_properties()


class ExtractionProductFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[ExtractionProduct]
):
    class Meta:
        model = ExtractionProduct
