"""Public examples are feedback, not the full acceptance contract."""
import unittest
from marshmallow import fields
from consumer import load_inventory


class VisibleContract(unittest.TestCase):
    def test_legacy_default_preserves_spaces(self):
        self.assertEqual(fields.String().deserialize("  A  "), "  A  ")

    def test_opt_in_strips_on_load(self):
        self.assertEqual(fields.String(strip_whitespace=True).deserialize("  A  "), "A")

    def test_consumer_only_normalizes_sku(self):
        self.assertEqual(load_inventory({"sku": "  A  ", "description": " keep "}),
                         {"sku": "A", "description": " keep "})


if __name__ == "__main__":
    outcome = unittest.main(exit=False)
    if not outcome.result.wasSuccessful():
        raise SystemExit(1)
