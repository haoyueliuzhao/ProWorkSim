"""Seal a reviewable, still-pending v061 recovery proposal without runtime IO."""

from __future__ import annotations

import json

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def prepare():
    plan = policy.create_plan()
    sources = policy.sources()
    root = policy.ROOT / "artifacts/software-benchmark-v061/model-compiler-r4/authorization"
    root.mkdir(parents=True, exist_ok=True)
    snapshot = reference(
        policy.ROOT
        / "runs/software-benchmark-v061/original-terminal-recovery-r1-20261025/recovery-result.json"
    )
    proposal = {
        "version": policy.VERSION,
        "status": "prepared_pending_specific_permission",
        "user_goal": "修复本项目私有Python编译头文件，同两个已停止用户服务显式再次部署；不新增unit身份，不重跑任何已进入模型回合",
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
        "new_continuation_resource_start_count": 0,
        "previous_execution_preserved": {"containers": 19, "named_volumes": 2,
            "completed_controls": 14, "completed_snapshot_scores": 1, "formal_generation": 0},
        "source_plan": reference(policy.PREVIOUS_PLAN_FILE),
        "plan_equivalence": policy.validate_plan_equivalence(reference(policy.PREVIOUS_PLAN_FILE), reference(policy.PLAN_FILE)),
        "completed_controls_replayed": 0,
        "completed_snapshot_scores_replayed": 0,
        "deployment_recovery": {"previous_model_deployments": 2, "both_closed_before_readiness": True,
            "previous_neutral_calls": 0, "previous_formal_generation": 0,
            "new_unique_user_units": 0, "gpu_memory_utilization": 0.6,
            "weights_context_sampling_and_budget_unchanged": True},
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
        "explicit_model_memory_authorization": None,
        "automatic_release": False,
        "constraints": policy.CONSTRAINTS,
        "plan": reference(policy.PLAN_FILE),
        "proposal": proposal_ref,
        "sources": sources,
    }
    pending_path = root / "pending-authorization.json"
    if pending_path.exists():
        if json.loads(pending_path.read_bytes()) != authorization:
            raise ValueError(
                "Existing pending continuation authorization differs"
            )
    else:
        write_new(pending_path, authorization)
    return {
        "authorization": reference(pending_path),
        "proposal": proposal_ref,
        "status": "pending",
        "container_upper_bound": policy.CONSTRAINTS["maximum_containers"],
        "volume_upper_bound": policy.CONSTRAINTS["maximum_named_volumes"],
    }


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
