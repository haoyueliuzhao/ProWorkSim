import reader


def summarize(script):
    records = reader.statement_records(script)
    counts = {"SELECT": 0, "UPDATE": 0, "DELETE": 0}
    for record in records:
        counts[record["kind"]] += 1
    return {"statements": records, "counts": counts, "total": len(records)}
