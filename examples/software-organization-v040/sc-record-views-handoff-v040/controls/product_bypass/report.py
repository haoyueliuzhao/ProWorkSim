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



def group_report(rows):
    records = _local_product(rows)
    if records is None:
        return {"ok": False, "groups": []}
    result = []
    for row in records:
        group = next((item for item in result if item["group"] == row["group"]), None)
        if group is None:
            group = {"group": row["group"], "names": []}
            result.append(group)
        group["names"].append(row["name"])
    return {"ok": True, "groups": result}
