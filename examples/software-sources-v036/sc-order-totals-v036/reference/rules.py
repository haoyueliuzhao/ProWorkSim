from schema import Schema, And, SchemaError


def validate_order(order):
    validator = Schema({"lines": [{"sku": str,
                                   "quantity": And(int, lambda value: value >= 1),
                                   "unit_price": And(int, lambda value: value >= 0)}],
                        "discount": And(int, lambda value: value >= 0)})
    try:
        return validator.validate(order)
    except SchemaError:
        return None
