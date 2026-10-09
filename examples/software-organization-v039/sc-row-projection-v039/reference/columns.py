import re
from schema import And, Schema, SchemaError


def validate_columns(columns):
    name = And(str, lambda value: re.fullmatch(r"[a-z]+", value) is not None)
    try:
        return Schema(And([name], lambda values: len(values) == len(set(values)))).validate(columns)
    except SchemaError:
        return None
