"""Singular provider object for ESI."""

from pathlib import Path

from esi.openapi_clients import ESIClientProvider

from . import __version__

spec_file = Path(__file__).parent / "openapi_2025-12-16.json"
esi = ESIClientProvider(
    compatibility_date="2025-12-16",
    ua_appname="aa-moonmining",
    ua_version=__version__,
    operations=[
        "GetCharactersCharacterIdNotifications",
        "GetCorporationCorporationIdMiningExtractions",
        "GetCorporationCorporationIdMiningObservers",
        "GetCorporationCorporationIdMiningObserversObserverId",
        "GetCorporationsCorporationIdStructures",
        "GetUniverseStructuresStructureId",
    ],
    spec_file=spec_file,
)
