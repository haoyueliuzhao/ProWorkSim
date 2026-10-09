import re
from schema import And, Schema, SchemaError, Use


def _local_product(rows):
    name = And(str, Use(lambda value: value.strip().lower()),
               lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        validated = Schema([{"name": name, "group": name}]).validate(rows)
    except SchemaError:
        return None
    return [{"position": index, "name": row["name"], "group": row["group"]}
            for index, row in enumerate(validated)]



def select_group(rows, group):
    records = _local_product(rows)
    if records is None:
        return {"ok": False, "matches": []}
    return {"ok": True, "matches": [{"position": row["position"], "name": row["name"]}
            for row in records if row["group"] == group]}
