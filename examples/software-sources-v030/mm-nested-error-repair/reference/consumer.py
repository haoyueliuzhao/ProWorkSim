from marshmallow import ValidationError
from models import PersonSchema


def _paths(messages, prefix=""):
    result = []
    for key, value in messages.items():
        path = prefix + "." + str(key) if prefix else str(key)
        if isinstance(value, dict):
            result.extend(_paths(value, path))
        else:
            result.append(path)
    return sorted(result)


def validate_people(rows):
    accepted, rejected = [], []
    schema = PersonSchema()
    for index, row in enumerate(rows):
        try:
            accepted.append(schema.load(row))
        except ValidationError as error:
            rejected.append({"index": index, "fields": _paths(error.messages)})
    return {"accepted": accepted, "rejected": rejected}
