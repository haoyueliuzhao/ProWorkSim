from marshmallow import Schema, fields


class RecordName(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        return super()._deserialize(value, attr, data, **kwargs).strip()


class RecordSchema(Schema):
    name = RecordName(required=True)
    quantity = fields.Integer(required=True)
