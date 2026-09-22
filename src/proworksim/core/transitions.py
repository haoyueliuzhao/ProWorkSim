"""Finite action frames, history preservation and explicit Apply/Derive receipts.

This module knows state containers, not business object names or correct answers.
External adapters own file rollback and persistence under a single-writer lock.
"""

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionFrame:
    name: str
    paths: tuple[tuple[str, ...], ...]
    derived_paths: tuple[tuple[str, ...], ...] = ()
    immutable_submission_extensions: tuple[str, ...] = ()
    append_only_extensions: tuple[str, ...] = ()


def changed_paths(before, after, path=()):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child = (*path, str(key))
            if key not in before:
                if isinstance(after[key], dict) and after[key]:
                    result.extend(changed_paths({}, after[key], child))
                else:
                    result.append(child)
            elif key not in after:
                if isinstance(before[key], dict) and before[key]:
                    result.extend(changed_paths(before[key], {}, child))
                else:
                    result.append(child)
            else:
                result.extend(changed_paths(before[key], after[key], child))
        return result
    if before != after:
        return [path]
    return []


def within(path, prefixes):
    return any(path[: len(prefix)] == prefix for prefix in prefixes)


def preserve_history(before, after, submission_extensions=(), append_extensions=()):
    """Enforce immutable facts, while allowing separate review/applicability fields."""
    for aid, artifact in before.get("artifacts", {}).items():
        newer = after.get("artifacts", {}).get(aid)
        if newer is None:
            raise ValueError(f"Historical object removed: {aid}")
        for vid, version in artifact.get("versions", {}).items():
            other = newer.get("versions", {}).get(vid)
            if other is None:
                raise ValueError(f"Historical version removed: {aid}/{vid}")
            for key in (
                "artifact_id",
                "version_id",
                "owner",
                "sha256",
                "logical_time",
                "derived_from",
                "credential",
            ):
                # A first formal attestation may be attached to an existing
                # immutable version; once attached it cannot be rewritten.
                if key == "credential" and key not in version:
                    continue
                if version.get(key) != other.get(key):
                    raise ValueError(f"Historical version fact changed: {aid}/{vid}/{key}")
    for key in ("messages", "interactions", "requirement_events") + append_extensions:
        previous = before.get(key, [])
        if after.get(key, [])[: len(previous)] != previous:
            raise ValueError(f"Append-only history changed: {key}")
    for key, attestation in before.get("attestations", {}).items():
        if after.get("attestations", {}).get(key) != attestation:
            raise ValueError(f"Formal attestation changed: {key}")
    for wid, work in before.get("work_items", {}).items():
        newer = after.get("work_items", {}).get(wid)
        if newer is None:
            raise ValueError(f"Historical work removed: {wid}")
        later = {s["submission_id"]: s for s in newer.get("submissions", [])}
        for sub in work.get("submissions", []):
            other = later.get(sub["submission_id"])
            if other is None:
                raise ValueError("Historical submission removed")
            for key in (
                "submission_id",
                "requirement_version",
                "actor_id",
                "artifact_versions",
                "answer",
                "at",
                "context_versions",
                "required_credentials",
                "requirement_snapshot",
            ) + submission_extensions:
                if sub.get(key) != other.get(key):
                    raise ValueError(f"Historical submission fact changed: {wid}/{key}")
            review = sub.get("review")
            if review is not None and review != other.get("review"):
                raise ValueError("Completed historical review changed")


def execute_transition(state, frame, apply, derive=lambda state: None):
    """Check an adapter's actual effects before commit; roll back state on failure."""
    before = copy.deepcopy(state)
    try:
        result = apply()
        applied = copy.deepcopy(state)
        derive(state)
        changes = changed_paths(before, state)
        prohibited = [
            path for path in changes if not within(path, frame.paths + frame.derived_paths)
        ]
        if prohibited:
            raise ValueError(
                f"Action {frame.name} changed objects outside its frame: {prohibited[:3]}"
            )
        # Derive may only update declared projections, never primary facts/files.
        if any(not within(path, frame.derived_paths) for path in changed_paths(applied, state)):
            raise ValueError("Derive changed a primary fact outside its projection scope")
        preserve_history(
            before, state, frame.immutable_submission_extensions, frame.append_only_extensions
        )
    except Exception:
        state.clear()
        state.update(before)
        raise
    return result, {
        "contract": frame.name,
        "allowed_business_paths": [list(p) for p in frame.paths],
        "direct_changes": [list(p) for p in changes if not within(p, frame.derived_paths)],
        "derived_changes": [list(p) for p in changes if within(p, frame.derived_paths)],
        "history_preserved": True,
        "frame_respected": True,
    }


def ordered_due_events(events, clock):
    """Equal due times follow insertion order, independent of random event IDs."""
    return [
        event
        for _, event in sorted(enumerate(events), key=lambda pair: (pair[1]["at"], pair[0]))
        if event["at"] <= clock
    ]
