import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet

from moonmining.models import MoonProduct


class Command(BaseCommand):
    help = (
        "Export all moons to a file in CSV format. "
        "Note: The file can be imported with the import command."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            help=(
                "Path of destination file for export. "
                "File will be created or overwritten. "
                'e.g.: "moons.csv" or  "/path/to/moons.csv"'
            ),
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as fp:
                fieldnames = ["moon_id", "ore_type_id", "amount"]
                writer = csv.DictWriter(fp, fieldnames=fieldnames)
                writer.writeheader()
                products: QuerySet[MoonProduct] = MoonProduct.objects.order_by(
                    "moon_id"
                )
                count = products.count()
                path_str = path.resolve()
                self.stdout.write((f"Exporting {count:,} moons to: {path_str}"))
                for p in products:
                    row = {
                        "moon_id": p.moon_id,
                        "ore_type_id": p.ore_type_id,
                        "amount": p.amount,
                    }
                    writer.writerow(row)

        except OSError as ex:
            raise CommandError(ex) from ex

        self.stdout.write(self.style.SUCCESS("DONE"))
