from marshmallow import ValidationError
from models import PersonSchema


def validate_people(rows):
    accepted, rejected = [], []
    schema = PersonSchema()
    for index, row in enumerate(rows):
        try:
            accepted.append(schema.load(row))
        except ValidationError as error:
            rejected.append({"index": index, "fields": sorted(error.messages)})
    return {"accepted": accepted, "rejected": rejected}
