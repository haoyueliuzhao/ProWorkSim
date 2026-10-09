import re
from schema import And, Schema, SchemaError, Use


def build_records(rows):
    name = And(str, Use(lambda value: value.strip().lower()),
               lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        validated = Schema([{"name": name, "group": name}]).validate(rows)
    except SchemaError:
        return None
    return [{"position": index, "name": row["name"], "group": row["group"]}
            for index, row in enumerate(validated)]
