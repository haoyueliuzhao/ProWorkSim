"""Six new frozen-parameter work episodes, independent of training probability admission.

Reuses real workers, managed tools and immutable episode closure. No learner
forward, backward, parameter update, reference-policy action, or resampling.
"""

import argparse
import copy
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.harness_collection import _runtime
from proworksim.online_collection import run_fragment
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "frozen-collaboration-evaluation-v0.21"


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def checked(value):
    path = Path(value["path"])
    if ref(path) != value:
        raise ValueError("Frozen reference changed")
    return path


def task(out, name):
    write(out / "task.json", {"task": name, "started_at": time.time(), "pid": os.getpid()})


def execute(owner, catalog, output):
    from proworksim.templates.retail_collaboration_v021 import assess_episode, build_case

    rows = []
    initial = owner.freeze_identity()
    for i, case in enumerate(catalog["situations"]):
        task(output, case["case_id"])
        folder = output / f"slot-{i}"
        prepared = build_case(case, folder)
        snapshot = owner.capture_evaluation_state()
        identity = owner.begin_window("v021-e-" + str(i))
        if identity != initial:
            raise ValueError("Frozen E policy changed between worlds")
        runtime, captured, _ = _runtime(owner, prepared, folder, "native_v15")
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["evaluation_only"] = {
            "version": VERSION, "training_projection": False,
            "qualification": "Inference identity/record/tool integrity only; training probability is not an entry gate."}
        seed = 202609280100 + i
        owner.reseed(seed, label=case["case_id"])
        episode = folder / "episode"
        row = {"case_id": case["case_id"], "slot": i, "sampling_seed": seed,
               "actor_identity": identity, "status": "started", "started_at": time.time()}
        rows.append(row)
        write(output / "progress.json", rows)
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(),
                          work_nodes=["TEAM::build"], work_ids=[], scenario=scenario,
                          policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            write(folder / "public-capture.json", captured)
            write(folder / "runtime.json", runtime.snapshot())
            assessment = assess_episode(episode)
            write(folder / "assessment.json", assessment)
            row.update(status="closed", boundary=boundary, assessment=assessment,
                       assessment_ref=ref(folder / "assessment.json"), ended_at=time.time())
            # No probability recomputation is requested here. This guard only
            # checks that the resident parameters/optimizers remained frozen.
            owner.finish_evaluation([{ "slot_id": case["case_id"],
                "active_members": prepared.active_roles, "reward": assessment}], folder / "frozen-evaluation")
            guard = owner.finish_evaluation_guard(snapshot)
            write(folder / "evaluation-guard.json", guard)
            if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                raise ValueError("Frozen evaluation changed learning state or failed RNG restoration")
            row["evaluation_guard"] = guard
        except BaseException as error:
            row.update(status="interrupted_or_unassessed", error={"type": type(error).__name__, "message": str(error)},
                       ended_at=time.time())
            write(folder / "public-capture.json", captured)
            write(folder / "runtime.json", runtime.snapshot())
            write(output / "progress.json", rows)
            raise
        write(output / "progress.json", rows)
        if not assessment["eligible"]:
            return {"status": "stopped_unassessable_or_untrusted", "rows": rows,
                    "not_started_case_ids": [c["case_id"] for c in catalog["situations"][i+1:]]}
    return {"status": "complete", "rows": rows, "not_started_case_ids": []}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    from scripts.run_ne_v021 import validate_plan
    plan = read_json(a.plan)
    validate_plan(plan)
    source = code_identity()
    if source["code_dirty"] or os.environ.get("CUDA_VISIBLE_DEVICES") not in {str(i) for i in range(8)}:
        raise ValueError("Freeze source and select exactly one GPU before E")
    from proworksim.candidate_runtime_v0201 import CandidateActor

    prior_plan = read_json(checked(plan["N_prior_plan"]))
    catalog = read_json(checked(plan["E_catalog"]))
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / "launch-plan.json", plan)
    report = {"version": VERSION, "status": "loading", "source_before": source,
              "qualification": {"inference": "requires actual trusted identity/records and managed tools",
                                "training_probability": "not assessed or required in E; old failure unchanged",
                                "backward_capacity": "not assessed", "parameter_updates": "forbidden"},
              "planned_episodes": 6, "optimizer_steps": 0, "model_api_calls": 0,
              "training_projection": False, "old_P1_unstarted_worlds_backfilled": False}
    write(output / "report.json", report)
    owner = None
    try:
        task(output, "E-model-loading")
        recipe = copy.deepcopy(prior_plan["recipe"])
        recipe["max_rss_bytes"] = plan["limits"]["host_rss_bytes"]
        owner = CandidateActor.from_candidate(prior_plan["model"], manifest=checked(prior_plan["manifest"]),
            profile=prior_plan["runtime_profile"], recipe=recipe, output=output / "resident")
        original = read_json(checked(plan["N_saved_response"]))["response"]["actor_identity"]
        if owner.freeze_identity() != original:
            raise ValueError("Actual E initialization differs from the selected fixed candidate")
        report.update(status="evaluating", initial_actor_identity=owner.freeze_identity())
        write(output / "report.json", report)
        result = execute(owner, catalog, output)
        report.update(result)
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report.update(final_actor_identity=None, actor_steps=owner.actor_steps if owner else None,
                      critic_steps=owner.critic_steps if owner else None)
        if owner is not None:
            try:
                report["final_actor_identity"] = owner._make_identity()
                report["final_identity_matches_initial"] = report["final_actor_identity"] == report.get("initial_actor_identity")
            except BaseException as error:
                report["final_identity_matches_initial"] = None
                report["identity_check_error"] = {"type": type(error).__name__, "message": str(error)}
        try:
            report["source_after"] = code_identity()
            report["source_unchanged"] = report["source_before"] == report["source_after"]
        except BaseException as error:
            report["source_unchanged"] = None
            report["source_check_error"] = {"type": type(error).__name__, "message": str(error)}
        write(output / "report.json", report)
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
