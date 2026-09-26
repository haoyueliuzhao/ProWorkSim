"""Deterministic public presentation, with exact immutable receipt provenance.

This layer may omit metadata from a submission/default inspection; it never creates a
read, chooses a version, changes a tool argument, or summarizes file contents.
"""

import copy

from .core.journal import canonical_digest
from .storage import digest, json_bytes

PRESENTATION_VERSION = "work-presentation-v0.14"
PRESENTATIONS = ("v13", "full_v14", "compact_v14")
MARKER = "public_presentation"


def observation_projection(original, presentation):
    """Keep all currently public work data and required runtime identity."""
    if presentation not in PRESENTATIONS:
        raise ValueError("Unknown public presentation")
    return copy.deepcopy(original), {
        "omitted_fields": [],
        "reason": "Observation is identical across presentation arms; world/instance/branch/actor identity is required by the runtime binding. All contracts, routes and versions remain.",
    }


def project_response(raw, *, action, arguments, profile, project_id, presentation):
    """Pure projection; full inspection remains a real same-tool request.

    Default inspection keeps submitted versions, exact input bindings and
    structure. All omitted fixed contract/history data can be obtained by an
    explicit inspect_submission(include_contract=True) call, subject to the
    same real world authorization as the first call. Read bodies never change.
    """
    if presentation not in PRESENTATIONS:
        raise ValueError("Unknown public presentation")
    selected = copy.deepcopy(raw)
    reasons = []
    if presentation != "compact_v14" or not isinstance(raw, dict) or not raw.get("ok"):
        return selected, reasons
    if action == "submit" or (action == "inspect_submission" and arguments.get("include_contract") is not True):
        result = selected.get("result", {})
        snapshot = result.get("requirement_snapshot")
        if isinstance(snapshot, dict):
            kept = {key: copy.deepcopy(snapshot[key]) for key in (
                "goal", "owner_role", "approval_policy", "deliverable_contract",
                "required_credentials", "requirement_dimension", "purpose",
            ) if key in snapshot}
            requirements = snapshot.get("requirements", {})
            if isinstance(requirements, dict):
                kept["requirements"] = {
                    key: copy.deepcopy(requirements[key])
                    for key in ("reporting_period", "public_structure", "review_contract")
                    if key in requirements
                }
            result["requirement_snapshot"] = kept
            result["requirement_snapshot_complete"] = False
            result["read_full_inspection"] = {
                "tool": "inspect_submission",
                "arguments": {
                    "work_id": arguments["work_id"],
                    "submission_id": result["submission_id"],
                    "include_contract": True,
                },
                "returns": "Exact original fixed contract and complete inspection metadata. No correctness answer.",
            }
            reasons.append("Compact submission/inspection retains fixed references, goal, approval/credential conditions and deliverable structure; the complete immutable contract remains explicitly retrievable.")
        for binding in result.get("adoption_snapshot", {}).values():
            if isinstance(binding, dict):
                for key in ("history", "work_ids", "adoption_id", "project_id", "work_id", "actor_id", "at"):
                    binding.pop(key, None)
        result["artifact_read_tool"] = "read_version(reference={object_id, version_id}); artifact_versions lists the exact submitted versions, not workspace-current versions."
        reasons.append("Default adoption snapshot keeps every exact version, alias, requirement version, policy and target; provenance history is available from full inspection.")
    # Reads, query results, build results, refusals and full inspections are
    # returned exactly. Avoid replacing useful short payloads by bulky markers.
    if selected != raw:
        selected[MARKER] = {
            "version": PRESENTATION_VERSION,
            "variant": presentation,
            "profile": profile,
            "project_id": project_id,
            "raw_response_sha256": digest(json_bytes(raw)),
        }
    return selected, reasons


def response_matches_receipt(commit, public, *, action, arguments=None):
    """Accept identity or exactly recomputed projection, never a subset match.

    The compact marker is bound to the real command's request digest, including
    actor, project, actual tool arguments and role interface profile. Thus it
    cannot legitimize an arbitrary fabricated response or relabel a core tool.
    """
    if not isinstance(commit, dict) or not isinstance(public, dict):
        return False
    raw = commit.get("public_result")
    if raw == public:
        return True
    if not isinstance(raw, dict) or not isinstance(arguments, dict):
        return False
    marker = public.get(MARKER)
    if not isinstance(marker, dict) or set(marker) != {
        "version", "variant", "profile", "project_id", "raw_response_sha256"
    }:
        return False
    if marker.get("version") != PRESENTATION_VERSION or marker.get("variant") != "compact_v14":
        return False
    # Runtime import avoids the public interface/presentation import cycle.
    from .work_interface import V14_INTERFACE, V14_PROFILES
    profile = marker.get("profile")
    if profile not in {V14_INTERFACE + ":" + role for role in V14_PROFILES}:
        return False
    if action not in V14_PROFILES[profile.split(":")[-1]]:
        return False
    if commit.get("receipt", {}).get("contract") != action:
        return False
    pid = marker.get("project_id")
    if not isinstance(pid, str) or not pid:
        return False
    request_digest = canonical_digest({
        "actor": commit.get("bound_actor"), "context": pid,
        "action": "project_action",
        "arguments": {"project_id": pid, "tool": action, "arguments": arguments,
                      "interface_profile": profile},
    })
    if request_digest != commit.get("request_digest"):
        return False
    try:
        expected, _ = project_response(raw, action=action, arguments=arguments,
                                       profile=profile, project_id=pid,
                                       presentation="compact_v14")
    except (KeyError, TypeError, ValueError):
        return False
    return public == expected
