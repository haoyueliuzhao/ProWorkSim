"""Restore public checkpoints and replay bounded batches in given order."""
import copy
import event_store

def restore(checkpoint):
    if type(checkpoint) is not dict or set(checkpoint) != {"events", "totals"}:
        raise ValueError("checkpoint:invalid")
    events, totals = checkpoint["events"], checkpoint["totals"]
    if type(events) is not list or len(events) > 8 or type(totals) is not dict:
        raise ValueError("checkpoint:invalid")
    state = event_store.new_state()
    try:
        if len({event["id"] for event in events}) != len(events):
            raise ValueError
        event_store.apply_batch(state, copy.deepcopy(events))
    except (ValueError, KeyError, TypeError):
        raise ValueError("checkpoint:invalid") from None
    if any(type(v) is not int for v in totals.values()) or state["totals"] != totals:
        raise ValueError("checkpoint:invalid")
    for event in state["events"].values():
        event["revision"] = 0
    return state

def replay(batches, checkpoint=None):
    if type(batches) is not list or len(batches) > 8:
        raise ValueError("batches:invalid_size")
    state = event_store.new_state() if checkpoint is None else restore(checkpoint)
    for batch in batches:
        event_store.apply_batch(state, batch)
    return state
