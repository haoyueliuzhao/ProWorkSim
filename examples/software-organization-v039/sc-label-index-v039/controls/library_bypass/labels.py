import re


def normalize_labels(values):
    result = [value.strip().lower() for value in values]
    return result if all(re.fullmatch(r"[a-z]+", value) is not None for value in result) else None
