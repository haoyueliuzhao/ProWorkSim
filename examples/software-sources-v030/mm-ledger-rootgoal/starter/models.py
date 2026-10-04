from marshmallow import Schema, fields


class CentsField(fields.Field):
    """Load nonnegative integer minor units; dump canonical major-unit strings."""
    def _deserialize(self, value, attr, data, **kwargs):
        raise NotImplementedError("Implement money parsing")

    def _serialize(self, value, attr, obj, **kwargs):
        raise NotImplementedError("Implement canonical money formatting")


class LedgerSchema(Schema):
    id = fields.String(required=True)
    amount = CentsField(required=True)
