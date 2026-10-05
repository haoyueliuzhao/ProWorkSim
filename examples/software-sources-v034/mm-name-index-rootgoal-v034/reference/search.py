from models import NameSchema


def find_matches(names, query):
    schema = NameSchema()
    rows = schema.dump(schema.load([{"name": name} for name in names], many=True), many=True)
    target = schema.dump(schema.load({"name": query}))["name"]
    return [index for index, row in enumerate(rows) if row["name"] == target]
