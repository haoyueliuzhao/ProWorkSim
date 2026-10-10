"""Bounded integer event store with atomic revision batches."""
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

def _totals(events):
    totals = {}
    for event in events.values():
        account = event["account"]
        totals[account] = totals.get(account, 0) + event["amount"]
    return dict(sorted(totals.items()))

def _state(state):
    if type(state) is not dict or set(state) != {"events", "totals"} or type(state["events"]) is not dict:
        raise ValueError("state:invalid")
    if len(state["events"]) > 8 or type(state["totals"]) is not dict:
        raise ValueError("state:invalid")
    for key, event in state["events"].items():
        _event(event, "state.events")
        if key != event["id"]:
            raise ValueError("state:invalid")
    if any(type(v) is not int for v in state["totals"].values()) or state["totals"] != _totals(state["events"]):
        raise ValueError("state:invalid")

def apply_batch(state, batch):
    _state(state)
    if type(batch) is not list or len(batch) > 8:
        raise ValueError("batch:invalid_size")
    work = state["events"]
    for index, event in enumerate(batch):
        path = "batch[" + str(index) + "]"
        _event(event, path)
        old = work.get(event["id"])
        if old is not None:
            if event["revision"] < old["revision"]:
                continue
            if event["revision"] == old["revision"]:
                if event != old:
                    raise ValueError(path + ":revision_conflict")
                continue
        work[event["id"]] = copy.deepcopy(event)
        if len(work) > 8:
            raise ValueError(path + ":store_capacity")
    state.clear()
    state.update(events=work, totals=_totals(work))

def snapshot(state):
    _state(state)
    return {"events": [copy.deepcopy(state["events"][key]) for key in sorted(state["events"])],
            "totals": copy.deepcopy(state["totals"])}
