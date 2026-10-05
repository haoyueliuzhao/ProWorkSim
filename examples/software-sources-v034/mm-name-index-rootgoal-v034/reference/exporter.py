from models import NameSchema


def export_names(names):
    schema = NameSchema()
    rows = schema.dump(schema.load([{"name": name} for name in names], many=True), many=True)
    return [row["name"] for row in rows]
