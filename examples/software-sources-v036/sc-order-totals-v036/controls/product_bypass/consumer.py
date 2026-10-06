from schema import Schema, And, SchemaError


def _validate_order(order):
    validator = Schema({"lines": [{"sku": str,
                                   "quantity": And(int, lambda value: value >= 1),
                                   "unit_price": And(int, lambda value: value >= 0)}],
                        "discount": And(int, lambda value: value >= 0)})
    try:
        return validator.validate(order)
    except SchemaError:
        return None



def price_order(order):
    value = _validate_order(order)
    if value is None:
        return {"ok": False, "lines": [], "subtotal": 0, "discount": 0, "due": 0}
    lines = [{"sku": line["sku"], "quantity": line["quantity"], "unit_price": line["unit_price"],
              "amount": line["quantity"] * line["unit_price"]} for line in value["lines"]]
    subtotal = sum(line["amount"] for line in lines)
    return {"ok": True, "lines": lines, "subtotal": subtotal,
            "discount": value["discount"], "due": max(0, subtotal - value["discount"])}
