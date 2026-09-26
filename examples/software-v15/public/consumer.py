"""Simulated downstream inventory importer; source library remains upstream."""
from marshmallow import Schema, fields


class InventorySchema(Schema):
    sku = fields.String(required=True)
    description = fields.String(required=True)


def load_inventory(payload):
    return InventorySchema().load(payload)
