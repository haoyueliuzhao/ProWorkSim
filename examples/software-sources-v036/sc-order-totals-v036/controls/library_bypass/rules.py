import copy


def validate_order(order):
    if order["discount"] < 0 or any(line["quantity"] < 1 or line["unit_price"] < 0 for line in order["lines"]):
        return None
    return copy.deepcopy(order)
