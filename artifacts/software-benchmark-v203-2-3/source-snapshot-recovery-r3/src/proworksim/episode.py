"""Readable episode boundaries independent of later progress in a live world.

A boundary stores facts and independent copies of every committed file version.
History is evaluated with a read-only Store; reopening a WorldCore (and its
recovery/materialization) is neither needed nor permitted by this module.
"""

import copy
import uuid
from pathlib import Path

from .audit import code_identity
from .core.work import current_id
from .evaluation import assess_episode, evaluator_fault
from .storage import Store, atomic_write, digest, json_bytes, read_json

EPISODE_VERSION = "episode-manifest-v0.11"


def _experience(value):
    if not isinstance(value, dict) or not isinstance(value.get("events"), list):
        raise ValueError("Episode boundary requires a full experience snapshot")
    for index, event in enumerate(value["events"]):
        if not isinstance(event, dict) or event.get("sequence") != index:
            raise ValueError("Boundary experience must retain consecutive original sequence")
    json_bytes(value)
    return copy.deepcopy(value)


def _identity(state):
    return {key: state[key] for key in ("world_id", "instance_id", "branch_id")}


def _manifest_path(destination):
    path = Path(destination).resolve()
    return path if path.name == "manifest.json" else path / "manifest.json"


def _outside_world(world, destination):
    root = Path(destination).resolve()
    live = world.store.root.resolve()
    if root == live or live in root.parents or root in live.parents:
        raise ValueError("Episode archive must be outside and separate from the live world")
    return root


def _capture_boundary(world, destination):
    destination.mkdir(parents=True, exist_ok=False)
    files = []
    with world.store.lock():
        state = copy.deepcopy(world.store.load())
        snapshot_store = Store(destination)
        atomic_write(snapshot_store.control / "state.json", json_bytes(state))
        for aid, artifact in sorted(state["artifacts"].items()):
            for vid, version in sorted(artifact["versions"].items()):
                target = snapshot_store.version_path(artifact, vid)
                entry = {
                    "object_id": aid,
                    "version_id": vid,
                    "path": str(target.relative_to(destination)),
                    "committed_sha256": version["sha256"],
                }
                try:
                    content = world.store.version_path(artifact, vid).read_bytes()
                except OSError as exc:
                    entry.update(availability="unavailable", reason=str(exc))
                else:
                    # Copy bytes, not a hardlink to a subsequently mutable inode.
                    atomic_write(target, content)
                    entry.update(
                        availability="available", sha256=digest(content), bytes=len(content)
                    )
                files.append(entry)
    return {
        "path": destination.name,
        "identity": _identity(state),
        "state": {"path": "control/state.json", "sha256": digest(json_bytes(state))},
        "clock": state["clock"],
        "state_revision": state.get("state_revision"),
        "files": files,
    }, state


def begin_episode(
    world,
    destination,
    *,
    experience,
    work_ids,
    scenario,
    policies,
    work_nodes=(),
    parent_episode_id=None,
    episode_id=None,
):
    """Fix responsibility and capture a readable start before staff actions.

    ``work_ids`` selects exact obligations; ``work_nodes`` additionally follows
    declared nodes to whichever current editions exist at this episode's end.
    Policies/scenario are supplied version/config facts, never inferred identities.
    """
    root = _outside_world(world, destination)
    history = _experience(experience)
    if not isinstance(work_ids, (list, tuple)) or not isinstance(work_nodes, (list, tuple)):
        raise ValueError("Episode responsibility must be explicit work/node lists")
    if any(not isinstance(wid, str) or not wid for wid in [*work_ids, *work_nodes]):
        raise ValueError("Episode work/node identities must be nonempty strings")
    if len(set(work_ids)) != len(work_ids) or len(set(work_nodes)) != len(work_nodes):
        raise ValueError("Episode responsibility identities must be distinct")
    if not isinstance(scenario, dict) or not isinstance(policies, dict):
        raise ValueError("Episode scenario and policy versions/configuration must be objects")
    state = world.store.load()
    if any(wid not in state["work_items"] for wid in work_ids):
        raise ValueError("Unknown exact episode responsibility")
    known_nodes = {item["node_id"] for item in state["work_items"].values()}
    if not set(work_nodes) <= known_nodes:
        raise ValueError("Episode nodes must be declared in the start world")
    json_bytes({"scenario": scenario, "policies": policies})
    root.mkdir(parents=True, exist_ok=False)
    start, _ = _capture_boundary(world, root / "start")
    atomic_write(root / "start-experience.json", json_bytes(history))
    manifest = {
        "version": EPISODE_VERSION,
        "episode_id": episode_id or str(uuid.uuid4()),
        "status": "open",
        "identity": start["identity"],
        "parent_episode_id": parent_episode_id,
        "responsibility": {"work_ids": list(work_ids), "work_nodes": list(work_nodes)},
        "scenario": copy.deepcopy(scenario),
        "policies": copy.deepcopy(policies),
        "source_start": code_identity(),
        "start": start,
        "experience_start": {
            "path": "start-experience.json",
            "sha256": digest(json_bytes(history)),
            "event_count": len(history["events"]),
        },
    }
    atomic_write(root / "manifest.json", json_bytes(manifest))
    return {**manifest, "manifest_path": str(root / "manifest.json")}


def _selected(state, responsibility):
    exact = set(responsibility["work_ids"])
    nodes = set(responsibility["work_nodes"])
    exact = {wid for wid in exact if state["work_items"][wid]["node_id"] not in nodes}
    for node in nodes:
        editions = [item for item in state["work_items"].values() if item["node_id"] == node]
        if not editions:
            raise ValueError("Declared episode node no longer has a work identity")
        project = state["projects"][editions[0]["project_id"]]
        head = project.get("maintenance_heads", {}).get(node, editions[0].get("root_work_id", node))
        selected = current_id(state, head)
        if selected not in state["work_items"] or state["work_items"][selected]["node_id"] != node:
            raise ValueError("Current maintenance head differs from its declared episode node")
        exact.add(selected)
    return sorted(exact)


def _prior_node_obligations(state, responsibility, selected):
    return _fixed_deliveries(
        state,
        sorted(
            wid
            for wid, item in state["work_items"].items()
            if item["node_id"] in responsibility["work_nodes"] and wid not in selected
        ),
    )


def _fixed_deliveries(state, selected):
    result = {}
    for wid in selected:
        item = state["work_items"][wid]
        sub = item["submissions"][-1] if item["submissions"] else None
        result[wid] = {
            "requirement_version": item["requirement_version"],
            "submission_id": sub["submission_id"] if sub else None,
            "artifact_versions": copy.deepcopy(sub["artifact_versions"]) if sub else {},
            "review": copy.deepcopy(sub.get("review")) if sub else None,
            "status": item["status"],
        }
    return result


def finish_episode(world, destination, *, experience, termination):
    """Close once after a complete action/runner return, without ending the world."""
    path = _manifest_path(destination)
    root = _outside_world(world, path.parent)
    manifest = read_json(path)
    if manifest.get("version") != EPISODE_VERSION or manifest.get("status") != "open":
        raise ValueError("Only an open current episode manifest can be closed")
    history = _experience(experience)
    beginning = read_json(root / manifest["experience_start"]["path"])
    if digest(json_bytes(beginning)) != manifest["experience_start"]["sha256"]:
        raise ValueError("Episode start experience changed")
    start = manifest["experience_start"]["event_count"]
    if history["events"][:start] != beginning["events"]:
        raise ValueError("Episode experience must extend its exact original prefix")
    if not isinstance(termination, dict) or not isinstance(termination.get("status"), str):
        raise ValueError("Episode termination must declare runner status and supporting facts")
    if _identity(world.store.load()) != manifest["identity"]:
        raise ValueError("Episode finish world instance or branch does not match its start")
    end, state = _capture_boundary(world, root / "end")
    if end["identity"] != manifest["identity"]:
        raise ValueError("World identity changed while capturing the end boundary")
    selected = _selected(state, manifest["responsibility"])
    atomic_write(root / "experience.json", json_bytes(history))
    manifest.update(
        status="closed",
        end=end,
        source_end=code_identity(),
        termination=copy.deepcopy(termination),
        selected_work_ids=selected,
        fixed_deliveries=_fixed_deliveries(state, selected),
        prior_node_obligations=_prior_node_obligations(state, manifest["responsibility"], selected),
        experience={
            "path": "experience.json",
            "sha256": digest(json_bytes(history)),
            "start": start,
            "end": len(history["events"]),
            "interval": "start inclusive, end exclusive; original event sequence retained",
        },
    )
    atomic_write(path, json_bytes(manifest))
    return {**manifest, "manifest_path": str(path)}


def _relative(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Episode evidence must use a relative path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Episode evidence path escapes archive")
    return path


def _read_boundary(root, boundary):
    base = _relative(root, boundary["path"])
    raw = _relative(base, boundary["state"]["path"]).read_bytes()
    if digest(raw) != boundary["state"]["sha256"]:
        raise ValueError("Episode boundary state was changed")
    store = Store(base)
    state = store.load()
    if _identity(state) != boundary["identity"]:
        raise ValueError("Episode boundary identity differs from manifest")
    for entry in boundary["files"]:
        path = _relative(base, entry["path"])
        if entry["availability"] == "unavailable":
            if path.exists():
                raise ValueError("Captured unavailable file appeared after episode ended")
        elif digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError("Episode boundary file was changed")
    return store, state


def assess_historical_episode(destination, *, independent_targets=(), process_requirements=()):
    """Evaluate the end boundary; the current live world is never an input."""
    path = _manifest_path(destination)
    root = path.parent
    try:
        manifest = read_json(path)
        if manifest.get("version") != EPISODE_VERSION or manifest.get("status") != "closed":
            raise ValueError("Historical assessment requires a closed episode")
        _, start_state = _read_boundary(root, manifest["start"])
        store, state = _read_boundary(root, manifest["end"])
        if (
            _identity(start_state) != manifest["identity"]
            or _identity(state) != manifest["identity"]
        ):
            raise ValueError("Episode state identity differs from manifest")
        selected = _selected(state, manifest["responsibility"])
        if (
            selected != manifest["selected_work_ids"]
            or _fixed_deliveries(state, selected) != manifest["fixed_deliveries"]
        ):
            raise ValueError("Manifest fixed submissions do not match the readable end state")
        raw = _relative(root, manifest["experience"]["path"]).read_bytes()
        if digest(raw) != manifest["experience"]["sha256"]:
            raise ValueError("Episode end experience was changed")
        history = _experience(read_json(_relative(root, manifest["experience"]["path"])))
        beginning = _experience(read_json(_relative(root, manifest["experience_start"]["path"])))
        if digest(json_bytes(beginning)) != manifest["experience_start"]["sha256"]:
            raise ValueError("Episode start experience was changed")
        start, end = manifest["experience"]["start"], manifest["experience"]["end"]
        if (
            start != len(beginning["events"])
            or end != len(history["events"])
            or history["events"][:start] != beginning["events"]
        ):
            raise ValueError("Episode interval does not extend the original experience")
        targets = copy.deepcopy(list(independent_targets))
        for target in targets:
            wid = target.get("work_id")
            if wid not in selected:
                raise ValueError("Independent target is outside the fixed episode responsibility")
            fixed = manifest["fixed_deliveries"][wid]["submission_id"]
            if target.get("submission_id") not in {None, fixed}:
                raise ValueError("Independent target attempts to select another episode submission")
            if fixed is not None:
                target["submission_id"] = fixed
        sliced = {
            "version": history.get("version"),
            "sequence_start": start,
            "events": copy.deepcopy(history["events"][start:end]),
        }
        assessment = assess_episode(
            store,
            state,
            sliced,
            work_ids=selected,
            independent_targets=targets,
            process_requirements=process_requirements,
        )
        assessment["historical_episode"] = {
            "version": EPISODE_VERSION,
            "episode_id": manifest["episode_id"],
            "manifest_sha256": digest(path.read_bytes()),
            "identity": manifest["identity"],
            "termination": copy.deepcopy(manifest["termination"]),
            "responsibility": copy.deepcopy(manifest["responsibility"]),
            "fixed_deliveries": copy.deepcopy(manifest["fixed_deliveries"]),
            "prior_node_obligations": copy.deepcopy(manifest.get("prior_node_obligations", {})),
            "node_bindings": {
                node: next(wid for wid in selected if state["work_items"][wid]["node_id"] == node)
                for node in manifest["responsibility"]["work_nodes"]
            },
            "start_fixed_deliveries": _fixed_deliveries(
                start_state, [wid for wid in selected if wid in start_state["work_items"]]
            ),
            "experience_interval": {"start": start, "end": end},
            "start_state_sha256": manifest["start"]["state"]["sha256"],
            "end_state_sha256": manifest["end"]["state"]["sha256"],
            "scope": "Only readable episode snapshots and captured versions; no live-world lookup",
        }
        return assessment
    except (OSError, ValueError, KeyError) as exc:
        return {
            "version": EPISODE_VERSION,
            "assessment_execution": {
                "status": "source_unavailable",
                "reason": str(exc),
                "boundary": "episode_evidence",
                "attribution": "missing_changed_or_invalid_episode_evidence",
            },
        }
    except Exception as exc:
        return {
            "version": EPISODE_VERSION,
            "assessment_execution": evaluator_fault(exc, boundary="historical_episode_assessment"),
        }
