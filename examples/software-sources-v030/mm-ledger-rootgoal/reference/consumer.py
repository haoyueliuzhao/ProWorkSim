from marshmallow import ValidationError
from models import CentsField, LedgerSchema


def ledger_report(rows):
    accepted, rejected, seen = [], [], set()
    schema = LedgerSchema()
    total = 0
    for index, row in enumerate(rows):
        try:
            item = schema.load(row)
        except ValidationError:
            rejected.append({"index": index, "reason": "invalid"})
            continue
        if item["id"] in seen:
            rejected.append({"index": index, "reason": "duplicate"})
            continue
        seen.add(item["id"])
        accepted.append(schema.dump(item))
        total += item["amount"]
    return {"accepted": accepted, "rejected": rejected,
            "total": CentsField()._serialize(total, None, None)}
