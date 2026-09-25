"""Current-policy online window binding and optional composition diagnostics.

This module neither samples worlds nor gates base RL on method diversity. It
keeps distinct situation blocks, actual actor identity and unstarted slots apart.
"""

import copy
import re

from .member_views import member_view
from .storage import digest, json_bytes
from .support_weights import build_support, materialize_weights

VERSION = "online-window-support-v0.13"
ACTOR_VERSION = "shared-actor-identity-v0.13"
ACTOR_FIELDS = {
    "version",
    "policy_version",
    "adapter_sha256",
    "base_manifest_sha256",
    "inference_profile_sha256",
}


def _actor(identity):
    if (
        not isinstance(identity, dict)
        or set(identity) != ACTOR_FIELDS
        or identity.get("version") != ACTOR_VERSION
    ):
        raise ValueError("The online window requires a complete shared effective actor identity")
    if not isinstance(identity["policy_version"], str) or not identity["policy_version"]:
        raise ValueError("The actual policy version must be explicit")
    if any(
        not isinstance(identity[key], str) or not re.fullmatch(r"[0-9a-f]{64}", identity[key])
        for key in ACTOR_FIELDS - {"version", "policy_version"}
    ):
        raise ValueError(
            "Base, adapter and inference profile identities require exact SHA256 values"
        )
    return copy.deepcopy(identity)


def _policies(policies, active, identity):
    if not isinstance(policies, dict) or not set(active) <= set(policies):
        raise ValueError("Predeclare the actual policy map for every active target member")
    for member in active:
        policy = policies[member]
        config = policy.get("config", {})
        if (
            policy.get("implementation") != "proworksim.model_policy.ModelPolicy"
            or config.get("weight_identity") != identity
            or config.get("model_revision") != identity["policy_version"]
        ):
            raise ValueError(
                "Active members must share the same actual current actor, including its adapter"
            )
    return copy.deepcopy(policies)


def declare_window(window_id, *, actor_identity, gamma_identity, slot_specs, min_class_count=2):
    """Freeze the window before interaction; policies may differ by role/task.

    Each slot declares slot_id, xi_id, xi_fingerprint, active_members, policies,
    and mapping_spec_id. Shared weights are checked separately from the actual
    per-situation policy-map hash used by existing TeamRollout.
    """
    identity = _actor(actor_identity)
    if (
        not isinstance(window_id, str)
        or not window_id
        or not isinstance(gamma_identity, dict)
        or not gamma_identity
    ):
        raise ValueError("An online window and its fixed execution protocol must be declared")
    if type(min_class_count) is not int or min_class_count < 1:
        raise ValueError("Declare a positive support threshold before collection")
    if not isinstance(slot_specs, list) or not slot_specs:
        raise ValueError("A nonempty planned joint-slot inventory is required")
    slots, seen, groups = [], set(), {}
    gamma = digest(json_bytes(gamma_identity))
    for original in slot_specs:
        row = copy.deepcopy(original)
        if set(row) != {
            "slot_id",
            "xi_id",
            "xi_fingerprint",
            "active_members",
            "policies",
            "mapping_spec_id",
        }:
            raise ValueError(
                "Each slot must predeclare exact situation, active members, policies and mapper"
            )
        for key in ("slot_id", "xi_id", "xi_fingerprint", "mapping_spec_id"):
            if not isinstance(row[key], str) or not row[key]:
                raise ValueError("Slot and situation identities must be nonempty")
        active = row["active_members"]
        if (
            not isinstance(active, list)
            or not active
            or len(active) != len(set(active))
            or any(not isinstance(m, str) or not m for m in active)
        ):
            raise ValueError(
                "Actual target members must be distinct; do not invent inactive actor blocks"
            )
        if row["slot_id"] in seen:
            raise ValueError("One declared joint slot cannot be duplicated")
        seen.add(row["slot_id"])
        row["policies"] = _policies(row["policies"], active, identity)
        row["window"] = {
            "window_id": window_id,
            "xi_id": row["xi_id"],
            "xi_fingerprint": row["xi_fingerprint"],
            "gamma_fingerprint": gamma,
            "team_policy_fingerprint": digest(json_bytes(row["policies"])),
        }
        binding = (
            row["xi_fingerprint"],
            tuple(active),
            row["window"]["team_policy_fingerprint"],
            row["mapping_spec_id"],
        )
        if row["xi_id"] in groups and groups[row["xi_id"]] != binding:
            raise ValueError(
                "One exact situation cannot silently vary layout, roles, policy prompts or mapper"
            )
        groups[row["xi_id"]] = binding
        slots.append(row)
    return {
        "version": VERSION,
        "window_id": window_id,
        "actor_identity": identity,
        "actor_identity_sha256": digest(json_bytes(identity)),
        "gamma_identity": copy.deepcopy(gamma_identity),
        "gamma_fingerprint": gamma,
        "min_class_count": min_class_count,
        "slots": slots,
    }


def _declaration(value):
    rebuilt = declare_window(
        value["window_id"],
        actor_identity=value["actor_identity"],
        gamma_identity=value["gamma_identity"],
        slot_specs=[
            {k: copy.deepcopy(v) for k, v in row.items() if k != "window"} for row in value["slots"]
        ],
        min_class_count=value["min_class_count"],
    )
    if rebuilt != value:
        raise ValueError("Frozen online declaration differs from its binding values")
    return value


def expected_window(declaration, slot_id):
    declaration = _declaration(declaration)
    rows = [row for row in declaration["slots"] if row["slot_id"] == slot_id]
    if len(rows) != 1:
        raise ValueError("Unknown planned online slot")
    return copy.deepcopy(rows[0]["window"])


def bind_rollout(declaration, slot_id, rollout, *, mapping=None):
    """Bind already collected evidence; never rewrite an event or actor input."""
    expected = expected_window(declaration, slot_id)
    row = next(row for row in declaration["slots"] if row["slot_id"] == slot_id)
    if (
        rollout.get("window") != expected
        or rollout.get("manifest", {}).get("policies") != row["policies"]
    ):
        raise ValueError("Rollout situation, execution window or policy bindings changed")
    actual_targets = {
        member
        for member, binding in rollout["members"].items()
        if binding.get("origin") == "target_model"
    }
    if actual_targets != set(row["active_members"]):
        raise ValueError("Only the declared active target members belong to this online slot")
    identity = declaration["actor_identity"]
    views = {member: member_view(rollout, member) for member in row["active_members"]}
    # Inspect all retained actual responses, including orphan records that a
    # MemberView cannot admit. Missing behavior records remain a separate mask.
    for event in rollout["events"]:
        if event.get("worker_id") not in actual_targets:
            continue
        payload = event["payload"]
        response = (
            payload.get("response")
            if event["kind"] == "model_response"
            else payload.get("response", {}).get("body")
            if event["kind"] == "model_attempt"
            and payload.get("stage") == "finished"
            and payload.get("status") == "success"
            else None
        )
        if response is None:
            continue
        if (
            response.get("actor_identity") != identity
            or response.get("system_fingerprint") != identity["policy_version"]
            or response.get("online_window_id") != declaration["window_id"]
        ):
            raise ValueError("Actual generation came from another policy/adapter/profile/window")
    if mapping is None:
        mapping = {
            "rollout_id": rollout["rollout_id"],
            "spec_id": row["mapping_spec_id"],
            "status": "unmapped",
            "class_id": None,
            "reason": "No method claimed; base online RL is independent of composition support",
        }
    if (
        mapping.get("rollout_id") != rollout["rollout_id"]
        or mapping.get("spec_id") != row["mapping_spec_id"]
    ):
        raise ValueError(
            "Method mapping is not bound to this actual rollout and predeclared mapper"
        )
    return {
        "slot_id": slot_id,
        "window": expected,
        "rollout": rollout,
        "mapping": copy.deepcopy(mapping),
        "member_views": views,
    }


def diagnose_window(declaration, records):
    """Report each exact situation without pooling old policies or filling quotas.

    records contain slot_id, status (closed/closed_unassessed/interrupted/not_started),
    and for closed records rollout plus optional mapping. A closed_unassessed
    record supplies its actual episode path and manifest SHA256. Missing declared records are
    explicitly not_started. Incomplete blocks have no empirical b/v estimate.
    """
    declaration = _declaration(declaration)
    planned = {row["slot_id"]: row for row in declaration["slots"]}
    by_id = {}
    for record in records:
        sid = record["slot_id"]
        if (
            sid not in planned
            or sid in by_id
            or record.get("status")
            not in {"closed", "closed_unassessed", "interrupted", "not_started"}
        ):
            raise ValueError("Runtime status must retain each original planned slot once")
        if record["status"] != "closed" and record.get("rollout") is not None:
            raise ValueError("An open/unstarted slot cannot claim a closed TeamRollout")
        by_id[sid] = record
    groups = {}
    seen_rollouts = set()
    for sid, row in planned.items():
        record = by_id.get(sid, {"slot_id": sid, "status": "not_started"})
        group = groups.setdefault(
            row["xi_id"],
            {
                "window": row["window"],
                "active_members": row["active_members"],
                "slots": [],
                "planned": 0,
                "closed": 0,
                "closed_unassessed": 0,
                "unassessed_boundaries": [],
                "interrupted": 0,
                "not_started": 0,
            },
        )
        group["planned"] += 1
        group[record["status"]] += 1
        if record["status"] == "closed_unassessed":
            from pathlib import Path
            from .storage import read_json

            root = Path(record["episode"])
            path = root if root.name == "manifest.json" else root / "manifest.json"
            manifest = read_json(path)
            if (
                manifest.get("status") != "closed"
                or digest(path.read_bytes()) != record.get("manifest_sha256")
                or manifest.get("policies") != row["policies"]
            ):
                raise ValueError(
                    "Closed-unassessed evidence must bind the actual declared closed episode"
                )
            rid = manifest["episode_id"]
            if rid in seen_rollouts:
                raise ValueError("A closed episode cannot fill two online slots")
            seen_rollouts.add(rid)
            group["slots"].append({"slot_id": sid, "window": row["window"], "rollout": None})
            group["unassessed_boundaries"].append(
                {
                    "slot_id": sid,
                    "episode": str(path.parent),
                    "episode_id": rid,
                    "manifest_sha256": record["manifest_sha256"],
                }
            )
        if record["status"] == "closed":
            bound = bind_rollout(declaration, sid, record["rollout"], mapping=record.get("mapping"))
            rid = bound["rollout"]["rollout_id"]
            if rid in seen_rollouts:
                raise ValueError("A joint rollout cannot be reused as a fresh online interaction")
            seen_rollouts.add(rid)
            group["slots"].append(bound)
    result = []
    for group in groups.values():
        slots = group.pop("slots")
        complete = group["closed"] + group["closed_unassessed"] == group["planned"]
        support = weights = None
        baseline = None
        if complete:
            observed = build_support(
                slots,
                window=group["window"],
                member_ids=group["active_members"],
                min_class_count=declaration["min_class_count"],
            )
            baseline = {
                member: {
                    "actor_mask": block["base_actor_mask"],
                    "weights": {sid: 1.0 for sid in observed["slot_ids"]},
                }
                for member, block in observed["blocks"].items()
            }
            if not group["closed_unassessed"]:
                support = observed
                weights = materialize_weights(
                    support, {member: block["b"] for member, block in support["blocks"].items()}
                )
        result.append(
            {
                **group,
                "complete": complete,
                "support": support,
                "Q_equals_B": weights,
                "closed_joint_M": group["closed"] + group["closed_unassessed"],
                "baseline_only_materialization": baseline,
                "base_RL_requires_method_support": False,
                "empirical_distribution_status": "incomplete_no_b_or_v_estimate"
                if not complete
                else "closed_unassessed_no_b_or_v_estimate"
                if group["closed_unassessed"]
                else "closed_current_policy_block",
            }
        )
    return {
        "version": VERSION,
        "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "gamma_fingerprint": declaration["gamma_fingerprint"],
        "complete": all(group["complete"] for group in result),
        "groups": result,
        "scope": "Online diagnostic only. Base actor masks preserve trustworthy failures independently of V/method diversity. Unstarted slots are not observed failures. No previous actor window is pooled into current support; optimizer/reward/probability/zero-advantage gates belong to the trainer.",
    }


def assess_online_validity(
    episode, spec, *, independent_capture, members, reward_result=None, window=None
):
    """Compose record/permission with independently evaluated scoped work facts.

    The scalar reward and its completion flag are never used as V. A short
    fragment is judged against its own predeclared basis/delivery obligations.
    """
    from pathlib import Path

    from .online_rewards import assess_online_reward
    from .storage import read_json
    from .team_rollout import validate_window, work_validity
    from .team_validity import assess_record_permission

    root = Path(episode)
    if root.name == "manifest.json":
        root = root.parent
    manifest = read_json(root / "manifest.json")
    frozen = manifest.get("scenario", {}).get("variation", {}).get("online_reward")
    if frozen != spec:
        raise ValueError("Online validity scope must be fixed before current actor actions")
    reward = reward_result if reward_result is not None else assess_online_reward(root, spec)
    manifest_sha = digest((root / "manifest.json").read_bytes())
    if (
        reward.get("episode_id") != manifest["episode_id"]
        or reward.get("manifest_sha256") != manifest_sha
    ):
        raise ValueError("Scoped work facts do not bind this exact episode")
    if window is not None:
        window = validate_window(window)
        if window["team_policy_fingerprint"] != digest(json_bytes(manifest["policies"])):
            raise ValueError("Record validation window differs from the actual episode policies")
    spec_id = "online-scoped-validity-v0.13.1:" + digest(json_bytes(spec))
    common = assess_record_permission(
        root,
        members=members,
        independent_capture=independent_capture,
        spec_id=spec_id,
        window=window,
    )
    checks = [
        row
        for dimension in ("record", "permission")
        for row in common["components"][dimension]["checks"]
    ]
    for dimension in ("basis", "delivery"):
        fact = reward.get("work_components", {}).get(dimension)
        value = fact.get("value") if isinstance(fact, dict) else None
        if type(value) not in (bool, type(None)):
            raise ValueError("Scoped validity facts must be true/false/unknown")
        if value is True and not fact.get("evidence"):
            raise ValueError("A true scoped work fact requires its actual evidence")
        checks.append(
            {
                "dimension": dimension,
                "value": value,
                "reason": fact.get("reason", "Actual scoped work predicate")
                if isinstance(fact, dict)
                else "Scoped work evidence is unavailable",
                "evidence": {
                    "manifest_sha256": manifest_sha,
                    "scope": spec["task"],
                    "spec_sha256": digest(json_bytes(spec)),
                    "work_fact": copy.deepcopy(fact),
                },
            }
        )
    return work_validity(checks, spec_id=spec_id)


def export_online_rollout(episode, *, window, members, independent_capture, reward_spec):
    """Closed-episode bridge that preserves new reward/V and original experiences."""
    from .online_rewards import assess_online_reward
    from .team_rollout import export_team_rollout

    reward = assess_online_reward(episode, reward_spec)
    validity = assess_online_validity(
        episode,
        reward_spec,
        independent_capture=independent_capture,
        members=members,
        reward_result=reward,
        window=window,
    )
    rollout = export_team_rollout(
        episode, window=window, members=members, validity=validity, reward=reward
    )
    rollout["online_scope"] = {
        "version": VERSION,
        "task": reward_spec["task"],
        "reward_spec": copy.deepcopy(reward_spec),
        "reward_spec_sha256": digest(json_bytes(reward_spec)),
        "validity_spec_id": validity["spec_id"],
        "scope": "Current actor work under this scope; preparation receives no actor credit. Reward eligibility, scoped V and method support are separate. Short success is not full-chain success.",
    }
    return rollout
