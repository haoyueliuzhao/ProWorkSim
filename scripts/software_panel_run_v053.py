"""Frozen-panel native workers and tokenizer-only initial capture; no training."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

from proworksim import software_panel_native_v053 as native
from proworksim.storage import digest


def read(path):
    return json.loads(Path(path).read_bytes())


def validate_environment_binding(plan, panel):
    from proworksim.software_panel_v053 import canonical_bytes
    environment = read(native.checked(plan["environment_admission_ref"]))
    if native.digest(canonical_bytes(environment)) != panel["admission_sha256"]:
        raise ValueError("The panel must bind its exact pre-model environment admission")
    if native.digest(canonical_bytes(plan["backend_config"])) != environment.get("config_sha256"):
        raise ValueError("The backend configuration differs from the frozen environment admission")
    return environment


def validate_task_qualification(plan, task_id, *, environment=None):
    """Hash this worker's one receipt, never refresh qualification authority."""
    if environment is None:
        environment = read(native.checked(plan["environment_admission_ref"]))
    expected = (Path(plan["backend_config"]["environment_root"]) / "tasks"
                / task_id / "qualification.json").resolve()
    matches = [
        reference
        for repository in environment["repositories"]
        if repository.get("admitted") is True and task_id in repository.get("qualified_task_ids", [])
        for reference in repository.get("task_receipts", [])
        if reference.get("path") == str(expected)
    ]
    if len(matches) != 1:
        raise ValueError("The task lacks one unique frozen environment qualification receipt")
    native.checked(matches[0])
    return matches[0]


def validate_plan(path, *, require_admission):
    plan = read(path)
    if plan.get("contract") != native.CONTRACT:
        raise ValueError("Frozen v053 numerical contract differs")
    panel = read(native.checked(plan["panel_ref"]))
    validate_environment_binding(plan, panel)
    rows = panel["slots"]
    first = [row for row in rows if row["repeat_index"] == 1]
    repeats = Counter(row["task_id"] for row in rows if row["repeat_index"] != 1)
    if (len(rows) != 280 or len(first) != 200 or len({r["task_id"] for r in first}) != 200
            or len({r["slot_id"] for r in rows}) != 280
            or len({r["seed"] for r in rows}) != 280
            or len(repeats) != 40 or set(repeats.values()) != {2}
            or any({r["repeat_index"] for r in rows if r["task_id"] == task} != {1, 2, 3}
                   for task in repeats)
            or not set(repeats) <= {r["task_id"] for r in first}):
        raise ValueError("The complete 200-task/40-repeat/280-episode panel must be fixed")
    root = Path(plan["source_root"]).resolve()
    if not plan.get("source_files"):
        raise ValueError("Freeze the new source implementation before entry")
    for name, sha in plan["source_files"].items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or digest(source.read_bytes()) != sha:
            raise ValueError("Frozen v053 implementation changed: " + name)
    if require_admission:
        admission = read(native.checked(plan["admission_ref"]))
        if (any(admission.get(k) is not True for k in (
                "passed", "formal_model_calls_allowed",
                "environment_qualification_passed", "initial_inputs_passed"))
                or admission.get("panel_sha256") != plan["panel_ref"]["sha256"]):
            raise ValueError("Complete source/environment/initial-request admission is required")
        initial = read(native.checked(admission["initial_inputs_ref"]))
        if (initial.get("passed") is not True or initial.get("panel_ref") != plan["panel_ref"]
                or initial.get("reference_runtime") != plan["reference_runtime"]
                or initial.get("contract") != native.CONTRACT
                or len(initial.get("rows", [])) != 200
                or {row["task_id"] for row in initial["rows"]} != set(panel["main_task_ids"])
                or any(row.get("fits") is not True for row in initial["rows"])
                or any(initial.get(key) != 0 for key in (
                    "new_model_generations", "new_model_loads", "new_tool_executions",
                    "new_candidate_exports", "new_grading_executions"))):
            raise ValueError("Bind all 200 actual initial native requests before model entry")
        if admission.get("backend_control_ref") != plan.get("backend_control_ref"):
            raise ValueError("The final plan and admission must bind the same container control")
        control = read(native.checked(admission["backend_control_ref"]))
        if (control.get("passed") is not True or control.get("model_calls") != 0
                or control.get("generation_tokens") != 0
                or control.get("task_id") != panel["main_task_ids"][0]):
            raise ValueError("The pre-model original export-to-judge CPU control must pass")
    native.checked(plan["reference_runtime"])
    native.checked(plan["model_manifest"])
    if require_admission:
        native.checked(plan["model_source_receipt"])
    return plan, panel


def task_for(plan, panel, task_id):
    selected = [task for task in panel["tasks"] if task["task_id"] == task_id]
    if len(selected) != 1:
        raise ValueError("One preselected official task is required")
    root = Path(plan["task_source_root"]).resolve()
    source = (root / (task_id + ".json")).resolve()
    if not source.is_relative_to(root) or digest(source.read_bytes()) != selected[0]["source_row_sha256"]:
        raise ValueError("Original task row differs from the frozen panel")
    task = read(source)
    if task.get("instance_id") != task_id:
        raise ValueError("Task and official instance identity differ")
    return task


def phase(output, stage, *, episode_started_at=None):
    native.write(Path(output) / "phase.json", {
        "phase": stage, "at": time.time(), "pid": os.getpid(),
        "episode_started_at": episode_started_at,
    })


def provider_accounting(resident, ledger=None):
    """Reconcile the numerical provider's on-disk actual receipts once per closure."""
    from scripts.software_calibration_v051_cal2 import native_accounting
    accounting = native_accounting(resident)
    if ledger is not None:
        if (accounting["known_actual_tokens"] != ledger["known_actual_tokens"]
                or accounting["complete_generations"] != ledger["complete_responses"]
                or {c["attempt_id"] for c in accounting["actual_calls"]}
                != {c["native_attempt_id"] for c in ledger["calls"]}):
            accounting["integrity_errors"].append("v053_native_ledger_provider_mismatch")
            accounting["all_started_settled"] = False
            accounting["complete_actual_tokens"] = None
    return accounting


def worker(plan_path, slot_id, output):
    plan, panel = validate_plan(plan_path, require_admission=True)
    if Path(sys.executable).resolve() != Path(plan["native_python"]).resolve():
        raise ValueError("Run the frozen native SDK/numerical interpreter")
    rows = [row for row in panel["slots"] if row["slot_id"] == slot_id]
    if len(rows) != 1:
        raise ValueError("Select exactly one predeclared slot")
    row, output = rows[0], Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    native.write_new(output / "started.json", {
        "version": native.VERSION, "row": row, "plan": native.ref(plan_path),
        "pid": os.getpid(), "started_at": time.time(), "model_replay_allowed": False,
        "model_loader_entered": False, "scope": "resource attempt, before model entry",
    })
    backend, owner, episode_started = None, None, None
    try:
        from proworksim.software_calibration_runtime_v051 import load_actor
        from proworksim.software_panel_docker_v053 import DockerBackend
        from proworksim import software_panel_resources_v053 as resources
        task = task_for(plan, panel, row["task_id"])
        qualification_ref = validate_task_qualification(plan, row["task_id"])
        native.write_new(output / "qualified-environment-binding.json", {
            "task_id": row["task_id"], "environment_admission_ref": plan["environment_admission_ref"],
            "task_qualification_ref": qualification_ref,
        })
        binding = resources.binding_from_environment()
        phase(output, "reservation")
        try:
            resources.acquire_startup(output / "startup", binding, identity={
                "source_plan": native.ref(plan_path), "row": row,
            })
        except Exception as exc:
            if not resources.is_preload_resource_wait(exc):
                raise
            if (output / "resident").exists() or (output / "model-entered.json").exists():
                raise native.PublicSystemFault("A resource wait cannot conceal entered model work") from exc
            native.write_new(output / "report.json", {
                "version": native.VERSION, "row": row, "source_plan": native.ref(plan_path),
                "status": "resource_wait", "R_code": None, "loader_not_entered": True,
                "model_loader_entered": False, "resident_exists": False,
                "model_calls": 0, "known_actual_tokens": 0,
                "fresh_process_resource_retry_allowed": True,
                "resource_receipt": exc.receipt,
            })
            return 75
        phase(output, "preparation")
        backend = DockerBackend(plan["backend_config"], task, row, output / "backend")
        native.write_new(output / "model-entered.json", {
            "version": native.VERSION, "row": row, "source_plan": native.ref(plan_path),
            "pid": os.getpid(), "at": time.time(), "resource_binding": binding,
            "model_replay_allowed": False,
        })
        phase(output, "loading")
        owner = load_actor(
            plan["model_path"], manifest=plan["model_manifest"]["path"],
            contract=native.CONTRACT, path="project", output=output / "resident", checkpoint=None,
            verified_source_receipt=plan["model_source_receipt"])
        original_generate = owner.generate_native

        def generation(record):
            phase(output, "generation", episode_started_at=episode_started)
            try:
                with resources.native_context(owner, output / "native-cache", binding):
                    return original_generate(record)
            finally:
                phase(output, "episode", episode_started_at=episode_started)

        owner.generate_native = generation
        episode_started = time.time()
        phase(output, "episode", episode_started_at=episode_started)
        result = native.collect_episode(
            owner=owner, row=row, panel_sha256=plan["panel_ref"]["sha256"], task=task,
            backend=backend, reference_runtime=plan["reference_runtime"],
            episode_folder=output / "episode")
        phase(output, "scoring", episode_started_at=episode_started)
        if result["status"] == "execution_fault":
            grade = {"R_code": None, "technical_error": result["error"], "evaluation_skipped": True}
        else:
            grade = backend.grade_candidate(result["candidate_lock"])
        if time.time() - episode_started >= native.LIMITS["hard_seconds"]:
            grade = {**grade, "R_code": None, "technical_error": "episode_hard_deadline_exceeded"}
        phase(output, "measurement", episode_started_at=episode_started)
        accounting = provider_accounting(owner.output, result["ledger"])
        guard = owner.verify_evaluation_guard()
        episode_guard = dict(result["episode_guard"])
        if guard.get("passed") is not True or accounting["all_started_settled"] is not True:
            episode_guard["software_binding_unchanged"] = False
        verdict = native.classify_episode(
            status=result["status"], stop_reason=result["stop_reason"],
            sdk_status=result["sdk_execution_status"], ledger=result["ledger"],
            guard=episode_guard, grade=grade, error=result["error"])
        report = {
            "version": native.VERSION, "row": row, "source_plan": native.ref(plan_path),
            "result": result, "grade": grade, "accounting": accounting,
            "guard": guard, "verdict": verdict, "status": verdict["status"],
            "R_code": verdict["R_code"], "episode_started_at": episode_started,
            "closed_at": time.time(), "new_parameter_updates": 0, "new_backward_calls": 0,
        }
        native.write_new(output / "report.json", report)
        phase(output, "closed", episode_started_at=episode_started)
        return 0 if verdict["decision"] == "continue" else 78
    except BaseException as exc:
        accounting = provider_accounting(output / "resident")
        native.write_new(output / "interruption.json", {
            "version": native.VERSION, "row": row, "source_plan": native.ref(plan_path),
            "status": "technical_unknown", "R_code": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "accounting": accounting, "decision": "global_pause",
            "model_replay_allowed": False, "at": time.time(),
        })
        return 78
    finally:
        if backend is not None:
            backend.close()


class CaptureBackend:
    """Only declared metadata; cannot execute, export a patch or read scores."""
    working_dir = "/testbed"

    def __init__(self, task):
        self.identity = {
            "task_id": task["instance_id"], "fresh_initial_state": True,
            "metadata_only": True, "image_name": task["image_name"],
        }


def capture(plan_path, task_id, output):
    plan, panel = validate_plan(plan_path, require_admission=False)
    task = task_for(plan, panel, task_id)
    row = next(row for row in panel["slots"] if row["task_id"] == task_id and row["repeat_index"] == 1)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(plan["model_path"], local_files_only=True)
    owner = native.MetadataOwner(tokenizer, model_manifest=plan["model_manifest"])
    result = native.collect_episode(
        owner=owner, row=row, panel_sha256=plan["panel_ref"]["sha256"], task=task,
        backend=CaptureBackend(task), reference_runtime=plan["reference_runtime"],
        episode_folder=output, initial_capture=lambda request, record: None)
    record = read(native.checked(result["native_input"]))
    result["fits"] = record["fits"]
    native.write_new(Path(output) / "capture-result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("worker", "capture"):
        command = commands.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--slot-id" if name == "worker" else "--task-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "worker":
        return worker(args.plan, args.slot_id, args.output)
    result = capture(args.plan, args.task_id, args.output)
    print(json.dumps({"fits": result["fits"], "task_id": args.task_id}))
    return 0 if result["fits"] else 78


if __name__ == "__main__":
    raise SystemExit(main())
