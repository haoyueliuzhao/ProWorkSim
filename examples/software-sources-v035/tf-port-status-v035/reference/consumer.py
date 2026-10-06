import adapter


def port_report(text):
    rows = adapter.port_records(text)
    return {"records": rows, "up": sum(row["state"] == "up" for row in rows),
            "down": sum(row["state"] == "down" for row in rows)}
