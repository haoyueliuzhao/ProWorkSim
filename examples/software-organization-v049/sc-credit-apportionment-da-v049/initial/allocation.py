import re


def _validated(total_cents, accounts):
    if type(total_cents) is not int or not -1000000000 <= total_cents <= 1000000000:
        raise ValueError("allocation:invalid")
    if type(accounts) is not list or not 1 <= len(accounts) <= 16:
        raise ValueError("allocation:invalid")
    seen = set()
    for account in accounts:
        if type(account) is not dict or set(account) != {"id", "weight"}:
            raise ValueError("allocation:invalid")
        name, weight = account["id"], account["weight"]
        if (type(name) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,15}", name) is None
                or name in seen or type(weight) is not int or not 1 <= weight <= 1000000):
            raise ValueError("allocation:invalid")
        seen.add(name)
    return sorted(accounts, key=lambda row: row["id"])


def allocate(total_cents, accounts):
    ordered = _validated(total_cents, accounts)
    denominator = sum(row["weight"] for row in ordered)
    sign = -1 if total_cents < 0 else 1
    return [{"id": row["id"], "cents": sign * (abs(total_cents) * row["weight"] // denominator)}
            for row in ordered]
