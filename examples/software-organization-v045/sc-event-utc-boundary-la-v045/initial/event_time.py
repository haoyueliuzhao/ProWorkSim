"""Bounded explicit-offset event timestamp API."""
from datetime import datetime, timezone
import re

_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})")

def utc_date_key(timestamp):
    if type(timestamp) is not str or not _FORM.fullmatch(timestamp):
        raise ValueError("timestamp:invalid")
    if timestamp[-1] != "Z":
        hours, minutes = int(timestamp[-5:-3]), int(timestamp[-2:])
        if hours > 14 or minutes > 59 or hours == 14 and minutes != 0:
            raise ValueError("timestamp:invalid")
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        offset = value.utcoffset().total_seconds()
        if not 2000 <= value.year <= 2099 or abs(offset) > 14 * 3600:
            raise ValueError
        return value.date().isoformat()
    except (ValueError, OverflowError):
        raise ValueError("timestamp:invalid") from None
