import adapter


def latest_readings(text):
    latest = {}
    for record in adapter.readings(text):
        latest[record["name"]] = record["value"]
    records = [{"name": name, "value": latest[name]} for name in sorted(latest)]
    return {"latest": records, "total": sum(record["value"] for record in records)}
