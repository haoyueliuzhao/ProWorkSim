import re


def build_records(rows):
    result = []
    for index, row in enumerate(rows):
        name, group = row["name"].strip().lower(), row["group"].strip().lower()
        if re.fullmatch(r"[a-z]+", name) is None or re.fullmatch(r"[a-z]+", group) is None:
            return None
        result.append({"position": index, "name": name, "group": group})
    return result
