"""Read-only public API client: report committed states after each batch."""
import event_store
import recovery

def exercise(batches, checkpoint=None, restore_after=None):
    if type(batches) is not list or len(batches) > 8:
        raise ValueError("batches:invalid_size")
    state = event_store.new_state() if checkpoint is None else recovery.restore(checkpoint)
    steps = []
    for index, batch in enumerate(batches):
        try:
            event_store.apply_batch(state, batch)
            step = {"ok": True}
        except ValueError as error:
            step = {"ok": False, "error": str(error)}
        step["state"] = event_store.snapshot(state)
        steps.append(step)
        if restore_after == index:
            state = recovery.restore(event_store.snapshot(state))
    return {"steps": steps, "final": event_store.snapshot(state)}

def replayed(batches, checkpoint=None):
    return event_store.snapshot(recovery.replay(batches, checkpoint))

def restored(checkpoint):
    return event_store.snapshot(recovery.restore(checkpoint))
