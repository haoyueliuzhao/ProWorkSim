from decimal import Decimal, InvalidOperation
import re
from marshmallow import EXCLUDE, Schema, ValidationError, fields


class CentsField(fields.Field):
    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value) is None:
            raise ValidationError("Invalid nonnegative money string")
        try:
            return int(Decimal(value) * 100)
        except (InvalidOperation, ValueError) as error:
            raise ValidationError("Invalid money string") from error

    def _serialize(self, value, attr, obj, **kwargs):
        return str(value // 100) + "." + str(value % 100).zfill(2)


class LedgerSchema(Schema):
    id = fields.String(required=True)
    amount = CentsField(required=True)

    class Meta:
        unknown = EXCLUDE
