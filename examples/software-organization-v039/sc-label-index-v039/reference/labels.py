import re
from schema import And, Schema, SchemaError, Use


def normalize_labels(values):
    normalized = And(str, Use(lambda value: value.strip().lower()),
                     lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        return Schema([normalized]).validate(values)
    except SchemaError:
        return None
