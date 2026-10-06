from schema import Schema, And, SchemaError


def validate_booking(booking):
    validator = Schema(And({"room": str, "start": int, "end": int},
                           lambda value: 0 <= value["start"] < value["end"] <= 24))
    try:
        return validator.validate(booking)
    except SchemaError:
        return None
