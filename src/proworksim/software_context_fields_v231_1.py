"""Lossless edits inside the previously visible v230 worker observation."""

from copy import deepcopy
from .software_context_builder_v230 import compact, identity, object_text

FIELDS = frozenset(
    {
        "organization_protocol",
        "fixed_organization",
        "personal_workbench",
        "delivery_readiness",
        "dynamic_organization",
        "member_availability",
        "team_model_budget",
        "file_directory",
        "current_version_test_coverage",
    }
)
PATCHED = "fields_edited_against_previous_observation"


def pointer(path, name):
    return path + "/" + name.replace("~", "~0").replace("/", "~1")


def edits(old, new, path=""):
    if type(old) is dict and type(new) is dict:
        for k in old:
            if k not in new:
                yield {"op": "remove", "path": pointer(path, k)}
        for k, v in new.items():
            key = pointer(path, k)
            if k not in old:
                yield {"op": "add", "path": key, "value": v}
            else:
                yield from edits(old[k], v, key)
    elif type(old) is not type(new) or compact(old) != compact(new):
        yield {"op": "replace", "path": path, "value": new}


def apply_edits(old, changes):
    result = deepcopy(old)
    for change in changes:
        path = change["path"]
        if not path.startswith("/"):
            raise ValueError("An edit must identify a member of the previous object")
        names = [k.replace("~1", "/").replace("~0", "~") for k in path[1:].split("/")]
        target = result
        for key in names[:-1]:
            target = target[key]
        key = names[-1]
        if change["op"] == "remove":
            del target[key]
        elif change["op"] in ("add", "replace") and (key in target) == (change["op"] == "replace"):
            target[key] = change["value"]
        else:
            raise ValueError("Inconsistent nested edit")
    return result


def transform(wire, actor, *, restore=False):
    """Operate within this request only. Keep the first snapshot and ordinary messages intact."""
    messages = list(wire["messages"])
    previous = {}
    previous_index = None
    entries = []
    for i, msg in enumerate(messages):
        if msg["role"] != "user":
            continue
        value = object_text(msg.get("content")) or {}
        snapshot = value.get("observation")
        if isinstance(snapshot, dict):
            if snapshot.get("actor_id", actor) != actor:
                raise ValueError("Foreign snapshot")
            previous = dict(snapshot)
            previous_index = i
            continue
        delta = value.get("observation_delta")
        if not isinstance(delta, dict):
            continue
        if previous_index is None or previous_index != delta["inherits_observation_at_message"]:
            raise ValueError("Missing observation base")
        changed = delta["changed"].copy()
        if changed.get("actor_id", actor) != actor:
            raise ValueError("Foreign delta")
        fields = []
        if restore:
            fields = delta.get(PATCHED, [])
            for name in fields:
                if name not in FIELDS:
                    raise ValueError("Unknown nested field")
                changed[name] = apply_edits(previous[name], changed[name])
            full = changed
        else:
            full = delta["changed"]
            if PATCHED in delta:
                raise ValueError("Duplicate optimization pass")
            for name, new in full.items():
                old = previous.get(name)
                if name not in FIELDS or not isinstance(old, dict) or not isinstance(new, dict):
                    continue
                original = compact(new)
                if len(original) < 256:
                    continue
                updates = list(edits(old, new))
                # Require a material saving after including the field index.
                if len(compact(updates)) + len(name) + 64 >= 0.8 * len(original):
                    continue
                if compact(apply_edits(old, updates)) != original:
                    continue
                changed[name] = updates
                fields.append(name)
                entries.append(
                    {
                        "index": i,
                        "base": previous_index,
                        "field": name,
                        "edits": len(updates),
                        "full_value_sha256": identity(new),
                    }
                )
        if fields:
            replacement = {**delta, "changed": changed}
            if restore:
                del replacement[PATCHED]
            else:
                replacement[PATCHED] = fields
            messages[i] = {**msg, "content": compact({**value, "observation_delta": replacement})}
        for name in delta["removed"]:
            previous.pop(name)
        previous.update(full)
        previous_index = i
    return {**wire, "messages": messages}, entries
