from marshmallow import Schema, fields


class NameSchema(Schema):
    """Shared name boundary; implement the public canonical rule."""
    name = fields.String(required=True)
