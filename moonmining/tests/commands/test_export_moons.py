import csv
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command

from app_utils.testing import NoSocketsTestCase

from moonmining.models import Moon, MoonProduct
from moonmining.tests.testdata.factories import (
    EveOreTypeFactory,
    MoonFactory,
    MoonProductFactory,
)

PACKAGE_PATH = "moonmining.management.commands"


class TestMoonminingExportMoons(NoSocketsTestCase):
    def setUp(self) -> None:
        self.out = StringIO()

    def test_can_export_moons(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # given
            path = Path(tmp_dir) / "out.csv"
            moon_id = 40161708
            ore_type_id = 45506  # cinnabar
            amount = 0.4
            moon = MoonFactory(eve_moon__id=moon_id, create_products=False)
            ore_type = EveOreTypeFactory(id=ore_type_id)
            MoonProductFactory(moon=moon, amount=amount, ore_type=ore_type)

            # when
            call_command("moonmining_export_moons", str(path), stdout=self.out)

            # then
            self.assertTrue(path.exists())
            with path.open("r", newline="") as f:
                reader = csv.DictReader(f)
                rows = [row for row in reader]

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["moon_id"], str(moon_id))
            self.assertEqual(row["ore_type_id"], str(ore_type_id))
            self.assertEqual(row["amount"], str(amount))

    def test_can_abort_gracefully_on_os_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # given
            path = Path(tmp_dir) / "out.csv"

            # when
            with patch(PACKAGE_PATH + ".moonmining_export_moons.Path.open") as m:
                m.side_effect = OSError
                with self.assertRaises(CommandError):
                    call_command("moonmining_export_moons", str(path), stdout=self.out)


class TestExportAndImportMoons(NoSocketsTestCase):
    def setUp(self) -> None:
        self.out = StringIO()

    def test_can_export_and_import_moons(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # given
            path = Path(tmp_dir) / "out.csv"
            moon_id = 40161708
            ore_type_id = 45506  # cinnabar
            amount = 0.4
            moon = MoonFactory(eve_moon__id=moon_id, create_products=False)
            ore_type = EveOreTypeFactory(id=ore_type_id)
            MoonProductFactory(moon=moon, amount=amount, ore_type=ore_type)

            call_command("moonmining_export_moons", str(path), stdout=self.out)

            moon.delete()
            self.assertEqual(Moon.objects.count(), 0)

            with patch(
                PACKAGE_PATH + ".moonmining_import_moons.is_esi_online",
                new=lambda: True,
            ):
                call_command("moonmining_import_moons", str(path), stdout=self.out)

            self.assertEqual(Moon.objects.count(), 1)
            moon: Moon = Moon.objects.first()
            self.assertEqual(moon.eve_moon.id, moon_id)
            self.assertEqual(moon.products.count(), 1)
            product: MoonProduct = moon.products.first()
            self.assertEqual(product.ore_type.id, ore_type_id)
            self.assertEqual(product.amount, amount)
