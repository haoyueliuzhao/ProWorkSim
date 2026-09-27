"""Non-executable study proposals and source-lineage checks for collaboration RL.

The V1 theory is unchanged. Counts are design arithmetic, not observed support,
source admission, resource authorization, or a launchable learning protocol.
"""

from collections import Counter

VERSION = "domain-collaboration-study-v0.20"
PURPOSES = ("interface_development", "policy_training", "contribution_development", "locked_evaluation")
LINEAGE_KEYS = ("origin_database", "database_sha256", "target_table_family", "template_family", "ancestor_task")


def source_partition_audit(records):
    """Transitive shared ancestors cannot silently cross research purposes.

    Missing lineage remains unresolved. A public benchmark split is not an
    independent-source certificate. Caller must supply concrete asset evidence.
    """
    by_id = {}
    for row in records:
        key = row.get("asset_id")
        if not key or key in by_id or row.get("purpose") not in PURPOSES:
            raise ValueError("Unique asset IDs and one declared research purpose required")
        by_id[key] = row
    parent = {key: key for key in by_id}

    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    seen = {}
    unknown = []
    for key, row in by_id.items():
        if row.get("lineage_review") != "complete" or not row.get("evidence"):
            unknown.append(key)
        values = 0
        for field in LINEAGE_KEYS:
            items = row.get(field, [])
            if not isinstance(items, list) or any(not isinstance(v, str) or not v for v in items):
                raise ValueError("Lineage keys must be explicit nonempty string lists")
            for value in items:
                values += 1
                token = (field, value)
                if token in seen:
                    parent[root(key)] = root(seen[token])
                seen[token] = key
        if values == 0 and key not in unknown:
            unknown.append(key)
    groups = {}
    for key in by_id:
        groups.setdefault(root(key), []).append(key)
    components, conflicts = [], []
    for ids in groups.values():
        purposes = sorted({by_id[key]["purpose"] for key in ids})
        entry = {"asset_ids": sorted(ids), "purposes": purposes,
                 "conflict": len(purposes) > 1,
                 "lineage_complete": not set(ids) & set(unknown)}
        components.append(entry)
        if entry["conflict"]:
            conflicts.append(entry)
    return {"version": VERSION, "admitted": not conflicts and not unknown,
            "components": components, "cross_purpose_conflicts": conflicts,
            "unresolved_assets": sorted(unknown),
            "scope": "Only supplied provenance and declared grouping; no semantic decontamination guarantee. Unresolved assets cannot enter locked evaluation."}


def build_design():
    windows = []
    for index in range(4):
        slots = []
        for family, count in (("joint_handoff_and_use", 8), ("joint_review_feedback_repair", 8),
                              ("individual_implementation", 4), ("individual_review", 4)):
            for repeat in range(count):
                slots.append({"slot_id": f"p2-w{index}-{family}-{repeat}", "task_family": family,
                              "exact_situation_group": f"unbound-w{index}-{family}" if count == 8 else f"unbound-w{index}-{family}-{repeat}",
                              "repeat": repeat, "situation_asset": None, "purpose": "policy_training"})
        windows.append({"window_id": f"p2-proposed-{index}", "slots": slots,
                        "current_policy_only": True, "min_class_count": 2,
                        "theoretical_max_qualifying_classes_per_joint_block": 4,
                        "observed_valid_classes": None, "same_initial_state_hash_required": True})
    evaluation = []
    for family in ("information_handoff_and_use", "review_and_repair", "project_maintenance"):
        for case in range(4):
            for repeat in range(2):
                evaluation.append({"situation": f"unbound-{family}-{case}", "repeat": repeat,
                                   "family": family, "purpose": "locked_evaluation", "asset": None})
    return {"version": VERSION, "launchable": False, "resource_approved": False,
            "domain": "structured-data-analysis-and-data-engineering-collaboration",
            "final_policy": "One shared actor and LoRA for all roles, one actor optimizer, independent auxiliary critic.",
            "execution": {"resident_instances": 1, "sampling_replicas": 0,
                          "role_sessions_and_permissions": "separate", "prefix_cache_required": False},
            "research_purposes": list(PURPOSES),
            "P1": {"separate_bounded_authorization": True, "automatically_qualifies_P2": False},
            "P2": {"method": "Q=B", "time_credit": "terminal_MC", "windows": windows,
                   "evaluation_per_endpoint": evaluation,
                   "counts": {"train": 96, "initial_evaluation": 24, "final_evaluation": 24, "total": 144,
                              "maximum_formal_updates": 4},
                   "evaluation_binding": "Same admitted cases/seeds/contracts before and after, no training on locked worlds.",
                   "project_maintenance": "Requires frozen-checkpoint evaluation adapter; existing four-project utility is not a training projection.",
                   "source_rotation": "Predeclare actual databases/facts across windows; unbound placeholders here are not admitted worlds.",
                   "support": "Current theta/Gamma/exact xi only; keep failure residuals on base handling, no resampling to fill classes.",
                   "interpretation": "Four updates are a pilot dose; neither guaranteed improvement nor sufficient general null evidence."},
            "P3": {"predeclared_window_positions": [1, 3], "max_distinct_member_directions_per_position": 2,
                   "branches": ["F0", "FA", "FB", "FAB"], "development_episodes_per_branch": 8,
                   "maximum_trial_branches": 8, "maximum_development_episodes": 64,
                   "conditional_on_actual_support": True, "automatic_launch": False,
                   "common_start": ["actor", "critic", "actor_optimizer", "critic_optimizer", "RNG"],
                   "joint_interaction": "FAB - FA - FB + F0",
                   "formal_update": "Return to common start; do not accumulate exploratory branch parameters."},
            "P4": {"methods": ["base_Q_equals_B", "generic_member_raw_trajectory_meta_reweighting", "ID_VTDO_first_order_structured_member_configuration"],
                   "exploratory_train_episodes_one_seed": 288, "three_seeds": 864,
                   "outer_work_and_evaluation_included": False, "automatic_launch": False,
                   "fairness": ["same_material_same_initial_learning_state", "same_total_resource_including_probes_and_outer_work"],
                   "baseline_budget": "Predeclare useful extra interaction/update allocation, never idle padding."},
            "external_evaluation": {"candidate_benchmarks": ["TeamBench_data", "CoGym_tabular", "MiniInteract_a", "BIRD_Critic_SQLite"],
                                    "maximum_tasks_each": 12, "policy_endpoints": 2,
                                    "upper_bound_runs_one_method": 96, "admitted_tasks": None,
                                    "role": "First three collaboration; Critic individual SQL ability/retention only.",
                                    "automatic_launch": False},
            "unresolved_before_P2": ["approve_whole_run_resource_budget", "admit_concrete_source_lineage_partition",
                                      "bind_real_joint_review_feedback_repair_assets", "bind_12_distinct_evaluation_situations",
                                      "frozen_checkpoint_project_maintenance_evaluation"],
            "supersedes": "Unstarted 118-episode restoration plan only; original H1, V1 theory, and historical scores remain unchanged."}


def validate_design(design):
    if design != build_design():
        raise ValueError("Study draft differs from the frozen design arithmetic")
    windows = design["P2"]["windows"]
    for window in windows:
        counts = Counter(row["task_family"] for row in window["slots"])
        if sorted(counts.values()) != [4, 4, 8, 8]:
            raise ValueError("Required joint density and individual controls missing")
    return {"status": "planning_arithmetic_checked_not_executed", "train": sum(len(w["slots"]) for w in windows),
            "evaluation_each_endpoint": len(design["P2"]["evaluation_per_endpoint"]),
            "observed_support": None, "source_admission": False, "launchable": False}
