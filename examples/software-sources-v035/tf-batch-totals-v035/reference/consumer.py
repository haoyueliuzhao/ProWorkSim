import adapter


def batch_totals(text):
    groups = {}
    for row in adapter.batch_values(text):
        item = groups.setdefault(row["batch"], {"batch": row["batch"], "count": 0, "total": 0})
        item["count"] += 1
        item["total"] += row["value"]
    return list(groups.values())
