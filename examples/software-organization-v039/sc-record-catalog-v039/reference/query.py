from records import build_catalog


def lookup_many(rows, keys):
    catalog = build_catalog(rows)
    if catalog is None:
        return {"ok": False, "matches": []}
    matches = []
    for key in keys:
        found = key in catalog["keys"]
        value = catalog["values"][catalog["keys"].index(key)] if found else None
        matches.append({"key": key, "found": found, "value": value})
    return {"ok": True, "matches": matches}
