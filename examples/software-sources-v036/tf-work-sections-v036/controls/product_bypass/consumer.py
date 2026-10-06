import textfsm


def _work_items(text):
    with open("work.template", encoding="utf-8") as stream:
        parser = textfsm.TextFSM(stream)
    return [{"group": group, "item": item, "minutes": int(minutes)}
            for group, item, minutes in parser.ParseText(text)]



def work_timeline(text):
    totals, steps = {}, []
    for row in _work_items(text):
        group = row["group"]
        start = totals.get(group, 0)
        finish = start + row["minutes"]
        steps.append({"group": group, "item": row["item"], "start": start, "finish": finish})
        totals[group] = finish
    return {"steps": steps,
            "totals": [{"group": group, "minutes": minutes} for group, minutes in totals.items()]}
