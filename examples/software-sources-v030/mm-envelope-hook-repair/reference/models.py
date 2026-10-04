from marshmallow import Schema, fields, pre_load


class EnvelopeSchema(Schema):
    code = fields.String(required=True)
    quantity = fields.Integer(required=True)

    @pre_load(pass_collection=True)
    def unwrap(self, data, many, **kwargs):
        return data["items"] if many else data["item"]
