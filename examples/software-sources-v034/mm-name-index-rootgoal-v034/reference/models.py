from marshmallow import Schema, fields


class CanonicalName(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        return super()._deserialize(value, attr, data, **kwargs).strip().lower()


class NameSchema(Schema):
    name = CanonicalName(required=True)
