from marshmallow import Schema, fields


class RecordSchema(Schema):
    """Reusable record boundary; implement the public normalization contract."""
    name = fields.String(required=True)
    quantity = fields.String(required=True)
