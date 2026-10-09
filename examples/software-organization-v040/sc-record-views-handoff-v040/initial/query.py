from records import build_records


def select_group(rows, group):
    records = build_records(rows)
    if records is None:
        return {"ok": False, "matches": []}
    selected = [row for row in records if row["group"] == group]
    return {"ok": True, "matches": [{"position": index, "name": row["name"]}
            for index, row in enumerate(selected)]}
