import re


def _name(value):
    return type(value) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,15}", value) is not None


def _validate(stock, operations):
    if type(stock) is not dict or not 1 <= len(stock) <= 12:
        raise ValueError("inventory:invalid")
    for sku, qty in stock.items():
        if not _name(sku) or type(qty) is not int or not 0 <= qty <= 1000000:
            raise ValueError("inventory:invalid")
    if type(operations) is not list or len(operations) > 24:
        raise ValueError("inventory:invalid")
    for operation in operations:
        if type(operation) is not dict or operation.get("op") not in ("reserve", "cancel"):
            raise ValueError("inventory:invalid")
        expected = {"op", "id", "items"} if operation["op"] == "reserve" else {"op", "id"}
        if set(operation) != expected or not _name(operation["id"]):
            raise ValueError("inventory:invalid")
        if operation["op"] == "reserve":
            rows = operation["items"]
            if type(rows) is not list or not 1 <= len(rows) <= 12:
                raise ValueError("inventory:invalid")
            for row in rows:
                if type(row) is not dict or set(row) != {"sku", "qty"}:
                    raise ValueError("inventory:invalid")
                if (not _name(row["sku"]) or row["sku"] not in stock
                        or type(row["qty"]) is not int or not 1 <= row["qty"] <= 1000000):
                    raise ValueError("inventory:invalid")


def _execute(available, active, operation):
    key = operation["id"]
    if operation["op"] == "reserve":
        items = {}
        for row in operation["items"]:
            items[row["sku"]] = items.get(row["sku"], 0) + row["qty"]
        if key in active or any(qty > available[sku] for sku, qty in items.items()):
            raise ValueError("inventory:conflict")
        for sku, qty in items.items():
            available[sku] -= qty
        active[key] = items
    else:
        if key not in active:
            raise ValueError("inventory:conflict")
        for sku, qty in active.pop(key).items():
            available[sku] += qty


def _result(available, active):
    return {"available": [{"sku": sku, "qty": available[sku]} for sku in sorted(available)],
            "reservations": [{"id": key, "items": [{"sku": sku, "qty": active[key][sku]}
                for sku in sorted(active[key])]} for key in sorted(active)]}


def transact(stock, operations):
    _validate(stock, operations)
    available, active = dict(stock), {}
    for operation in operations:
        _execute(available, active, operation)
    return _result(available, active)
