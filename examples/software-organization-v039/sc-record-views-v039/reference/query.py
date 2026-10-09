from records import build_records


def select_group(rows, group):
    records = build_records(rows)
    if records is None:
        return {"ok": False, "matches": []}
    return {"ok": True, "matches": [{"position": row["position"], "name": row["name"]}
            for row in records if row["group"] == group]}
