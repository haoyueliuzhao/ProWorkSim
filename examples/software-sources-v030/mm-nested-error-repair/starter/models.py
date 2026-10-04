from marshmallow import EXCLUDE, Schema, fields, validate


class AddressSchema(Schema):
    postal = fields.Integer(required=True, validate=validate.Range(min=1))
    city = fields.String(required=True)

    class Meta:
        unknown = EXCLUDE


class PersonSchema(Schema):
    name = fields.String(required=True, data_key="fullName")
    address = fields.Nested(AddressSchema, required=True)

    class Meta:
        unknown = EXCLUDE
