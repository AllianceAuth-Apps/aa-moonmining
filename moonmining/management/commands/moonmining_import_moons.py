import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from eveuniverse.core.esitools import is_esi_online
from eveuniverse.models import EveMoon

from allianceauth.services.hooks import get_extension_logger

from moonmining.core import CalculatedMoonProduct
from moonmining.models import EveOreType, Moon, MoonProduct

logger = get_extension_logger(__name__)


class Command(BaseCommand):
    help = "Import moons from a file in CSV format."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            help=(
                "Path of the CSV file to be imported. "
                'e.g.: "moons.csv" or  "/path/to/moons.csv"'
            ),
        )
        parser.add_argument(
            "--overwrite-existing",
            action="store_const",
            const=True,
            default=False,
            help="When set will overwrite existing moon surveys",
        )
        parser.add_argument(
            "--disable-esi-check",
            action="store_const",
            const=False,
            default=False,
            help="When set script will not check if ESI is online",
        )

    def handle(self, *args, **options):
        if not options["disable_esi_check"] and not is_esi_online():
            raise CommandError("ESI if offline. Aborting")

        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Could not find a file with the path: {path.resolve()}")

        moons = self.read_moons(path)
        total = len(moons.keys())
        self.stdout.write(f"Read {total:,} moons from file.")
        if not options["overwrite_existing"]:
            found = self.remove_existing_moons(moons)
            if found > 0:
                self.stdout.write(
                    f"Skipping update of {found:,} moons with existing surveys."
                )

        total_2 = len(moons.keys())
        self.stdout.write(f"Starting update of {total_2:,} moons.")

        try:
            self.update_moons(moons)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Aborted"))

        self.stdout.write(self.style.SUCCESS("DONE"))

    def read_moons(self, input_file: Path) -> Dict[int, List[CalculatedMoonProduct]]:
        self.stdout.write(f"Importing moons from: {input_file} ...")
        moons: Dict[int, List[CalculatedMoonProduct]] = defaultdict(list)
        with input_file.open("r", encoding="utf-8") as fp:
            csv_reader = csv.DictReader(fp)
            for row in csv_reader:
                try:
                    moon_id = int(row["moon_id"])
                    ore_type_id = int(row["ore_type_id"])
                    amount = float(row["amount"])
                except KeyError:
                    continue

                product = CalculatedMoonProduct(
                    ore_type_id=ore_type_id,
                    amount=amount,
                )
                moons[moon_id].append(product)

        if not len(moons.keys()):
            raise CommandError("Could not find any moons in the input file.")

        return moons

    def remove_existing_moons(
        self, moons: Dict[int, List[CalculatedMoonProduct]]
    ) -> int:
        existing = set(
            Moon.objects.filter(products__isnull=False).values_list(
                "eve_moon__id", flat=True
            )
        )
        overlapping = existing.intersection(moons.keys())
        removed = 0
        for moon_id in overlapping:
            del moons[moon_id]
            removed += 1

        return removed

    def update_moons(self, moons: Dict[int, List[CalculatedMoonProduct]]):
        amount = len(moons)
        completed = 0
        for eve_moon_id, products in moons.items():
            created_ores = []
            for p in products:
                _, created = EveOreType.objects.get_or_create_esi(id=p.ore_type_id)
                created_ores.append(created)
            if any(created_ores):
                EveOreType.objects.update_current_prices()

            eve_moon, _ = EveMoon.objects.get_or_create_esi(id=eve_moon_id)
            moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)

            product_objects = []
            for p in products:
                product_objects.append(
                    MoonProduct(
                        moon_id=moon.id, ore_type_id=p.ore_type_id, amount=p.amount
                    )
                )
            moon.update_products(product_objects)

            completed += 1
            progress = round(completed / amount * 100, 1)
            self.stdout.write(f"Updated: {str(moon):30} [Progress: {progress}%]")
            logger.info(
                "Added survey for moon ID %d with import command", moon.eve_moon.id
            )
