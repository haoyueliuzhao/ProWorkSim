from marshmallow import EXCLUDE, Schema, fields, validate


class NetworkSchema(Schema):
    host = fields.String(required=True)
    port = fields.Integer(required=True, validate=validate.Range(min=1, max=65535))

    class Meta:
        unknown = EXCLUDE


class SettingsSchema(Schema):
    name = fields.String(required=True)
    network = fields.Nested(NetworkSchema, required=True)
    token = fields.String(required=True, load_only=True)
    retries = fields.Integer(load_default=3, validate=validate.Range(min=0))

    class Meta:
        unknown = EXCLUDE
