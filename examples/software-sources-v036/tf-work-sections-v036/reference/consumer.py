import adapter


def work_timeline(text):
    totals, steps = {}, []
    for row in adapter.work_items(text):
        group = row["group"]
        start = totals.get(group, 0)
        finish = start + row["minutes"]
        steps.append({"group": group, "item": row["item"], "start": start, "finish": finish})
        totals[group] = finish
    return {"steps": steps,
            "totals": [{"group": group, "minutes": minutes} for group, minutes in totals.items()]}
