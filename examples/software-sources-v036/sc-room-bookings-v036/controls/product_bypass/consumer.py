from schema import Schema, And, SchemaError


def _validate_booking(booking):
    validator = Schema(And({"room": str, "start": int, "end": int},
                           lambda value: 0 <= value["start"] < value["end"] <= 24))
    try:
        return validator.validate(booking)
    except SchemaError:
        return None



def schedule_bookings(bookings):
    accepted, rejected = [], []
    for index, booking in enumerate(bookings):
        value = _validate_booking(booking)
        conflict = value is not None and any(
            previous["room"] == value["room"] and
            value["start"] < previous["end"] and previous["start"] < value["end"]
            for previous in accepted)
        if value is None or conflict:
            rejected.append(index)
        else:
            accepted.append(value)
    return {"accepted": accepted, "rejected_indices": rejected,
            "hours": sum(value["end"] - value["start"] for value in accepted)}
