"""Single-world operation identities, payload conflicts and committed results.

Records are committed in the same atomic state snapshot as the business effects.
This is a bounded single-writer protocol, not distributed exactly-once delivery.
"""

import copy
import hashlib
import json

SEMANTICS_VERSION = "work-world-v0.5"


class CommandConflict(ValueError):
    pass


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def lookup_operation(state, operation_id, actor, request_digest):
    record = state.get("operation_commits", {}).get(operation_id)
    if record is None:
        return None
    if record["bound_actor"] != actor or record["request_digest"] != request_digest:
        raise CommandConflict(
            "An operation identifier is already committed with a different actor or payload"
        )
    return copy.deepcopy(record)


def record_operation(state, operation_id, actor, request_digest, result, receipt, kind):
    if operation_id in state.setdefault("operation_commits", {}):
        raise CommandConflict("Operation already committed; its effects cannot be committed twice")
    previous = state.get("state_revision", 0)
    revision = previous + 1
    receipt.update(
        transition_id=operation_id,
        bound_actor=actor,
        request_digest=request_digest,
        pre_state_revision=previous,
        semantics_version=state.get("semantics_version", SEMANTICS_VERSION),
        committed_revision=revision,
        execution_outcome="committed" if result.get("ok", True) else "rejected_attempt_committed",
    )
    record = {
        "operation_id": operation_id,
        "kind": kind,
        "bound_actor": actor,
        "request_digest": request_digest,
        "pre_state_revision": previous,
        "committed_revision": revision,
        "public_result": copy.deepcopy(result),
        "receipt": copy.deepcopy(receipt),
    }
    state["state_revision"] = revision
    state["operation_commits"][operation_id] = record
    return copy.deepcopy(record)


def validate_committed_prefix(state):
    """A trusted snapshot plus journal entries must form one committed suffix."""
    records = list(state.get("operation_commits", {}).values())
    revisions = sorted(record["committed_revision"] for record in records)
    checkpoint = state.get("checkpoint_revision", 0)
    if not revisions:
        if state.get("state_revision", checkpoint) != checkpoint:
            raise ValueError("Committed revision has no operation journal prefix")
        return
    if revisions != list(range(checkpoint + 1, state["state_revision"] + 1)):
        raise ValueError("Operation journal is not a contiguous committed prefix")
    for key, record in state["operation_commits"].items():
        if (
            record["operation_id"] != key
            or record["pre_state_revision"] + 1 != record["committed_revision"]
        ):
            raise ValueError("Inconsistent operation identity or revision")
