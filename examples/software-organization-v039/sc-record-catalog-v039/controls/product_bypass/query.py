import re
from schema import And, Or, Schema, SchemaError


def _local_product(rows):
    name = And(str, lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        validated = Schema([{"key": name, "value": Or(str, int, bool, type(None))}]).validate(rows)
    except SchemaError:
        return None
    keys, values = [], []
    for row in validated:
        if row["key"] not in keys:
            keys.append(row["key"])
            values.append(row["value"])
        else:
            values[keys.index(row["key"])] = row["value"]
    return {"keys": keys, "values": values}



def lookup_many(rows, keys):
    catalog = _local_product(rows)
    if catalog is None:
        return {"ok": False, "matches": []}
    matches = []
    for key in keys:
        found = key in catalog["keys"]
        value = catalog["values"][catalog["keys"].index(key)] if found else None
        matches.append({"key": key, "found": found, "value": value})
    return {"ok": True, "matches": matches}
