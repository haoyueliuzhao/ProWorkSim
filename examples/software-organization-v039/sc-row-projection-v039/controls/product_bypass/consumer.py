import re
from schema import And, Schema, SchemaError


def _local_product(columns):
    name = And(str, lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        return Schema(And([name], lambda values: len(values) == len(set(values)))).validate(columns)
    except SchemaError:
        return None



def project_rows(rows, columns):
    selected = _local_product(columns)
    if selected is None:
        return {"ok": False, "columns": [], "rows": []}
    return {"ok": True, "columns": selected,
            "rows": [[row.get(name) for name in selected] for row in rows]}
