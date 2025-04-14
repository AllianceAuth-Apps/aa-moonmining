from django.apps import AppConfig

from . import __version__


class MoonMiningConfig(AppConfig):
    name = "moonmining"
    label = "moonmining"
    verbose_name = f"Moon Mining v{__version__}"
