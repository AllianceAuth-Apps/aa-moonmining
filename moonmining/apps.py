from django.apps import AppConfig

from moonmining import __version__


class MoonMiningConfig(AppConfig):
    name = "moonmining"
    label = "moonmining"
    verbose_name = f"Moon Mining v{__version__}"
