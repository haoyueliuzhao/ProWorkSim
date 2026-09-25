"""Immutable joint-rollout records over existing readable episode boundaries.

The three gates are deliberately separate: a trusted reward, valid work, and a
member's supported reconfiguration eligibility answer different questions.
"""

import copy
from pathlib import Path

from .episode import assess_historical_episode
from .storage import digest, json_bytes, read_json

TEAM_ROLLOUT_VERSION = "team-rollout-v0.12"
WINDOW_FIELDS = (
    "window_id",
    "xi_id",
    "xi_fingerprint",
    "gamma_fingerprint",
    "team_policy_fingerprint",
)
ORIGINS = {"target_model", "rule", "teacher", "historical_model", "offline_fixture"}
DIMENSIONS = ("record", "permission", "basis", "delivery")


def validate_window(window):
    if not isinstance(window, dict) or set(window) != set(WINDOW_FIELDS):
        raise ValueError("Window must declare exact situation, protocol and team-policy identities")
    if any(not isinstance(window[key], str) or not window[key] for key in WINDOW_FIELDS):
        raise ValueError("Window identities must be nonempty strings")
    return copy.deepcopy(window)


def work_validity(checks, *, spec_id):
    """Combine evidenced, three-valued validity components without reward input.

    Domain/permission validators supply these checks. Unchecked dimensions remain
    unknown; a high reward or mapped class never fills missing validity evidence.
    """
    if not isinstance(spec_id, str) or not spec_id:
        raise ValueError("Validity needs a predeclared specification identity")
    result = {}
    for dimension in DIMENSIONS:
        rows = [copy.deepcopy(row) for row in checks if row.get("dimension") == dimension]
        for row in rows:
            if type(row.get("value")) not in (bool, type(None)) or not row.get("evidence"):
                raise ValueError(
                    "Validity checks require true/false/unknown and evidence references"
                )
        value = (
            False
            if any(row["value"] is False for row in rows)
            else True
            if rows and all(row["value"] is True for row in rows)
            else None
        )
        result[dimension] = {"value": value, "checks": rows}
    value = (
        False
        if any(row["value"] is False for row in result.values())
        else True
        if all(row["value"] is True for row in result.values())
        else None
    )
    return {
        "version": "work-validity-v0.12",
        "spec_id": spec_id,
        "value": value,
        "components": result,
    }


def export_team_rollout(episode, *, window, members, validity, reward, assessment_spec=None):
    """Read a closed episode; attach frozen contracts without changing the world.

    `xi_fingerprint` must come from the predeclared situation registry, including
    its initial information/permissions. Random episode UUIDs are not situations.
    The exporter does not infer semantic situation equivalence from names.
    """
    root = Path(episode).resolve()
    if root.name == "manifest.json":
        root = root.parent
    manifest = read_json(root / "manifest.json")
    assessment = assess_historical_episode(root, **(assessment_spec or {}))
    if assessment.get("assessment_execution", {}).get("status") != "complete":
        raise ValueError(
            "Unusable episode evidence; retain this failed collection slot in the window inventory"
        )
    if not isinstance(members, dict) or not members:
        raise ValueError("Team rollout needs explicit member bindings and origins")
    for label, member in members.items():
        if member.get("origin") not in ORIGINS or label not in manifest["policies"]:
            raise ValueError("Member origin and actual episode policy binding are required")
        if not isinstance(member.get("actor_id"), str):
            raise ValueError("Member must identify its actual actor")
    if validity.get("version") != "work-validity-v0.12":
        raise ValueError("Reward eligibility cannot substitute for validity")
    # Recheck the claimed conjunction, not just its top-level flag.
    flattened = [row for dim in DIMENSIONS for row in validity["components"][dim]["checks"]]
    if work_validity(flattened, spec_id=validity["spec_id"]) != validity:
        raise ValueError("Validity summary differs from its evidenced components")
    window = validate_window(window)
    if window["team_policy_fingerprint"] != digest(json_bytes(manifest["policies"])):
        raise ValueError("Declared team policy differs from the actual episode policy identities")
    manifest_sha = digest((root / "manifest.json").read_bytes())
    if (
        reward.get("episode_id") != manifest["episode_id"]
        or reward.get("manifest_sha256") != manifest_sha
    ):
        raise ValueError("Reward must bind this exact historical episode")
    history = read_json(root / manifest["experience"]["path"])
    start, end = manifest["experience"]["start"], manifest["experience"]["end"]
    return {
        "version": TEAM_ROLLOUT_VERSION,
        "rollout_id": manifest["episode_id"],
        "window": validate_window(window),
        "members": copy.deepcopy(members),
        "manifest": copy.deepcopy(manifest),
        "manifest_sha256": manifest_sha,
        "episode_path": str(root),
        "events": copy.deepcopy(history["events"][start:end]),
        "event_interval": {"start": start, "end": end},
        "reward_eligibility": copy.deepcopy(reward),
        "work_validity": copy.deepcopy(validity),
        "assessment": assessment,
        "origin_note": "Rules/teacher views may be inspected but cannot count as current target-model support",
    }
