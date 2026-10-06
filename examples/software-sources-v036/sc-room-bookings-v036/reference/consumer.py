import rules


def schedule_bookings(bookings):
    accepted, rejected = [], []
    for index, booking in enumerate(bookings):
        value = rules.validate_booking(booking)
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
