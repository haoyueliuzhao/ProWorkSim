import rules


def price_order(order):
    value = rules.validate_order(order)
    if value is None:
        return {"ok": False, "lines": [], "subtotal": 0, "discount": 0, "due": 0}
    lines = [{"sku": line["sku"], "quantity": line["quantity"], "unit_price": line["unit_price"],
              "amount": line["quantity"] * line["unit_price"]} for line in value["lines"]]
    subtotal = sum(line["amount"] for line in lines)
    return {"ok": True, "lines": lines, "subtotal": subtotal,
            "discount": value["discount"], "due": max(0, subtotal - value["discount"])}
