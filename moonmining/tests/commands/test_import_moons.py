from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from eveuniverse.tests.testdata.factories_2 import EveMoonFactory

from app_utils.testing import NoSocketsTestCase

from moonmining.models import Moon
from moonmining.tests.testdata.factories import (
    MoonAsteroidsTypeFactory,
    MoonFactory,
    MoonProductFactory,
    random_percentages,
)

MODULE_PATH = "moonmining.management.commands.moonmining_import_moons"


class TestImportMoons(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.import_file = (
            Path(__file__).parent.parent / "testdata" / "moons_for_import.csv"
        )
        EveMoonFactory(id=40161708)
        EveMoonFactory(id=40161709)
        MoonAsteroidsTypeFactory(id=45506)
        MoonAsteroidsTypeFactory(id=46676)
        MoonAsteroidsTypeFactory(id=46678)
        MoonAsteroidsTypeFactory(id=46689)
        MoonAsteroidsTypeFactory(id=45492)
        MoonAsteroidsTypeFactory(id=45494)

    def setUp(self) -> None:
        self.out = StringIO()

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: True)
    def test_should_create_moons(self):
        # when
        call_command("moonmining_import_moons", str(self.import_file), stdout=self.out)

        # then
        m1: Moon = Moon.objects.get(pk=40161708)
        self.assertIsNone(m1.products_updated_by)
        self.assertTrue(m1.products_updated_at)
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2: Moon = Moon.objects.get(pk=40161709)
        self.assertIsNone(m2.products_updated_by)
        self.assertTrue(m2.products_updated_at)
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: True)
    def test_should_not_overwrite_existing_surveys(self):
        # given
        moon = MoonFactory(eve_moon__id=40161708, create_products=False)
        p = random_percentages(4)
        MoonProductFactory(moon=moon, ore_type__id=45506, amount=p[0])
        MoonProductFactory(moon=moon, ore_type__id=46676, amount=p[1])
        MoonProductFactory(moon=moon, ore_type__id=46678, amount=p[2])
        MoonProductFactory(moon=moon, ore_type__id=46689, amount=p[3])
        # when
        call_command("moonmining_import_moons", str(self.import_file), stdout=self.out)

        # then
        m1: Moon = Moon.objects.get(pk=40161708)
        self.assertIsNone(m1.products_updated_by)
        self.assertTrue(m1.products_updated_at)
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, p[0])
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, p[1])
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, p[2])
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, p[3])

        m2: Moon = Moon.objects.get(pk=40161709)
        self.assertIsNone(m2.products_updated_by)
        self.assertTrue(m2.products_updated_at)
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: True)
    def test_should_update_moons_that_exist_but_have_no_survey(self):
        # given
        MoonFactory(eve_moon__id=40161708, create_products=False)
        # when
        call_command("moonmining_import_moons", str(self.import_file), stdout=self.out)

        # then
        m1: Moon = Moon.objects.get(pk=40161708)
        self.assertIsNone(m1.products_updated_by)
        self.assertTrue(m1.products_updated_at)
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2: Moon = Moon.objects.get(pk=40161709)
        self.assertIsNone(m2.products_updated_by)
        self.assertTrue(m2.products_updated_at)
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: True)
    def test_should_overwrite_existing_surveys_when_requested(self):
        # given
        moon = MoonFactory(eve_moon__id=40161708, create_products=False)
        p = random_percentages(4)
        MoonProductFactory(moon=moon, ore_type__id=45506, amount=p[0])
        MoonProductFactory(moon=moon, ore_type__id=46676, amount=p[1])
        MoonProductFactory(moon=moon, ore_type__id=46678, amount=p[2])
        MoonProductFactory(moon=moon, ore_type__id=46689, amount=p[3])
        # when
        call_command(
            "moonmining_import_moons",
            "--overwrite-existing",
            str(self.import_file),
            stdout=self.out,
        )

        # then
        m1: Moon = Moon.objects.get(pk=40161708)
        self.assertIsNone(m1.products_updated_by)
        self.assertTrue(m1.products_updated_at)
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2: Moon = Moon.objects.get(pk=40161709)
        self.assertIsNone(m2.products_updated_by)
        self.assertTrue(m2.products_updated_at)
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: True)
    def test_should_abort_when_input_file_not_found(self):
        # given
        import_file = Path(__file__).parent / "testdata" / "unknown_file.xyz"

        # when/then
        with self.assertRaises(CommandError):
            call_command("moonmining_import_moons", str(import_file), stdout=self.out)

    @patch(MODULE_PATH + ".is_esi_online", new=lambda: False)
    def test_should_abort_when_esi_is_offline(self):
        # when/then
        with self.assertRaises(CommandError):
            call_command(
                "moonmining_import_moons", str(self.import_file), stdout=self.out
            )
