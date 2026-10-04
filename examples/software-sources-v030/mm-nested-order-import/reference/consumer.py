from models import OrderSchema


def import_orders(rows):
    orders = OrderSchema().load(rows, many=True)
    return [{"id": row["id"], "email": row["buyer"]["email"],
             "units": sum(line["qty"] for line in row["lines"]),
             "skus": [line["sku"] for line in row["lines"]]} for row in orders]
