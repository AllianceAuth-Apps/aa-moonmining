"""Global constants."""

from enum import IntEnum


class EveCategoryId(IntEnum):
    """An Eve category ID."""

    ASTEROID = 25
    CELESTIAL = 2
    MATERIAL = 4
    STRUCTURE = 65


class EveGroupId(IntEnum):
    """An Eve group ID."""

    CITADEL = 1657
    COMMON_MOON_ASTEROIDS = 1920
    EXCEPTIONAL_MOON_ASTEROIDS = 1923
    MINERAL = 18
    MOON = 8
    MOON_MATERIALS = 427
    RARE_MOON_ASTEROIDS = 1922
    REFINERY = 1406
    UBIQUITOUS_MOON_ASTEROIDS = 1884
    UNCOMMON_MOON_ASTEROIDS = 1921


class EveTypeId(IntEnum):
    """An Eve type ID."""

    ATHANOR = 35835
    CHROMITE = 45501
    EUXENITE = 45495
    XENOTIME = 45510
    BITUMENS = 45492
    CINNABAR = 45506
    CUBIC_BISTOT = 46676
    FLAWLESS_ARKONOR = 46678
    STABLE_VELDSPAR = 46689
    ZEOLITES = 45490
    BRIMFUL_ZEOLITES = 46280
    GLISTENING_ZEOLITES = 46281

    MOON = 14


class EveDogmaAttributeId(IntEnum):
    """An Eve dogma attribute ID."""

    ORE_QUALITY = 2699


DATETIME_FORMAT = "%Y-%b-%d %H:%M"
DATE_FORMAT = "%Y-%b-%d"
VALUE_DIVIDER = 1_000_000_000


class IconSize(IntEnum):
    """Icon sizes."""

    SMALL = 32
    MEDIUM = 64
