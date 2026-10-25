"""Seal a reviewable, still-pending v061 recovery proposal without runtime IO."""

from __future__ import annotations

import json

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def prepare():
    plan = policy.create_plan()
    sources = policy.sources()
    root = policy.ROOT / "artifacts/software-benchmark-v061/recovery-authorization-r1"
    root.mkdir(parents=True, exist_ok=True)
    snapshot = reference(
        policy.ROOT
        / "runs/software-benchmark-v061/original-terminal-recovery-r1-20261025/recovery-result.json"
    )
    proposal = {
        "version": policy.VERSION,
        "status": "prepared_pending_specific_permission",
        "user_goal": "全部修复后进行重新评分",
        "plan": reference(policy.PLAN_FILE),
        "original_terminal_recovery": snapshot,
        "constraints": policy.CONSTRAINTS,
        "operations": sorted(policy.OPERATIONS),
        "sources": sources,
        "cohort_definition": {
            "fresh_generation": [
                r["recovery_slot_id"]
                for r in plan["rows"]
                if r["measurement_kind"] == "fresh_generation_recovery"
            ],
            "same_original_candidate": [
                r["slot_id"]
                for r in plan["rows"]
                if r["measurement_kind"] == "original_terminal_snapshot_recovery"
            ],
            "old_thirteen_unknowns_overwritten": False,
            "select_best_of_multiple_attempts": False,
        },
        "specific_permission_needed": "Existing root-equivalent Docker API: fixed private actors/controllers/graders and newly owned local volumes; two project-owned ordinary-user model units and one bounded coordinator unit. No host bind mounts, privileged containers, shared-service changes, host namespace/mount operations or public network.",
        "diagnostic_revisions": "At most three separately numbered zero-model preparation pairs; failures retained; no automatic diagnostic replay; all formal generation uses the final validated source revision.",
        "resource_start_count_at_preparation": 0,
    }
    proposal_path = root / "proposal.json"
    if proposal_path.exists():
        if json.loads(proposal_path.read_bytes()) != proposal:
            raise ValueError(
                "Prepared proposal changed; retain the earlier pending revision before resealing"
            )
        proposal_ref = reference(proposal_path)
    else:
        proposal_ref = write_new(proposal_path, proposal)
    authorization = {
        "version": policy.VERSION,
        "status": "pending",
        "explicit_rootful_authorization": None,
        "automatic_release": False,
        "constraints": policy.CONSTRAINTS,
        "plan": reference(policy.PLAN_FILE),
        "proposal": proposal_ref,
        "sources": sources,
    }
    if policy.AUTHORIZATION_FILE.exists():
        if json.loads(policy.AUTHORIZATION_FILE.read_bytes()) != authorization:
            raise ValueError(
                "Existing authorization differs; never reopen or replace an approved grant"
            )
    else:
        write_new(policy.AUTHORIZATION_FILE, authorization)
    return {
        "authorization": reference(policy.AUTHORIZATION_FILE),
        "proposal": proposal_ref,
        "status": "pending",
        "container_upper_bound": policy.CONSTRAINTS["maximum_containers"],
        "volume_upper_bound": policy.CONSTRAINTS["maximum_named_volumes"],
    }


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
