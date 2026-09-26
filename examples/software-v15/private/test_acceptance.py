"""Frozen controller-only checks; never served by actor source/read tools."""
import inspect
import unittest
from pathlib import Path
from marshmallow import Schema, ValidationError, fields, validate
from consumer import InventorySchema, load_inventory


class IndependentAcceptance(unittest.TestCase):
    def test_import_is_exact_materialized_tree(self):
        self.assertTrue(Path(inspect.getfile(fields)).resolve().is_relative_to(Path.cwd() / "src"))

    def test_default_and_false_preserve(self):
        for value in ("  Keep\t ", "\u2003inside x\u2003", b" A "):
            expected = value.decode() if isinstance(value, bytes) else value
            self.assertEqual(fields.String().deserialize(value), expected)
            self.assertEqual(fields.String(strip_whitespace=False).deserialize(value), expected)

    def test_unicode_whitespace_and_inner_preserved(self):
        self.assertEqual(fields.String(strip_whitespace=True).deserialize("\u2003 A  B\t\n"), "A  B")
        self.assertEqual(fields.Str(strip_whitespace=True).deserialize("\t\n"), "")

    def test_bytes_decode_then_strip(self):
        self.assertEqual(fields.String(strip_whitespace=True).deserialize("  é\t".encode()), "é")

    def test_invalid_utf8_message(self):
        with self.assertRaises(ValidationError) as context:
            fields.String(strip_whitespace=True).deserialize(b"\xff")
        self.assertEqual(context.exception.messages, ["Not a valid utf-8 string."])

    def test_invalid_types_stay_errors(self):
        for value in (0, False, [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                fields.String(strip_whitespace=True).deserialize(value)

    def test_none_allow_and_reject(self):
        self.assertIsNone(fields.String(strip_whitespace=True, allow_none=True).deserialize(None))
        with self.assertRaises(ValidationError):
            fields.String(strip_whitespace=True).deserialize(None)

    def test_validation_uses_normalized_value(self):
        field = fields.String(strip_whitespace=True, validate=validate.Length(min=2, max=3))
        self.assertEqual(field.deserialize("  ab  "), "ab")
        with self.assertRaises(ValidationError):
            field.deserialize("  a  ")

    def test_dump_unmodified(self):
        field = fields.String(strip_whitespace=True)
        self.assertEqual(field.serialize("v", {"v": "  A  "}), "  A  ")

    def test_consumer_contract(self):
        for sku in ("\nSKU-X\t", "\u2002Q  R "):
            self.assertEqual(load_inventory({"sku": sku, "description": " untouched "}),
                             {"sku": sku.strip(), "description": " untouched "})
        self.assertEqual(InventorySchema().dump({"sku": " A ", "description": " B "}),
                         {"sku": " A ", "description": " B "})

    def test_schema_keyword_alias_and_partial(self):
        class Packet(Schema):
            code = fields.String(strip_whitespace=True, required=True, data_key="Code")
        self.assertEqual(Packet().load({"Code": " X "}), {"code": "X"})
        self.assertEqual(Packet().load({}, partial=True), {})
        class Envelope(Schema):
            packet = fields.Nested(Packet)
        self.assertEqual(Envelope().load({"packet": {"Code": " N "}}), {"packet": {"code": "N"}})
        parameter = inspect.signature(fields.String).parameters["strip_whitespace"]
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameter.default, False)
        self.assertIn("strip_whitespace", fields.String.__doc__ or "")

    def test_legacy_email_subclass_compatible(self):
        self.assertEqual(fields.Email().deserialize("a@example.com"), "a@example.com")


if __name__ == "__main__":
    outcome = unittest.main(exit=False)
    if not outcome.result.wasSuccessful():
        raise SystemExit(1)
