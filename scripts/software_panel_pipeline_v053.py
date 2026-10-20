"""One outcome-blind preparation pipeline followed by the fixed 280-slot supervisor."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import shlex
import signal
import subprocess
import time

from proworksim import software_panel_native_v053 as native
from scripts import software_panel_host_v053 as host

VERSION = "software-panel-pipeline-v053"
DEFAULT_PATHS = {
    "environment_admission": "evidence/environment-admission.json",
    "panel": "evidence/panel.json",
    "backend_control_root": "backend-control",
    "backend_control": "evidence/backend-control.json",
    "host_config": "evidence/host-config.json",
    "preparation_root": "preparation",
    "initial_inputs_root": "initial-inputs",
    "model_admission": "evidence/model-admission.json",
    "execution_root": "execution",
    "report_json": "report.json",
    "report_markdown": "report.md",
}


class GateFailure(RuntimeError):
    pass


def source_identity(project):
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "scripts"],
        cwd=project, text=True)
    if dirty:
        raise GateFailure("Commit all source changes before this one-shot pipeline")
    return {
        name: subprocess.check_output(
            ["git", "rev-parse", "HEAD:" + name], cwd=project, text=True).strip()
        for name in ("src", "scripts")
    }


def command_for(base, python, module, arguments, *, source_root=None, cpu_runtime=False):
    root = Path(source_root or base["project_root"])
    paths = [str(root / "src"), str(root)]
    if cpu_runtime:
        paths.extend(base["dependency_paths"])
    prefix = ([base["runtime_launcher"], "--write-project"] if cpu_runtime else [])
    return [
        *prefix, "/usr/bin/env", "PYTHONPATH=" + ":".join(paths),
        "PYTHONDONTWRITEBYTECODE=1", "LITELLM_LOCAL_MODEL_COST_MAP=True",
        "OPENHANDS_SUPPRESS_BANNER=1",
        "/bin/sh", "-c", "cd " + shlex.quote(str(root)) + ' && exec "$@"', "v053-pipeline-step",
        str(python), "-B", "-m", module, *map(str, arguments),
    ]


def resolved_paths(config):
    root = Path(config["paths"]["pipeline_root"]).resolve()
    result = {"pipeline_root": root}
    result.update({
        key: Path(config["paths"].get(key, root / relative)).resolve()
        for key, relative in DEFAULT_PATHS.items()
    })
    if len(set(result.values())) != len(result):
        raise ValueError("Pipeline outputs must have distinct new destinations")
    return result


def run_pipeline(config_path, *, executor=None):
    """An executor injection is used only by finite CPU orchestration controls."""
    config_path = Path(config_path).resolve()
    config = host.read(config_path)
    base_spec = config["host_prepare_config_base"]
    base = copy.deepcopy(base_spec if isinstance(base_spec, dict) else host.read(base_spec))
    paths = resolved_paths(config)
    project = Path(base["project_root"]).resolve()
    frozen_source = source_identity(project)
    for name, path in paths.items():
        if path.exists():
            raise FileExistsError("One-shot pipeline refuses an existing output: " + name + "=" + str(path))
    root = paths["pipeline_root"]
    root.mkdir(parents=True)
    state_path = root / "pipeline-state.json"
    state = {
        "version": VERSION, "config_ref": native.ref(config_path), "source_tree_ids": frozen_source,
        "paths": {key: str(value) for key, value in paths.items()},
        "status": "preparing", "stages": [], "started_at": time.time(),
        "formal_supervisor_entered": False, "formal_completion_claimed": False,
        "failure": None, "automatic_pipeline_retries": False,
        "input_refs": {
            "environment_config": native.ref(config["environment_config"]),
            "inventory": native.ref(config["inventory"]),
            **({"host_prepare_config_base": native.ref(base_spec)}
               if not isinstance(base_spec, dict) else {}),
        },
    }
    host_python = config.get("host_python", str(project / ".venv/bin/python"))
    harness_python = config["harness_python"]
    current_child, received_signals = [None], []
    prior_handlers = {}

    def save():
        state["updated_at"] = time.time()
        state["received_signals"] = list(received_signals)
        native.write(state_path, state)

    def on_signal(number, frame):
        received_signals.append(signal.Signals(number).name)
        if current_child[0] is not None:
            host.signal_owned_process(current_child[0], number)

    def stage(name, command, *, accepted=(0,), check_source=True):
        if received_signals and name != "readonly_report":
            raise GateFailure("Pipeline was interrupted before " + name)
        if check_source and source_identity(project) != frozen_source:
            raise GateFailure("Source changed after pipeline entry; no mixed execution")
        if name != "readonly_report":
            if native.ref(config_path) != state["config_ref"]:
                raise GateFailure("Pipeline configuration changed after entry")
            for reference in state["input_refs"].values():
                native.checked(reference)
        index = len(state["stages"])
        record = {
            "name": name, "command": command, "started_at": time.time(),
            "ended_at": None, "exit_code": None, "pid": None,
            "log_path": str(root / f"{index:02d}-{name}.log"), "status": "running",
        }
        state["stages"].append(record)
        save()
        try:
            if executor is not None:
                code = executor(name, command, project, Path(record["log_path"]))
            else:
                with Path(record["log_path"]).open("xb") as log:
                    process = subprocess.Popen(
                        command, cwd=project, stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                    current_child[0] = process
                    record["pid"] = process.pid
                    save()
                    code = process.wait()
            record.update(exit_code=code, ended_at=time.time(),
                          status="complete" if code in accepted else "failed")
            save()
            if code not in accepted:
                raise GateFailure(f"{name} exited {code}; see its preserved log")
            return code
        finally:
            current_child[0] = None
            if record["ended_at"] is None:
                record.update(ended_at=time.time(), status="failed")
                save()

    def cpu(module, arguments, *, python=None, source=None):
        return command_for(base, python or harness_python, module, arguments,
                           source_root=source, cpu_runtime=True)

    def ordinary(module, arguments, *, source=None):
        return command_for(base, host_python, module, arguments, source_root=source)

    def readonly_report():
        if paths["panel"].exists():
            arguments = [
                "--panel", paths["panel"], "--reports-root", paths["execution_root"],
                "--output", paths["report_json"], "--markdown", paths["report_markdown"],
            ]
            execution_state = paths["execution_root"] / "state.json"
            if execution_state.exists():
                arguments.extend(["--state", execution_state])
            source = paths["preparation_root"] / "source"
            stage("readonly_report", ordinary(
                "scripts.software_panel_v053_report", arguments,
                source=source if source.exists() else None), check_source=False)
        else:
            native.write_new(paths["report_json"], {
                "version": VERSION, "kind": "preparation_gate_report", "status": "paused",
                "panel_frozen": False, "formal_supervisor_entered": False,
                "main_completion_rate": None, "new_model_generations": 0,
                "failure": state["failure"], "pipeline_config": state["config_ref"],
                "environment_admission_ref": (
                    native.ref(paths["environment_admission"])
                    if paths["environment_admission"].exists() else None),
                "scope": "No 200-task panel was frozen; no model capability estimate exists.",
            })
        state["readonly_report_ref"] = native.ref(paths["report_json"])

    for number in (signal.SIGTERM, signal.SIGINT):
        prior_handlers[number] = signal.signal(number, on_signal)
    save()
    result_code = 78
    try:
        arguments = [
            "--config", config["environment_config"], "--inventory", config["inventory"],
            "--output", paths["environment_admission"],
            "--workers", config.get("environment_workers", 4), "--target-repositories", 20,
        ]
        if config.get("allow_image_pull", True):
            arguments.append("--allow-image-pull")
        stage("environment_admission", cpu("scripts.software_panel_environment_v053", arguments))
        environment = host.read(paths["environment_admission"])
        if (environment.get("ready_to_freeze") is not True
                or environment.get("paused_common_system_fault") is not False
                or environment.get("model_runs_started") != 0):
            raise GateFailure("Environment admission did not qualify a 200-task panel")
        stage("freeze_panel", ordinary("scripts.software_panel_v053", [
            "freeze", "--inventory", config["inventory"], "--admission", paths["environment_admission"],
            "--output", paths["panel"],
        ]))
        panel = host.read(paths["panel"])
        stage("backend_control", cpu("scripts.software_panel_environment_v053", [
            "--config", config["environment_config"], "--control-task-id", panel["main_task_ids"][0],
            "--control-root", paths["backend_control_root"], "--output", paths["backend_control"],
        ]))
        control = host.read(paths["backend_control"])
        if (control.get("passed") is not True or control.get("model_calls") != 0
                or control.get("generation_tokens") != 0):
            raise GateFailure("The complete export-to-original-judge CPU control did not pass")
        base["environment_admission_ref"] = native.ref(paths["environment_admission"])
        base["backend_config"] = host.read(config["environment_config"])
        base["backend_control_ref"] = native.ref(paths["backend_control"])
        native.write_new(paths["host_config"], base)
        stage("prepare_snapshot", ordinary("scripts.software_panel_host_v053", [
            "prepare", "--config", paths["host_config"], "--panel", paths["panel"],
            "--output", paths["preparation_root"],
        ]))
        preparation_plan = paths["preparation_root"] / "preparation-plan.json"
        snapshot = paths["preparation_root"] / "source"
        stage("initial_capture", cpu("scripts.software_panel_host_v053", [
            "capture-panel", "--plan", preparation_plan, "--output", paths["initial_inputs_root"],
        ], python=base["native_python"], source=snapshot))
        initial_path = paths["initial_inputs_root"] / "initial-inputs.json"
        initial = host.read(initial_path)
        if initial.get("passed") is not True or len(initial.get("rows", [])) != 200:
            raise GateFailure("All 200 actual initial requests must pass before formal model entry")
        # The formal runner independently validates this evidence's complete task
        # identities, exact panel/SDK/contract, zero-generation counters and fit.
        native.write_new(paths["model_admission"], {
            "version": VERSION + "-model-admission", "passed": True,
            "formal_model_calls_allowed": True, "environment_qualification_passed": True,
            "initial_inputs_passed": True, "panel_sha256": native.ref(paths["panel"])["sha256"],
            "environment_admission_ref": base["environment_admission_ref"],
            "backend_control_ref": base["backend_control_ref"],
            "initial_inputs_ref": native.ref(initial_path),
            "preparation_plan_ref": native.ref(preparation_plan),
            "maximum_episodes": 280, "maximum_actual_tokens": 140000000,
            "new_training_authorized": False, "new_architecture_comparison_authorized": False,
            "source_tree_ids": frozen_source,
        })
        plan_path = paths["preparation_root"] / "plan.json"
        stage("seal_model_plan", ordinary("scripts.software_panel_host_v053", [
            "seal", "--plan", preparation_plan, "--admission", paths["model_admission"],
            "--output", plan_path,
        ], source=snapshot))
        state["status"], state["formal_supervisor_entered"] = "running", True
        save()
        supervisor_code = stage("supervise", ordinary("scripts.software_panel_host_v053", [
            "supervise", "--plan", plan_path, "--run-root", paths["execution_root"],
        ], source=snapshot), accepted=(0, 78))
        execution = host.read(paths["execution_root"] / "state.json")
        complete = (
            supervisor_code == 0 and execution.get("status") == "complete"
            and len(execution.get("slots", [])) == 280 and not execution.get("active")
            and {row["slot_id"] for row in execution["slots"]} == {row["slot_id"] for row in panel["slots"]}
            and all(row.get("status") == "complete" for row in execution["slots"])
        )
        state["status"] = "complete" if complete else "paused"
        state["formal_completion_claimed"] = complete
        state["host_state_ref"] = native.ref(paths["execution_root"] / "state.json")
        if not complete:
            state["failure"] = {"stage": "supervise", "reason": "Public host pause; no automatic continuation"}
        result_code = 0 if complete else 78
    except BaseException as error:
        state["status"], state["formal_completion_claimed"] = "paused", False
        state["failure"] = {
            "stage": state["stages"][-1]["name"] if state["stages"] else "preparation",
            "type": type(error).__name__, "reason": str(error),
        }
        result_code = 78
    finally:
        save()
        try:
            readonly_report()
        except Exception as error:
            state["status"] = "paused"
            state["report_failure"] = {"type": type(error).__name__, "reason": str(error)}
            result_code = 78
        state["ended_at"] = time.time()
        save()
        for number, handler in prior_handlers.items():
            signal.signal(number, handler)
    return result_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    return run_pipeline(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
