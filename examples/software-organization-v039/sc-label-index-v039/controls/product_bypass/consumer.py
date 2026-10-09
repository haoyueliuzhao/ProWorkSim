import re
from schema import And, Schema, SchemaError, Use


def _local_product(values):
    normalized = And(str, Use(lambda value: value.strip().lower()),
                     lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        return Schema([normalized]).validate(values)
    except SchemaError:
        return None



def index_labels(values):
    normalized = _local_product(values)
    if normalized is None:
        return {"ok": False, "names": [], "positions": []}
    names, positions = [], []
    for value in normalized:
        if value not in names:
            names.append(value)
        positions.append(names.index(value))
    return {"ok": True, "names": names, "positions": positions}
