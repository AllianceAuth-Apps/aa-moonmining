"""Alternative factories which are not relying on fixtures."""

import datetime as dt
import random
import urllib.parse
from typing import Generic, List, TypeVar

import factory
import factory.fuzzy

from django.db.models import QuerySet
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveTypeMaterial
from eveuniverse.tests.testdata.factories_2 import (
    EveDogmaAttributeFactory,
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
    EveGroupFactory,
    EveMarketPriceFactory,
    EveMoonFactory,
    EveTypeFactory,
)

from app_utils.testdata_factories import UserMainFactory

from moonmining.app_settings import MOONMINING_VOLUME_PER_DAY
from moonmining.constants import EveCategoryId, EveDogmaAttributeId, EveGroupId
from moonmining.models import (
    EveOreType,
    EveOreTypeExtras,
    Extraction,
    ExtractionProduct,
    Label,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Notification,
    NotificationType,
    OreQualityClass,
    Owner,
    Refinery,
)
from moonmining.tests.helpers import datetime_to_ldap

T = TypeVar("T")
_BASE_URL = "https://esi.evetech.net/"
_POSITION_MIN = -100_000_000_000_000_000
_POSITION_MAX = 100_000_000_000_000_000


class BaseMetaFactory(Generic[T], factory.base.FactoryMetaClass):
    def __call__(cls, *args, **kwargs) -> T:
        return super().__call__(*args, **kwargs)


def make_esi_url(path: str) -> str:
    if path.startswith("/"):
        raise ValueError("path can not start with a slash")
    if path.endswith("/"):
        raise ValueError("path can not end with a slash")

    url = urllib.parse.urljoin(_BASE_URL, "/latest/" + path + "/")
    return url


def random_percentages(parts: int) -> List[float]:
    percentages = []
    total = 0
    for _ in range(parts):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append((100 - total) / 100)
    return percentages


class PositionFactory(factory.DictFactory, metaclass=BaseMetaFactory[dict]):
    x = factory.fuzzy.FuzzyFloat(_POSITION_MIN, _POSITION_MAX)
    y = factory.fuzzy.FuzzyFloat(_POSITION_MIN, _POSITION_MAX)
    z = factory.fuzzy.FuzzyFloat(_POSITION_MIN, _POSITION_MAX)


class EveEntityCorporationDEDFactory(EveEntityCorporationFactory):
    id = 1000137
    name = "DED"


# TODO: Replace with eveuniverse version
class MoonTypeFactory(EveTypeFactory):
    eve_group = factory.SubFactory(
        EveGroupFactory,
        eve_category__id=EveCategoryId.CELESTIAL,
        eve_category__name="Celestial",
        id=EveGroupId.MOON,
        name="Moon",
    )
    id = 14
    name = "Moon"


class MoonAsteroidsTypeFactory(EveTypeFactory):
    eve_group = factory.SubFactory(
        EveGroupFactory,
        eve_category__id=EveCategoryId.ASTEROID,
        eve_category__name="Asteroid",
        id=EveGroupId.COMMON_MOON_ASTEROIDS,
        name="Common Moon Asteroids",
    )


class RefineryTypeFactory(EveTypeFactory):
    eve_group = factory.SubFactory(
        EveGroupFactory,
        eve_category__id=EveCategoryId.STRUCTURE,
        eve_category__name="Structure",
        id=EveGroupId.REFINERY,
        name="Refinery",
    )


class EveOreTypeFactory(MoonAsteroidsTypeFactory):
    class Meta:
        model = EveOreType
        django_get_or_create = ("id",)

    volume = 10

    @factory.post_generation
    def ore_quality_class(obj: EveOreType, create, extracted, **kwargs):
        if not create or extracted is False:
            return

        try:
            oqc = OreQualityClass(extracted)
        except ValueError:
            oqc = OreQualityClass.REGULAR

        match oqc:
            case OreQualityClass.REGULAR:
                value = 1
            case OreQualityClass.IMPROVED:
                value = 3
            case OreQualityClass.EXCELLENT:
                value = 5
            case _:
                raise ValueError(f"Undefined ore quality class: {oqc}")

        da = EveDogmaAttributeFactory(id=EveDogmaAttributeId.ORE_QUALITY)
        obj.dogma_attributes.get_or_create(
            eve_dogma_attribute=da, defaults={"value": value}
        )

    @factory.post_generation
    def create_type_materials(obj: EveOreType, create, extracted, **kwargs):
        if not create or extracted is not True:
            return

        for _ in range(3):
            OreTypeMaterialFactory(ore_type=obj)

    @factory.post_generation
    def create_price(obj: EveOreType, create, extracted, **kwargs):
        if not create or extracted is False:
            return
        params = {"eve_type": obj}
        if "average_price" in kwargs:
            params["average_price"] = kwargs["average_price"]
        price = EveMarketPriceFactory(**params)
        EveOreTypeExtras.objects.update_or_create(
            ore_type=obj,
            defaults={
                "current_price": price.average_price,
                "pricing_method": EveOreTypeExtras.PricingMethod.EVE_CLIENT,
            },
        )


class MoonMaterialTypeFactory(EveTypeFactory):
    eve_group = factory.SubFactory(
        EveGroupFactory,
        eve_category__id=EveCategoryId.MATERIAL,
        eve_category__name="Material",
        id=EveGroupId.MOON_MATERIALS,
        name="Moon Material",
    )


class OreTypeMaterialFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[EveTypeMaterial]
):
    class Meta:
        model = EveTypeMaterial

    eve_type = factory.SubFactory(MoonAsteroidsTypeFactory)
    material_eve_type = factory.SubFactory(MoonMaterialTypeFactory)
    quantity = factory.fuzzy.FuzzyInteger(1, 10_000)


class UserMainOwnerFactory(UserMainFactory):
    main_character__scopes = Owner.esi_scopes()
    permissions__ = [
        "moonmining.basic_access",
        "moonmining.upload_moon_scan",
        "moonmining.extractions_access",
        "moonmining.add_refinery_owner",
    ]


class UserMainMemberFactory(UserMainFactory):
    main_character__scopes = Owner.esi_scopes()
    permissions__ = [
        "moonmining.basic_access",
        "moonmining.upload_moon_scan",
    ]


class LabelFactory(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Label]):
    class Meta:
        model = Label

    name = factory.Sequence(lambda n: f"test label #{n}")
    description = factory.Faker("paragraph")
    style = Label.Style.GREY


class MoonFactory2(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Moon]):
    class Meta:
        model = Moon
        exclude = ("create_products",)

    eve_moon = factory.SubFactory(EveMoonFactory)
    products_updated_at = factory.LazyFunction(now)

    @factory.post_generation
    def create_products(obj: Moon, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return

        amount = kwargs["amount"] if "amount" in kwargs else 3
        for p in random_percentages(amount):
            MoonProductFactory2(moon=obj, amount=p)

        obj.update_calculated_properties()


class MoonProductFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[MoonProduct]
):
    class Meta:
        model = MoonProduct

    amount = factory.fuzzy.FuzzyFloat(0, 1)
    moon = factory.SubFactory(MoonFactory2)
    ore_type = factory.SubFactory(EveOreTypeFactory)


class OwnerFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Owner]
):
    class Meta:
        model = Owner
        exclude = ("user",)

    user = factory.SubFactory(UserMainOwnerFactory)

    character_ownership = factory.LazyAttribute(
        lambda o: o.user.profile.main_character.character_ownership
    )
    corporation = factory.LazyAttribute(
        lambda o: o.user.profile.main_character.corporation
    )
    last_update_at = factory.LazyFunction(now)
    last_update_ok = True


class RefineryFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Refinery]
):
    class Meta:
        model = Refinery

    id = factory.Sequence(lambda n: n + 1900000000001)
    eve_type = factory.SubFactory(RefineryTypeFactory)
    moon = factory.SubFactory(MoonFactory2)
    name = factory.Faker("city")
    owner = factory.SubFactory(OwnerFactory2)


class ExtractionFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Extraction]
):
    class Meta:
        model = Extraction

    started_at = factory.fuzzy.FuzzyDateTime(
        now() - dt.timedelta(days=30), force_microsecond=0
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda o: o.started_at + dt.timedelta(days=20)
    )
    auto_fracture_at = factory.LazyAttribute(
        lambda o: o.chunk_arrival_at + dt.timedelta(hours=3)
    )
    refinery = factory.SubFactory(RefineryFactory2)
    status = Extraction.Status.STARTED

    @factory.post_generation
    def create_products(obj, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return
        if not obj.refinery.moon:
            return
        for product in obj.refinery.moon.products.all():
            ExtractionProductFactory2(
                extraction=obj,
                ore_type=product.ore_type,
                volume=MOONMINING_VOLUME_PER_DAY
                * obj.duration_in_days
                * product.amount,
            )
        obj.update_calculated_properties()


class ExtractionProductFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[ExtractionProduct]
):
    class Meta:
        model = ExtractionProduct


class MiningLedgerRecordFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[MiningLedgerRecord]
):
    class Meta:
        model = MiningLedgerRecord

    day = factory.fuzzy.FuzzyDate((now() - dt.timedelta(days=120)).date())
    character = factory.SubFactory(EveEntityCharacterFactory)
    corporation = factory.SubFactory(EveEntityCorporationFactory)
    ore_type = factory.SubFactory(EveOreTypeFactory)
    quantity = factory.fuzzy.FuzzyInteger(10000)


class MoonNotificationFactory2(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[Notification]
):
    """Create moon notification from scratch."""

    class Meta:
        model = Notification
        exclude = (
            "auto_fracture_at",
            "chunk_arrival_at",
            "eve_moon",
            "refinery",
            "started_at",
        )

    class Params:
        canceled_by = None
        fired_by = None
        started_by = None

    started_at = factory.fuzzy.FuzzyDateTime(
        now() - dt.timedelta(days=30), force_microsecond=0
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda o: o.started_at + dt.timedelta(days=20)
    )
    auto_fracture_at = factory.LazyAttribute(
        lambda o: o.chunk_arrival_at + dt.timedelta(hours=3)
    )
    refinery = factory.SubFactory(RefineryFactory2)
    eve_moon = factory.LazyAttribute(lambda o: o.refinery.moon.eve_moon)

    notification_id = factory.Sequence(lambda n: 1_990_000_001 + n)
    owner = factory.LazyAttribute(lambda o: o.refinery.owner)
    created = factory.LazyFunction(now)
    notif_type = NotificationType.MOONMINING_EXTRACTION_STARTED.value
    last_updated = factory.LazyFunction(now)
    sender = factory.SubFactory(EveEntityCorporationDEDFactory)

    @factory.lazy_attribute
    def timestamp(self) -> dt.datetime:
        match NotificationType(self.notif_type):
            case NotificationType.MOONMINING_EXTRACTION_STARTED:
                return self.started_at.replace(microsecond=0)

            case NotificationType.MOONMINING_EXTRACTION_CANCELLED:
                return factory.fuzzy.FuzzyDateTime(
                    self.started_at, self.chunk_arrival_at, force_microsecond=0
                ).fuzz()

            case NotificationType.MOONMINING_EXTRACTION_FINISHED:
                return self.chunk_arrival_at

            case NotificationType.MOONMINING_LASER_FIRED:
                return factory.fuzzy.FuzzyDateTime(
                    self.chunk_arrival_at, self.auto_fracture_at, force_microsecond=0
                ).fuzz()

            case NotificationType.MOONMINING_AUTOMATIC_FRACTURE:
                return self.auto_fracture_at.replace(microsecond=0)

            case _:
                raise ValueError(f"invalid notif type: {self.notif_type}")

    @factory.lazy_attribute
    def details(self) -> dict:
        def _details_link(character: EveEntity) -> str:
            return f'<a href="showinfo:1379//{character.id}">{character.name}</a>'

        data = {
            "moonID": self.eve_moon.id,
            "structureID": self.refinery.id,
            "solarSystemID": self.eve_moon.eve_planet.eve_solar_system.id,
            "structureLink": (
                f'<a href="showinfo:35835//{self.refinery.id}">{self.refinery.name}</a>'
            ),
            "structureName": self.refinery.name,
            "structureTypeID": self.refinery.eve_type_id,
        }

        duration = (self.chunk_arrival_at - self.started_at).total_seconds() / 3600 / 24
        volume = MOONMINING_VOLUME_PER_DAY * duration
        if self.refinery and self.refinery.moon:
            products: QuerySet[MoonProduct] = self.refinery.moon.products.all()
            ore_volume_by_type = {
                str(p.ore_type.id): p.amount * volume for p in products
            }
        else:
            ore_volume_by_type = {
                EveOreTypeFactory().id: p * volume for p in random_percentages(3)
            }

        match NotificationType(self.notif_type):
            case NotificationType.MOONMINING_EXTRACTION_STARTED:
                started_by = self.started_by or EveEntityCharacterFactory()
                data.update(
                    {
                        "startedBy": started_by.id,
                        "startedByLink": _details_link(started_by),
                        "autoTime": datetime_to_ldap(self.auto_fracture_at),
                        "readyTime": datetime_to_ldap(self.chunk_arrival_at),
                        "oreVolumeByType": ore_volume_by_type,
                    }
                )

            case NotificationType.MOONMINING_EXTRACTION_CANCELLED:
                canceled_by = self.canceled_by or EveEntityCharacterFactory()
                data.update(
                    {
                        "cancelledBy": canceled_by.id,
                        "cancelledByLink": _details_link(canceled_by),
                    }
                )

            case NotificationType.MOONMINING_EXTRACTION_FINISHED:
                data.update(
                    {
                        "autoTime": datetime_to_ldap(self.auto_fracture_at),
                        "oreVolumeByType": ore_volume_by_type,
                    }
                )

            case NotificationType.MOONMINING_LASER_FIRED:
                fired_by = self.fired_by or EveEntityCharacterFactory()
                data.update(
                    {
                        "firedBy": fired_by.id,
                        "firedByLink": _details_link(fired_by),
                        "oreVolumeByType": ore_volume_by_type,
                    }
                )

            case NotificationType.MOONMINING_AUTOMATIC_FRACTURE:
                data.update(
                    {
                        "oreVolumeByType": ore_volume_by_type,
                    }
                )

            case _:
                raise ValueError(f"invalid notif type: {self.notif_type}")

        return data
