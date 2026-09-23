"""Finite project-declared consequences of a committed publication.

This module has no file, clock, scheduler or persistence access. The runner captures
an impact candidate when a release occurs and commits its application as a separate
event. A rule names one stable work lineage; revisions and maintenance successors
never mutate published bytes, adoption records or historical observations.
"""

import copy
import hashlib
import json

from ..policies.organization import require_authority
from .adoption import validate_policy_contract
from .projections import derive_current_work_view, rebuild_projections
from .work import current_id, revise_requirement

STAGES = frozenset({"before_read", "after_read", "output_ready", "pending", "accepted"})
EFFECTS = frozenset({"notice", "revise", "successor", "ignore"})
UPDATE_FIELDS = frozenset({"goal", "visible_requirements", "requirements"})


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:24]


def normalize_rules(state, project_id, rules):
    """Validate rules against an already planned/installed project, without mutation.

    ``source`` is either an exact object or a workspace alias. Root ``work_nodes``
    may be local package names or global node identities. Event actors must be
    real project participants; obligation-producing effects additionally require
    existing, scoped revision authority. Updates deliberately exclude ACLs,
    credentials, object identities and executable callbacks.
    """
    if not isinstance(rules, list):
        raise ValueError("Maintenance rules must be a list")
    project = state["projects"][project_id]
    normalized, seen = [], set()
    for raw in rules:
        if not isinstance(raw, dict) or set(raw) - {
            "rule_id",
            "source",
            "work_nodes",
            "when",
            "effect",
            "actor",
            "updates",
        }:
            raise ValueError("Unsupported maintenance rule fields")
        rule = copy.deepcopy(raw)
        rid = rule.get("rule_id")
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            raise ValueError("Maintenance rule IDs must be unique nonempty strings")
        seen.add(rid)
        source = rule.get("source")
        if not isinstance(source, dict) or set(source) - {"alias", "object_id", "source_project"}:
            raise ValueError("Unsupported publication source selector")
        if ("alias" in source) == ("object_id" in source):
            raise ValueError("Publication source must select exactly one alias or object")
        oid = source.get("object_id") or state["workspaces"][project_id].get(source["alias"])
        artifact = state.get("artifacts", {}).get(oid)
        if artifact is None:
            raise ValueError("Publication source selector is unknown")
        if "source_project" in source and source["source_project"] != artifact.get("project_id"):
            raise ValueError("Publication source project does not own selected object")
        source["object_id"] = oid
        nodes = rule.get("work_nodes")
        if not isinstance(nodes, list) or not nodes or any(not isinstance(n, str) for n in nodes):
            raise ValueError("Maintenance rule requires explicit work nodes")
        nodes = [node if "::" in node else f"{project_id}::{node}" for node in nodes]
        if len(nodes) != len(set(nodes)):
            raise ValueError("Maintenance work nodes must be unique")
        for node in nodes:
            item = state.get("work_items", {}).get(node)
            if item is None or item.get("project_id") != project_id or item["node_id"] != node:
                raise ValueError("Maintenance work scope must name this project's root nodes")
        stages = rule.get("when", list(sorted(STAGES)))
        if not isinstance(stages, list) or not stages or set(stages) - STAGES:
            raise ValueError("Unsupported maintenance stage")
        effect, actor = rule.get("effect"), rule.get("actor")
        if effect not in EFFECTS or actor not in project["participants"]:
            raise ValueError("Maintenance rule requires a known effect and project actor")
        if effect == "successor" and set(stages) != {"accepted"}:
            raise ValueError("Successor rules must explicitly require an accepted predecessor")
        updates = rule.get("updates", {})
        if not isinstance(updates, dict) or set(updates) - UPDATE_FIELDS:
            raise ValueError("Maintenance updates must be declarative requirement metadata")
        if effect in {"revise", "successor"} and not updates:
            raise ValueError("New work obligations require explicit requirement updates")
        if effect in {"notice", "ignore"} and updates:
            raise ValueError("Notice and ignore policies cannot change requirements")
        if "goal" in updates and (
            not isinstance(updates["goal"], str) or not updates["goal"].strip()
        ):
            raise ValueError("Maintenance goal must be nonempty text")
        if "requirements" in updates and not isinstance(updates["requirements"], dict):
            raise ValueError("Maintenance requirements must be an object")
        if "visible_requirements" in updates and (
            not isinstance(updates["visible_requirements"], list)
            or any(not isinstance(v, str) for v in updates["visible_requirements"])
        ):
            raise ValueError("Visible requirements must be text entries")
        json.dumps(updates, allow_nan=False)
        for node in nodes:
            validate_policy_contract({**state["work_items"][node], **updates})
        if effect in {"revise", "successor"}:
            for node in nodes:
                require_authority(
                    state, actor, "revise_requirement", "requirements", node, project_id=project_id
                )
        normalized.append(
            {
                **rule,
                "source": source,
                "work_nodes": nodes,
                "when": sorted(set(stages)),
                "updates": updates,
            }
        )
    return normalized


def work_stage(state, work_id, source_object_id):
    """Observe factual progress, without pretending to know a worker's intent.

    Reading means this owner explicitly read this source for this exact work and
    requirement version since the obligation became active. It is not inferred from an observation or a policy round number.
    ``output_ready`` means a declared deliverable was edited; it does not certify
    its content, completeness, or the employee's belief that it is finished.
    """
    item = state["work_items"][work_id]
    view = derive_current_work_view(state)[work_id]
    if view["status"] == "accepted":
        return "accepted"
    if view["pending_submission_id"] is not None:
        return "pending"
    if any(
        edit.get("work_item_id", edit.get("work_id")) == work_id
        and edit.get("requirement_version") == item["requirement_version"]
        for edit in item.get("artifact_edits", [])
    ):
        return "output_ready"
    reads = state.get("knowledge", {}).get(item["owner_role"], {}).get("read_artifacts", [])
    if any(
        read.get("artifact_id") == source_object_id
        and read.get("project_id") == item["project_id"]
        and read.get("work_item_id", read.get("work_id")) == work_id
        and read.get("requirement_version") == item["requirement_version"]
        and read.get("at", -1) >= item.get("activated_at", 0)
        for read in reads
    ):
        return "after_read"
    return "before_read"


def impact_identity(release_id, project_id, rule_id, target_node):
    """Dedup uses stable lineage scope, so revision cannot replay the same release."""
    return "impact-" + _digest([release_id, project_id, rule_id, target_node])


def impact_candidates(state, release):
    """Freeze matching rule, work and progress context when a release is recorded."""
    candidates = []
    for pid in sorted(release["scope"]["target_projects"]):
        project = state["projects"][pid]
        if project["status"] != "active":
            continue
        for rule in project.get("maintenance_rules", []):
            source = rule["source"]
            if source["object_id"] != release["object_id"] or (
                "source_project" in source and source["source_project"] != release["source_project"]
            ):
                continue
            for node in rule["work_nodes"]:
                identity = impact_identity(release["release_id"], pid, rule["rule_id"], node)
                if identity in state.get("maintenance_impacts", {}):
                    continue
                head = project.get("maintenance_heads", {}).get(node, node)
                wid = current_id(state, head)
                view = derive_current_work_view(state)[wid]
                if view["status"] in {"cancelled", "superseded"}:
                    continue
                stage = work_stage(state, wid, source["object_id"])
                if stage not in rule["when"]:
                    continue
                candidates.append(
                    {
                        "impact_id": identity,
                        "release_id": release["release_id"],
                        "project_id": pid,
                        "target_node": node,
                        "target_work_id": wid,
                        "stage": stage,
                        "rule_id": rule["rule_id"],
                        "actor": rule["actor"],
                        "effect": rule["effect"],
                        "updates": copy.deepcopy(rule["updates"]),
                        "source": {
                            "object_id": release["object_id"],
                            "version_id": release["version_id"],
                        },
                    }
                )
    return candidates


def successor_identity(payload):
    return (
        payload["target_node"]
        + "@m-"
        + _digest(
            [
                payload["release_id"],
                payload["project_id"],
                payload["rule_id"],
                payload["target_node"],
            ]
        )
    )


def _successor(state, payload, item):
    """Create a distinct obligation, leaving its predecessor current and accepted."""
    if derive_current_work_view(state)[item["work_item_id"]]["status"] != "accepted":
        raise ValueError("Maintenance successor requires an accepted predecessor")
    wid = successor_identity(payload)
    if wid in state["work_items"]:
        raise ValueError("Successor identity already exists without its committed impact")
    successor = copy.deepcopy(item)
    successor.update(copy.deepcopy(payload["updates"]))
    revision = (
        max(
            work["requirement_version"]
            for work in state["work_items"].values()
            if work.get("node_id") == item["node_id"]
        )
        + 1
    )
    successor.update(
        work_item_id=wid,
        requirement_version=revision,
        status="open",
        applicability="current",
        submissions=[],
        artifact_edits=[],
        blocker=None,
        blocker_ids=[],
        activated_at=state["clock"],
        origin_event=payload["impact_id"],
        previous_obligation_id=item["work_item_id"],
        maintenance_trigger=copy.deepcopy(payload),
    )
    for field in ("supersedes", "superseded_by", "cancelled_at", "cancellation_reason"):
        successor.pop(field, None)
    state["work_items"][wid] = successor
    return wid


def apply_impact(state, payload):
    """Apply one configured consequence. The caller commits this event atomically.

    Payload context was captured at publication. If another event has replaced its
    target before delivery, retain a stale-target outcome rather than silently
    applying the old event to a different obligation. Repeated delivery returns
    the recorded outcome even when the work stage has subsequently changed.
    """
    impacts = state.get("maintenance_impacts", {})
    identity = impact_identity(
        payload["release_id"], payload["project_id"], payload["rule_id"], payload["target_node"]
    )
    if payload["impact_id"] != identity:
        raise ValueError("Publication impact identity mismatch")
    if identity in impacts:
        if impacts[identity]["payload"] != payload:
            raise ValueError("Publication impact identity payload conflict")
        return {"created": False, **copy.deepcopy(impacts[identity]["result"])}
    project = state["projects"][payload["project_id"]]
    rule = next(
        (r for r in project.get("maintenance_rules", []) if r["rule_id"] == payload["rule_id"]),
        None,
    )
    if rule is None or any(rule[key] != payload[key] for key in ("actor", "effect", "updates")):
        raise ValueError("Publication impact does not match installed rule")
    if payload["target_node"] not in rule["work_nodes"] or payload["stage"] not in rule["when"]:
        raise ValueError("Publication impact escapes installed scope")
    release = next(
        (r for r in state.get("releases", []) if r["release_id"] == payload["release_id"]), None
    )
    if (
        release is None
        or release["object_id"] != rule["source"]["object_id"]
        or (
            payload["source"]
            != {"object_id": release["object_id"], "version_id": release["version_id"]}
            or payload["project_id"] not in release["scope"]["target_projects"]
        )
    ):
        raise ValueError("Publication impact requires an actual scoped release")
    item = state["work_items"][payload["target_work_id"]]
    if item["project_id"] != payload["project_id"] or item["node_id"] != payload["target_node"]:
        raise ValueError("Publication impact targets another project's work")
    effect = payload["effect"]
    result = {
        "impact_id": identity,
        "effect": effect,
        "target_work_id": item["work_item_id"],
        "stage": payload["stage"],
    }
    if project["status"] != "active":
        result["outcome"] = "project_inactive"
    elif current_id(state, item["work_item_id"]) != item["work_item_id"]:
        result["outcome"] = "stale_target"
    else:
        if effect in {"revise", "successor"}:
            require_authority(
                state,
                payload["actor"],
                "revise_requirement",
                "requirements",
                item["node_id"],
                project_id=payload["project_id"],
            )
            if effect == "revise":
                replacement = revise_requirement(
                    state, [item["work_item_id"]], payload["updates"], payload["actor"], identity
                )[item["work_item_id"]]
            else:
                replacement = _successor(state, payload, item)
            project["work_ids"].append(replacement)
            project.setdefault("maintenance_heads", {})[payload["target_node"]] = replacement
            result["new_work_id"] = replacement
        result["outcome"] = "ignored" if effect == "ignore" else "applied"
    state.setdefault("maintenance_impacts", {})[identity] = {
        "payload": copy.deepcopy(payload),
        "result": copy.deepcopy(result),
        "at": state["clock"],
    }
    rebuild_projections(state)
    return {"created": True, **result}
