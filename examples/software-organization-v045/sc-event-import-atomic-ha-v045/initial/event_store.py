"""Bounded integer event import API, current implementation."""
import copy
import re

def new_state():
    return {"events": {}, "totals": {}}

def _event(value, path):
    if type(value) is not dict or set(value) != {"id", "revision", "account", "amount"}:
        raise ValueError(path + ":event_shape")
    for field in ("id", "account"):
        if type(value[field]) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,15}", value[field]):
            raise ValueError(path + "." + field + ":invalid_name")
    if type(value["revision"]) is not int or not 0 <= value["revision"] <= 1000:
        raise ValueError(path + ".revision:integer_range")
    if type(value["amount"]) is not int or not -1000 <= value["amount"] <= 1000:
        raise ValueError(path + ".amount:integer_range")

def apply_batch(state, batch):
    if type(batch) is not list or len(batch) > 8:
        raise ValueError("batch:invalid_size")
    for index, event in enumerate(batch):
        path = "batch[" + str(index) + "]"
        _event(event, path)
        old = state["events"].get(event["id"])
        if old is not None and event["revision"] < old["revision"]:
            continue
        if old is not None and event["revision"] == old["revision"] and event != old:
            raise ValueError(path + ":revision_conflict")
        state["events"][event["id"]] = copy.deepcopy(event)
        account = event["account"]
        state["totals"][account] = state["totals"].get(account, 0) + event["amount"]

def snapshot(state):
    return {"events": [copy.deepcopy(state["events"][key]) for key in sorted(state["events"])],
            "totals": dict(sorted(state["totals"].items()))}
