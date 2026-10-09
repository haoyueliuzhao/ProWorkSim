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



def catalog_rows(rows):
    catalog = _local_product(rows)
    if catalog is None:
        return {"ok": False, "rows": []}
    return {"ok": True, "rows": [{"key": key, "value": value}
            for key, value in zip(catalog["keys"], catalog["values"])]}
