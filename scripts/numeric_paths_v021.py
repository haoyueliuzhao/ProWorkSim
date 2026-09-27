"""Run the fixed N diagnostic inside the separately authorized one-GPU supervisor.

No resource selection, waiting, sampling, optimizer step or successor is here.
"""

import argparse
import os
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.numeric_paths_v021 import VERSION, diagnose
from proworksim.online_training import reference
from proworksim.storage import atomic_write, json_bytes, read_json

ORIGINAL_CALL_SHA256 = "6a348353e319fe7ceb4954168f592f61188ea2a6ef94be02c58aa6d8566c9f65"
ORIGINAL_NUMERICAL_SHA256 = "49371bd535c435e9e09242d341e41def50c837eba5c63edf708a952f6373687a"


def run(prior_run, output):
    prior_run, output = Path(prior_run).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("N diagnostic requires a new output directory")
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("N execution source must be frozen and clean")
    plan = read_json(prior_run / "plan.json")
    prior_report = read_json(prior_run / "report.json")
    numeric = read_json(prior_run / "numerical.json")
    call_path = prior_run / "resident/calls" / (numeric["rows"][0]["response_id"] + ".json")
    call = read_json(call_path)
    if (reference(call_path)["sha256"] != ORIGINAL_CALL_SHA256
            or reference(prior_run / "numerical.json")["sha256"] != ORIGINAL_NUMERICAL_SHA256
            or reference(prior_run / "plan.json")["sha256"] != prior_report["plan"]["sha256"]):
        raise ValueError("The fixed archived N inputs changed; no new sample may be substituted")
    if (prior_report["status"] != "stopped_numeric_gate" or not prior_report["source_unchanged"]
            or plan["runtime_profile"]["version"] != "candidate-runtime-v0.20.1"
            or numeric["status"] != "failed" or len(numeric["rows"]) != 1):
        raise ValueError("The original closed v0.20.1 numeric failure is required")
    output.mkdir(parents=True)
    report = {"version": VERSION, "status": "started", "source_before": source,
              "prior_plan": reference(prior_run / "plan.json"), "prior_report": reference(prior_run / "report.json"),
              "original_call": reference(call_path), "original_numerical": reference(prior_run / "numerical.json"),
              "sampled_new_tokens": 0, "world_episodes": 0, "backward_calls": 0,
              "optimizer_steps": 0, "automatic_successors": []}
    def save():
        atomic_write(output / "report.json", json_bytes(report))
    save()
    owner = None
    try:
        from proworksim.candidate_runtime_v0201 import CandidateActor

        atomic_write(output / "task.json", json_bytes({"task": "model-loading", "started_at": time.time(), "pid": os.getpid()}))
        owner = CandidateActor.from_candidate(plan["model"], manifest=plan["manifest"]["path"],
            profile=plan["runtime_profile"], recipe=plan["recipe"], output=output / "resident")
        report["paths"] = diagnose(owner, call, numeric, output)
        report["status"] = "complete_diagnostic"
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        # Preserve obtainable facts even if a forward/OOM/observation fails.
        # A missing owner or failed tensor read is unknown, never a passed guard.
        guard = {"owner_constructed": owner is not None, "actor_steps": None,
                 "critic_steps": None, "actor_identity_unchanged": None}
        if owner is not None:
            guard.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps)
            try:
                guard["actual_actor_identity"] = owner._make_identity()
                guard["original_actor_identity"] = call["response"]["actor_identity"]
                guard["actor_identity_unchanged"] = guard["actual_actor_identity"] == guard["original_actor_identity"]
                guard["parameter_gradients_present"] = any(p.grad is not None for p in owner.actor_parameters.values())
            except BaseException as error:
                guard["identity_check_error"] = {"type": type(error).__name__, "message": str(error)}
        report["final_owner_guard"] = guard
        try:
            report["source_after"] = code_identity()
            report["source_unchanged"] = report["source_after"] == source
        except BaseException as error:
            report["source_unchanged"] = None
            report["source_check_error"] = {"type": type(error).__name__, "message": str(error)}
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.prior_run, args.output)


if __name__ == "__main__":
    main()
