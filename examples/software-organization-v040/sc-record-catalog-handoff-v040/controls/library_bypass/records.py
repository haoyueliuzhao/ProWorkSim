import re


def build_catalog(rows):
    keys, values = [], []
    for row in rows:
        if re.fullmatch(r"[a-z]+", row["key"]) is None:
            return None
        if row["key"] not in keys:
            keys.append(row["key"])
            values.append(row["value"])
        else:
            values[keys.index(row["key"])] = row["value"]
    return {"keys": keys, "values": values}
