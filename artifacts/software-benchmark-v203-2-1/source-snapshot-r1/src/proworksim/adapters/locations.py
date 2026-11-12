"""Bounded exact JSON locations for readable issue targets and evidence."""

import json


def read_location(kind, content, locator):
    if kind != "json":
        raise ValueError("Located review currently supports JSON objects")
    if (not isinstance(locator, list) or not 1 <= len(locator) <= 20
            or any(not (isinstance(part, str) and part or type(part) is int and part >= 0)
                   for part in locator)):
        raise ValueError("Locator must be a bounded JSON path of keys or array indexes")
    value = json.loads(content)
    for part in locator:
        if isinstance(value, dict) and isinstance(part, str) and part in value:
            value = value[part]
        elif isinstance(value, list) and type(part) is int and part < len(value):
            value = value[part]
        else:
            raise ValueError("Location is absent from the exact referenced version")
    return value
