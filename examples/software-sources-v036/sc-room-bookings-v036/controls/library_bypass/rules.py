def validate_booking(booking):
    if 0 <= booking["start"] < booking["end"] <= 24:
        return dict(booking)
    return None
