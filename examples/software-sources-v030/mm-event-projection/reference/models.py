from marshmallow import Schema, fields


class EventSchema(Schema):
    title = fields.String(attribute="event_name")
    at = fields.DateTime(attribute="happened_at", format="iso")
    owner = fields.String(attribute="meta.owner")
    secret = fields.String(load_only=True)
