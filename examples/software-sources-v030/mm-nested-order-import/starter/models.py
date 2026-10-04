from marshmallow import EXCLUDE, Schema, fields


class BuyerSchema(Schema):
    email = fields.String(required=True)

    class Meta:
        unknown = EXCLUDE


class LineSchema(Schema):
    sku = fields.String(required=True)
    qty = fields.Integer(required=True)

    class Meta:
        unknown = EXCLUDE


class OrderSchema(Schema):
    id = fields.String(required=True, data_key="orderId")
    buyer = fields.Nested(BuyerSchema, required=True)
    lines = fields.List(fields.Nested(LineSchema), required=True)

    class Meta:
        unknown = EXCLUDE
