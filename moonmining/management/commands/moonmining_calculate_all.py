import logging

from django.core.management.base import BaseCommand

from moonmining import tasks
from moonmining.management.commands import get_input
from moonmining.models import Extraction, Moon

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Calculate all properties for moons and extractions."

    def handle(self, *args, **options):
        moon_count = Moon.objects.count()
        extractions_count = Extraction.objects.count()
        self.stdout.write(
            f"Updating calculated properties for {moon_count} moons "
            f"and {extractions_count} extractions. This can take a while."
        )
        self.stdout.write("")
        user_input = get_input("Are you sure you want to proceed? (Y/n)?")

        if user_input.lower() != "n":
            tasks.run_calculated_properties_update.delay()
            self.stdout.write(self.style.SUCCESS("Update started."))
        else:
            self.stdout.write(self.style.WARNING("Aborted"))
