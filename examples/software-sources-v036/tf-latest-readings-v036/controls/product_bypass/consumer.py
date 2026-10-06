import textfsm


def _readings(text):
    with open("readings.template", encoding="utf-8") as stream:
        parser = textfsm.TextFSM(stream)
    return [{"name": name, "value": int(value)} for name, value in parser.ParseText(text)]



def latest_readings(text):
    latest = {}
    for record in _readings(text):
        latest[record["name"]] = record["value"]
    records = [{"name": name, "value": latest[name]} for name in sorted(latest)]
    return {"latest": records, "total": sum(record["value"] for record in records)}
