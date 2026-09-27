"""Freeze one selected combination's migration and four-window online pilot."""

import argparse
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from proworksim.templates.retail_work import case_spec
from scripts.build_harness_study_v016 import ref

TASKS = ("implement", "review", "pair", "chain")
VERSION = "harness-direct-learning-v0.17"


def slot(case_id, slot_id, seed, repeat):
    case = case_spec(case_id)
    return {
        "slot_id": slot_id,
        "case_id": case_id,
        "task": case["task"],
        "fact_position": case["fact_position"],
        "pool": case["pool"],
        "family": case["family"],
        "repeat": repeat,
        "sampling_seed": seed,
        "role_decision_limits": copy.deepcopy(case["role_decision_limits"]),
    }


def window(label, mode, phase, harness, rows):
    return {
        "window_id": label,
        "mode": mode,
        "stage": "H2_" + phase,
        "phase": phase,
        "harness": harness,
        "template": "retail_work",
        "interface": "v14",
        "presentation": "compact_v14",
        "external_tick_per_sweep": 1,
        "min_class_count": 2,
        "slots": rows,
    }


def build_protocols(h1, harness, selection_ref):
    if harness not in ("native_v15", "openhands_v16") or h1["stage"] != "H1_development":
        raise ValueError("An actually selected H1 model/harness is required")
    recipe = copy.deepcopy(h1["recipe"])
    recipe.update(
        credit_assignment="terminal_mc", diagnostic_max_groups=0, post_update_max_decisions=0
    )
    common = {
        "version": VERSION,
        "stage": "H2",
        "candidate_id": h1["candidate_id"],
        "harness": harness,
        "mode": "online",
        "collector": "proworksim.harness_collection:collect_window",
        "runtime": copy.deepcopy(h1["runtime"]),
        "recipe": recipe,
        "selection": selection_ref,
        "harness_identity": copy.deepcopy(h1["harness_identity"]),
        "initialization": {
            "kind": "fresh_public_base",
            "seed": recipe["seed"],
            "restore_checkpoint_permitted": False,
        },
        "training_rule": "Current model works in actual worlds, original own-token probability checks, shared actor/critic update, fresh work at new identity. No H0/H1 demonstration reuse.",
        "method_rule": "Q=B basic RL only. Current-window method support remains descriptive; no cross-harness or cross-model pooling.",
        "numeric_gate": "Existing max logprob tolerance .02 / mean .002 and unchanged FP32/highest; no outcome-driven tolerance expansion.",
        "scope": "Single selected combination, terminal MC, one training seed. No MC/RTG ranking or ID-VTDO incremental claim.",
    }
    migration = copy.deepcopy(common)
    migration.update(
        experiment_id="h2-migration-v017",
        purpose="bounded_actual_update_admission_not_first_online_loop_claim",
    )
    train = [
        slot(f"uci-train-f0-{task}", f"migration-train-{i}", 202609272000 + i, 0)
        for i, task in enumerate(TASKS)
    ]
    probe = [
        slot(f"uci-development-f1-{task}", f"migration-next-{i}", 202609272100 + i, 0)
        for i, task in enumerate(TASKS)
    ]
    migration["windows"] = [
        window("h2-migration-current", "online", "migration", harness, train),
        window("h2-migration-next", "evaluate", "migration_probe", harness, probe),
    ]
    migration["budget_scope"] = (
        "4 fresh training episodes, at most one shared update, then 4 new development episodes. No result-based retries."
    )
    main = copy.deepcopy(common)
    main.update(
        experiment_id="h2-pilot-v017",
        launch_gate={"version": "h2-admission-v0.17", "state": "awaiting_actual_migration"},
    )
    main["windows"] = []
    for phase in ("initial", "final"):
        rows = [
            slot(
                f"uci-locked-f{fact}-{task}",
                f"h2-{phase}-f{fact}-{task}-r{repeat}",
                202609273000 + fact * 100 + i * 10 + repeat,
                repeat,
            )
            for fact in range(3)
            for i, task in enumerate(TASKS)
            for repeat in range(2)
        ]
        target = window("h2-locked-" + phase, "evaluate", phase, harness, rows)
        if phase == "initial":
            main["windows"].append(target)
        else:
            final = target
    for index in range(4):
        rows = [
            slot(
                f"uci-train-f{fact}-{task}",
                f"h2-train-w{index}-{task}-r{repeat}",
                202609274000 + index * 100 + i * 10 + repeat,
                repeat,
            )
            for i, task in enumerate(TASKS)
            for repeat, fact in enumerate((0, 1, 2, 0))
        ]
        main["windows"].append(window(f"h2-train-{index}", "online", "train", harness, rows))
    main["windows"].append(final)
    main["budget_scope"] = (
        "4 x 16 = 64 online training episodes, at most four updates; 24 initial + 24 final independent within-source locked evaluations. Fresh restart after migration; no best-checkpoint choice or success-driven extension."
    )
    main["task_marginal"] = {task: 0.25 for task in TASKS}
    main["training_fact_marginal"] = {"f0": 0.5, "f1": 0.25, "f2": 0.25}
    main["split_scope"] = (
        "H1 new development entities disjoint from original train/locked; migration uses train plus original development only. Locked results never drive this run updates or checkpoint selection."
    )
    return migration, main


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("New output required")
    selected = json.loads(a.selection.read_text())
    choice = selected.get("selected")
    if selected.get("status") != "selected" or not isinstance(choice, dict):
        raise ValueError("Complete H1 selection required; no speculative model choice")
    h1 = json.loads(a.protocol.read_text())
    if choice["candidate_id"] != h1["candidate_id"] or choice.get("protocol_ref", {}).get(
        "sha256"
    ) != digest(a.protocol.read_bytes()):
        raise ValueError("Selected protocol differs from actual H1 identity")
    migration, pilot = build_protocols(h1, choice["harness"], ref(a.selection))
    a.output.mkdir(parents=True)
    for name, data in [("migration", migration), ("pilot-planned", pilot)]:
        (a.output / f"{name}.json").write_bytes(json_bytes(data))
    print(
        json.dumps(
            {"status": "generated_not_started", "migration_episodes": 8, "pilot_episodes": 112}
        )
    )


if __name__ == "__main__":
    main()
