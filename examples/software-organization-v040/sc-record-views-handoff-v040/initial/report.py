from records import build_records


def group_report(rows):
    records = build_records(rows)
    if records is None:
        return {"ok": False, "groups": []}
    result = []
    for row in records:
        group = next((item for item in result if item["group"] == row["group"]), None)
        if group is None:
            group = {"group": row["group"], "names": []}
            result.append(group)
        group["names"].append(row["name"])
    return {"ok": True, "groups": sorted(result, key=lambda item: item["group"])}
