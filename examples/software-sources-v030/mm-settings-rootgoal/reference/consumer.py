from copy import deepcopy
from marshmallow import ValidationError
from models import SettingsSchema


def apply_settings(base, patch):
    schema = SettingsSchema()
    state = schema.load(base)
    try:
        change = schema.load(patch, partial=True)
    except ValidationError:
        return {"ok": False, "public": schema.dump(state), "state": state}
    merged = deepcopy(state)
    for key, value in change.items():
        if key == "network":
            merged[key].update(value)
        else:
            merged[key] = value
    return {"ok": True, "public": schema.dump(merged), "state": merged}
