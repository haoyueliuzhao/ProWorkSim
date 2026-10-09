import re


def validate_columns(columns):
    if len(columns) != len(set(columns)) or not all(re.fullmatch(r"[a-z]+", name) is not None for name in columns):
        return None
    return list(columns)
