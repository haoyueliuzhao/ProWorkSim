"""Finite model-only software episode, separate from online training admission."""
import copy
from pathlib import Path

from .episode import begin_episode, finish_episode
from .experience import ExperienceRecorder, capture_port
from .model_policy import ModelPolicy
from .staff_runtime import StaffRuntime
from .storage import atomic_write, json_bytes
from .templates.software_maintenance import (
    ASSETS, SoftwareMaintenancePort, WORK, assess_software_submission, build_software_case,
)


def collect_software_episode(config, output_dir, *, transport=None, model_identity=None):
    """No automatic edits, tests, submissions, recovery or teacher actions.

    Caller supplies the frozen real model transport/config; its resource/model
    identity is archived. This function does not launch a model or train weights.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    prepared = build_software_case("marshmallow-v15-strip-implement", output / "case")
    actor_config = copy.deepcopy(config)
    actor_config["task"] = "Complete your software implementation responsibility using the public work contract. Your output must come from actual source edits, actual isolated tests, and your explicit submission."
    actor_config.setdefault("budget", {})["max_decisions"] = 18
    policy = ModelPolicy(actor_config, transport=transport, audit_dir=output / "model-calls")
    interface = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer", audit_dir=output / "public-projections")
    captured = []
    runtime = StaffRuntime({"implementer": capture_port(interface, captured)}, {"implementer": policy}, recorder=ExperienceRecorder())
    frozen = {"protocol": (ASSETS / "protocol.json").read_text(), "model_identity": model_identity,
              "model_config": policy.config, "case": prepared.case,
              "training_admission": "not_supported_by_this_extension", "model_role": "implementer"}
    atomic_write(output / "frozen-run.json", json_bytes(frozen))
    begin_episode(prepared.world, output / "episode", experience=runtime.recorder.snapshot(), work_ids=[WORK],
                  scenario=prepared.scenario, policies=runtime.policy_identities)
    steps = []
    termination = {"status": "opportunity_limit", "limit": 18}
    terminal = {"completed", "model_service_error", "model_format_error", "model_budget_exhausted", "policy_error", "environment_error", "binding_mismatch"}
    for _ in range(18):
        step = runtime.step()
        steps.append(step)
        atomic_write(output / "runtime.json", json_bytes(runtime.snapshot()))
        if step["status"] in terminal:
            termination = {"status": step["status"], "opportunities": len(steps), "reason": step.get("reason")}
            break
    manifest = finish_episode(prepared.world, output / "episode", experience=runtime.recorder.snapshot(), termination=termination)
    # Assessment occurs after dialogue closes; no private feedback is returned to policy.
    assessment = assess_software_submission(prepared, run_root=output / "private-assessment")
    result = {"version": "software-model-collection-v0.15", "termination": termination,
              "assessment": assessment, "model_identity": model_identity,
              "opportunities": len(steps), "actions": runtime.actions,
              "episode_manifest": manifest["manifest_path"], "memory": runtime.roles["implementer"]["memory"],
              "training_admission": "not_assessed_no_software_training_in_this_run"}
    atomic_write(output / "steps.json", json_bytes(steps))
    atomic_write(output / "capture.json", json_bytes(captured))
    atomic_write(output / "result.json", json_bytes(result))
    return result
