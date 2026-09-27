"""New-stage fixed Q=B pilot with crossed review conditions and macro utility."""

import argparse
from collections import Counter
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from proworksim.templates.retail_balanced import QUALITIES, resolve
from scripts.build_harness_learning_v017 import TASKS, build_protocols as previous_protocols
from scripts.build_harness_study_v016 import ref

VERSION = "harness-direct-learning-v0.18"
# All nine policy/source x quality cells occur. These are predetermined finite
# draws, independent of results; uniform task weights do not optimize xi shares.
REVIEW_TRAIN = (
    ((0, "correct"), (1, "wrong_count"), (2, "wrong_amount"), (0, "wrong_count")),
    ((0, "wrong_count"), (1, "wrong_amount"), (2, "correct"), (1, "correct")),
    ((0, "wrong_amount"), (1, "correct"), (2, "wrong_count"), (2, "wrong_amount")),
    ((0, "correct"), (1, "wrong_amount"), (2, "wrong_count"), (0, "correct")),
)


def slot(pool, fact, task, quality, label, seed, repeat=0):
    case = resolve(pool, fact, task, quality)
    return {
        "slot_id": label,
        "case_id": case["case_id"],
        "task": task,
        "fact_position": fact,
        "pool": pool,
        "family": case["family"],
        "repeat": repeat,
        "sampling_seed": seed,
        "role_decision_limits": copy.deepcopy(case["role_decision_limits"]),
    }


def apply_stage(protocol):
    protocol["version"] = VERSION
    protocol["stage"] = "H2_v018"
    protocol["experiment_id"] = protocol["experiment_id"].replace("v017", "v018")
    protocol["environment_revision"] = {
        "executor": "narrow SQL parenthesized Boolean syntax repair",
        "review_catalog": "retail-balanced-review-v0.18",
        "selection_scope": "Old H1 gives one provisional initialization under its old executor; no four-combination ranking in the repaired environment is claimed.",
        "learning_comparison": "Both initial and final evaluation use this same new environment. Tool repair, H1 harness effect and parameter learning are not pooled.",
    }
    protocol["method_rule"] = (
        "Q=B only. With at most two draws per exact xi/window and min_class_count=2, at most one class can qualify; this pilot cannot auto-start O4."
    )
    protocol["method_support_density"] = {
        "min_class_count": 2,
        "maximum_repeats_per_exact_xi_per_window": 2,
        "maximum_qualifying_classes_per_block": 1,
        "composition_degrees_of_freedom": 0,
        "auto_O4": False,
    }
    protocol.pop("training_fact_marginal", None)
    for w in protocol["windows"]:
        w["window_id"] = "v018-" + w["window_id"]
        w["stage"] = "H2_v018_" + w["phase"]
        w["template"] = "retail_balanced"
    return protocol


def build_protocols(h1, harness, selection_ref):
    migration, pilot = map(apply_stage, previous_protocols(h1, harness, selection_ref))
    migration["windows"][0]["slots"] = [
        slot(
            "train",
            0,
            t,
            "wrong_count" if t == "review" else None,
            f"v018-migration-current-{i}",
            202609281000 + i,
        )
        for i, t in enumerate(TASKS)
    ]
    migration["windows"][1]["slots"] = [
        slot(
            "development",
            1,
            t,
            "correct" if t == "review" else None,
            f"v018-migration-new-policy-{i}",
            202609281100 + i,
        )
        for i, t in enumerate(TASKS)
    ]
    migration["confirmation_scope"] = (
        "The four pre-update real episodes also provide the predeclared repaired-environment confirmation of the old-H1 candidate; counted once. No full-business-success threshold or result-driven candidate replacement."
    )
    pilot["launch_gate"] = {"version": "h2-admission-v0.18", "state": "awaiting_actual_migration"}
    for w in pilot["windows"]:
        if w["phase"] in ("initial", "final"):
            rows = []
            for i, task in enumerate(TASKS):
                for fact in range(3):
                    controls = QUALITIES if task == "review" else (None, None)
                    for repeat, quality in enumerate(controls):
                        rows.append(
                            slot(
                                "locked",
                                fact,
                                task,
                                quality,
                                f"v018-{w['phase']}-{i}-{fact}-{repeat}",
                                202609282000 + i * 100 + fact * 10 + repeat,
                                repeat,
                            )
                        )
            w["slots"] = rows
        else:
            index = int(w["window_id"].rsplit("-", 1)[1])
            rows = []
            for i, task in enumerate(TASKS):
                pairs = (
                    REVIEW_TRAIN[index]
                    if task == "review"
                    else tuple((f, None) for f in (0, 1, 2, 0))
                )
                for repeat, (fact, quality) in enumerate(pairs):
                    rows.append(
                        slot(
                            "train",
                            fact,
                            task,
                            quality,
                            f"v018-train-{index}-{i}-{repeat}",
                            202609283000 + index * 100 + i * 10 + repeat,
                            repeat,
                        )
                    )
            w["slots"] = rows
    pilot["budget_scope"] = (
        "64 train + 27 initial + 27 final = 118 real episodes; at most four updates. This explicitly replaces the unstarted v0.17 112-episode plan. Migration 8 and projects 4 are separate."
    )
    pilot["primary_evaluation"] = {
        "measure": "task_macro_mean",
        "task_weights": {t: 0.25 for t in TASKS},
        "episodes_per_endpoint": {"implement": 6, "review": 9, "pair": 6, "chain": 6},
        "raw_episode_mean": "Secondary only; its task weights differ from the primary utility.",
    }
    pilot["review_design"] = {
        "factorial_per_pool": {
            "source_policy_slices": 3,
            "prepared_quality_types": list(QUALITIES),
        },
        "training_schedule": "Declared Latin coverage of all nine cells over four windows; finite cell counts need not be identical. Not outcome-dependent sampling or an optimized xi marginal.",
        "training_cell_counts": dict(Counter(f"f{f}:{q}" for row in REVIEW_TRAIN for f, q in row)),
        "evaluation_cells": "Each of nine policy/source x quality cells exactly once per endpoint.",
        "host_only_labels": True,
        "number_randomization_alone_is_not_the_fix": True,
    }
    return migration, pilot


def support_protocol(h1, harness, selection_ref):
    _, pilot = build_protocols(h1, harness, selection_ref)
    result = copy.deepcopy(pilot)
    result.update(
        stage="ID_support_v018",
        experiment_id="id-support-density-v018",
        mode="evaluate",
        launch_gate={
            "version": "id-support-density-v0.18",
            "state": "awaiting_completed_pilot_final_checkpoint",
        },
        initialization={
            "kind": "fixed_completed_pilot_final_checkpoint",
            "restore_checkpoint_permitted": True,
        },
        budget_scope="Two fixed joint development situations x eight current-policy repeats = 16; zero updates. No success/method quota resampling.",
        method_rule="Support measurement only; eight per xi permits but does not ensure two min-count-two valid classes. No Contribution or configuration intervention is executed.",
        method_support_density={
            "min_class_count": 2,
            "repeats_per_exact_xi": 8,
            "maximum_qualifying_classes_per_block": 4,
            "auto_O4": False,
        },
    )
    rows = []
    for i, (fact, task) in enumerate(((0, "pair"), (1, "chain"))):
        for repeat in range(8):
            rows.append(
                slot(
                    "development",
                    fact,
                    task,
                    None,
                    f"v018-density-{i}-{repeat}",
                    202609284000 + i * 100 + repeat,
                    repeat,
                )
            )
    result.pop("primary_evaluation", None)
    result["windows"] = [
        {
            "window_id": "v018-current-policy-density",
            "mode": "evaluate",
            "stage": "ID_support_v018",
            "phase": "support_density",
            "harness": harness,
            "template": "retail_balanced",
            "interface": "v14",
            "presentation": "compact_v14",
            "external_tick_per_sweep": 1,
            "min_class_count": 2,
            "slots": rows,
        }
    ]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--completed-pilot",
        type=Path,
        help="Optional later binding of the standalone support plan to its actual completed pilot root",
    )
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("New output required")
    selected = json.loads(a.selection.read_text())
    choice = selected.get("selected")
    if selected.get("status") != "selected" or not isinstance(choice, dict):
        raise ValueError("Final original H1 candidate selection required")
    h1 = json.loads(a.protocol.read_text())
    if choice["candidate_id"] != h1["candidate_id"] or choice["protocol_ref"]["sha256"] != digest(
        a.protocol.read_bytes()
    ):
        raise ValueError("Candidate does not match its actual old-H1 protocol")
    migration, pilot = build_protocols(h1, choice["harness"], ref(a.selection))
    density = support_protocol(h1, choice["harness"], ref(a.selection))
    if a.completed_pilot is not None:
        from proworksim.harness_learning_admission import validate_h2_launch

        pilot_root = a.completed_pilot.resolve()
        density["launch_gate"] = {
            "version": "id-support-density-v0.18",
            "state": "admitted",
            "pilot_report": ref(pilot_root / "online/report.json"),
        }
        owner = json.loads((pilot_root / "resident/owner.json").read_text())
        validate_h2_launch(
            density,
            model_path=owner["base_identity"]["path"],
            weight_manifest=owner["base_identity"]["manifest"]["path"],
            restore_checkpoint=pilot_root / "online/window-5/checkpoint",
        )
    a.output.mkdir(parents=True)
    for name, data in [
        ("migration", migration),
        ("pilot-planned", pilot),
        ("support-density-planned", density),
    ]:
        (a.output / f"{name}.json").write_bytes(json_bytes(data))
    print(
        json.dumps(
            {
                "status": "generated_not_started",
                "migration": 8,
                "pilot": 118,
                "later_support_density": 16,
                "auto_O4": False,
            }
        )
    )


if __name__ == "__main__":
    main()
