from models import RecordSchema


def catalog(records):
    schema = RecordSchema()
    loaded = schema.load(records, many=True)
    rendered = schema.dump(loaded, many=True)
    return {"records": rendered, "total_quantity": sum(row["quantity"] for row in loaded)}
