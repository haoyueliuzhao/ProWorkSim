"""One fixed H1 -> selected migration/pilot + four-project continuation.

Only launch completion is observed before final selection. Each declared job may
be started once, in its own session. No retry, checkpoint restore, replacement
sample, timeout signal, or result-driven resource/recipe change is supported.
"""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proworksim.storage import atomic_write, digest, json_bytes

VERSION = "fixed-harness-continuation-v0.19"
CANDIDATES = ("qwen35-9b", "qwen38-27b")
POLL_SECONDS = 30
RESOURCE_WAIT_SECONDS = 48 * 3600
MIN_FREE_MIB = {"qwen35-9b": 65536, "qwen38-27b": 78000}
LANES = {
    "qwen35-9b": {"learning": [0, 1], "projects": [2, 3]},
    "qwen38-27b": {"learning": [0, 1, 2, 3], "projects": [4, 5, 6, 7]},
}
OPTIMIZED_LANES = {
    "qwen35-9b": {"learning": [0, 1], "replica": [2, 3], "projects": [0, 1]},
    "qwen38-27b": {"learning": [0, 1, 2, 3], "replica": [4, 5, 6, 7], "projects": [0, 1, 2, 3]},
}


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def checked(reference):
    path = Path(reference["path"]).resolve()
    if ref(path)["sha256"] != reference["sha256"]:
        raise ValueError("Bound artifact changed: " + str(path))
    return path


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def assert_source(source, expected_commit=None):
    source = Path(source).resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip()
    if dirty or (expected_commit is not None and head != expected_commit):
        raise ValueError("Continuation requires its fixed clean source commit")
    return head


def h1_finished(paths):
    """This guard reads only the two actual launcher JSON files, never scores."""
    observations = {candidate: read(path) for candidate, path in paths.items()}
    ended = set(observations) == set(CANDIDATES) and all(
        isinstance(row, dict) and finite(row.get("end")) and type(row.get("exit_code")) is int
        for row in observations.values()
    )
    return ended, observations


def resource_decision(raw, gpus, minimum_free_mib):
    """Literal free-memory admission, not a backward capacity certification."""
    reasons, available = [], {}
    if raw.get("gpu_returncode") != 0:
        return {"ready": False, "reasons": ["gpu_query_failed"], "gpus": available}
    try:
        for line in raw.get("gpu_stdout", "").splitlines():
            fields = [part.strip() for part in line.split(",")]
            index = int(fields[0])
            available[index] = {
                "uuid": fields[1],
                "memory_free_mib": float(fields[2]),
                "memory_total_mib": float(fields[3]),
                "utilization_gpu_percent": float(fields[4]),
            }
    except (ValueError, IndexError):
        return {"ready": False, "reasons": ["unparsed_gpu_capacity"], "gpus": available}
    for gpu in gpus:
        if gpu not in available:
            reasons.append(f"gpu_{gpu}_absent")
        elif not finite(available[gpu]["memory_free_mib"]) or not finite(
            available[gpu]["memory_total_mib"]
        ):
            reasons.append(f"gpu_{gpu}_capacity_unknown")
        elif available[gpu]["memory_free_mib"] < minimum_free_mib:
            reasons.append(f"gpu_{gpu}_free_below_declared_threshold")
    if raw.get("process_returncode") != 0:
        reasons.append("competition_query_failed")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "minimum_free_mib_per_gpu": minimum_free_mib,
        "gpus": {str(gpu): available.get(gpu) for gpu in gpus},
        "scope": "Small competing allocations are allowed when this literal threshold passes; no process is stopped.",
    }


def query_resources():
    result = {"time": time.time()}
    for label, command in [
        (
            "gpu",
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,memory.free,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
        ),
        (
            "process",
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name",
                "--format=csv,noheader,nounits",
            ],
        ),
    ]:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
            result.update(
                {
                    label + "_returncode": completed.returncode,
                    label + "_stdout": completed.stdout,
                    label + "_stderr": completed.stderr,
                }
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            result.update(
                {
                    label + "_returncode": None,
                    label + "_stdout": "",
                    label + "_stderr": type(error).__name__,
                }
            )
    return result


def pilot_candidate(planned, migration_report):
    """Construct an in-memory candidate; caller validates BEFORE writing it."""
    if (
        planned.get("experiment_id") not in {"h2-pilot-v017", "h2-pilot-v018", "h2-pilot-v019"}
        or planned.get("initialization", {}).get("restore_checkpoint_permitted") is not False
    ):
        raise ValueError("Only the fixed fresh H2 pilot may follow migration")
    candidate = copy.deepcopy(planned)
    candidate["launch_gate"] = {
        "version": {"v017": "h2-admission-v0.17", "v018": "h2-admission-v0.18",
                    "v019": "h2-admission-v0.19"}[planned["experiment_id"].rsplit("-", 1)[1]],
        "state": "admitted",
        "migration_report": ref(migration_report),
    }
    return candidate


def admit_pilot(planned_path, migration_report, destination, *, model, manifest, validator):
    if Path(destination).exists():
        raise FileExistsError("Pilot admission is a single attempt")
    candidate = pilot_candidate(read(planned_path), migration_report)
    admitted = validator(
        candidate, model_path=model, weight_manifest=manifest, restore_checkpoint=None
    )
    if admitted.get("status") != "admitted":
        raise ValueError("Actual migration gate did not admit the fixed pilot")
    write(destination, candidate)
    return admitted


def migration_allows_admission(job):
    return (
        job.get("status") == "complete"
        and job.get("exit_code") == 0
        and job.get("actual_status") == "complete"
        and job.get("actual_report") is not None
    )


def config_for(project, source, output, optimization_admission, *, replicas=2, devices=None,
               learning_gpus=None, replica_gpus=None):
    project, source, output = map(lambda p: Path(p).resolve(), (project, source, output))
    if source != Path(__file__).resolve().parents[1]:
        raise ValueError("Execute this script from the declared frozen source tree")
    commit = assert_source(source)
    from proworksim.harness_learning_admission import OPTIMIZATION_VERSION

    if type(replicas) is not int or replicas not in (1, 2) or (devices is not None and (type(devices) is not int or devices < 1)):
        raise ValueError("Explicit fixed sampler count and positive device count required")
    learning_gpus, replica_gpus = gpu_list(learning_gpus), gpu_list(replica_gpus)
    if devices is not None:
        execution_lanes(devices, replicas, learning_gpus, replica_gpus)
    optimization_ref = ref(optimization_admission)
    optimization = read(checked(optimization_ref))
    if (not isinstance(optimization, dict) or optimization.get("version") != OPTIMIZATION_VERSION
            or optimization.get("execution_source_commit") != commit
            or optimization.get("sampling_replicas") != replicas
            or not isinstance(optimization.get("candidates"), dict)):
        raise ValueError("Actual optimization admission must bind this frozen source before continuation")
    launcher = project / "runs/v015-launch/launcher.py"
    # Do not resolve this symlink: the venv prefix must remain intact.
    python = project / "runs/v016-sdk/resident-venv/bin/python"
    if not python.is_file() or not launcher.is_file():
        raise FileNotFoundError("The existing isolated resident environment/launcher is required")
    environment = {
        "PYTHONPATH": str(source / "src"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "LITELLM_LOCAL_MODEL_COST_MAP": "true",
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PROWORKSIM_RETAIL_ASSETS": str(project / "runs/assets/uci-online-retail-v015"),
        "PROWORKSIM_RETAIL_HARNESS_ASSETS": str(project / "runs/assets/uci-retail-harness-v016"),
        "TMPDIR": str(output / "tmp"),
    }
    return {
        "version": VERSION,
        "project": str(project),
        "source": str(source),
        "source_commit": commit,
        "python": str(python),
        "launcher": ref(launcher),
        "environment": environment,
        "h1_launches": {
            c: str(project / f"runs/v017-launch/h1-{c}.launch.json") for c in CANDIDATES
        },
        "h1_runs": {c: str(project / f"runs/harness-v017-h1-{c}") for c in CANDIDATES},
        "poll_seconds": POLL_SECONDS,
        "resource_wait_seconds": RESOURCE_WAIT_SECONDS,
        "minimum_free_mib_per_gpu": MIN_FREE_MIB,
        "lanes": "Explicit GPU groups if supplied; otherwise consecutive original-width groups. Fixed before any migration slot.",
        "sampling_replicas": replicas,
        "optimized_devices": devices,
        "learning_gpus": learning_gpus,
        "replica_gpus": replica_gpus,
        "optimization_admission": optimization_ref,
        "resource_basis": "Actual long-request 9B peak about46GiB/device and27B maximum71.84GiB plus declared headroom. Not training/backward capacity certification.",
        "stage_revision": "Original H1 remains frozen; v0.19 binds measured prefix/replica execution to unchanged v0.18 work budgets. Learning and four-project evaluation use the same parent lane serially; no extra queue layer.",
        "support_density": "Separate 16-episode plan only; not automatically deployed before completed pilot; no O4.",
        "fixed_plan": {
            "migration": 8,
            "pilot_train": 64,
            "pilot_evaluation": 54,
            "project_evaluation": 4,
        },
        "timeout_policy": "Stop observer only; no signal or cancellation of any downstream/other process",
        "retry_policy": "Every job has one launch intent only; no sample replacement, restart, recipe/tolerance change or best-checkpoint selection",
    }


def command_step(config, state, label, command, output):
    assert_source(config["source"], config["source_commit"])
    row = {"command": command, "started_at": time.time(), "status": "started"}
    state.setdefault("metadata_steps", {})[label] = row
    write(output / "state.json", state)
    with (output / f"{label}.log").open("x") as log:
        result = subprocess.run(
            command,
            cwd=config["source"],
            env={**os.environ, **config["environment"]},
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    row.update(
        ended_at=time.time(),
        exit_code=result.returncode,
        status="complete" if result.returncode == 0 else "failed",
    )
    write(output / "state.json", state)
    return result.returncode


def gpu_list(value):
    if value is None:
        return None
    values = [int(item.strip()) for item in value.split(",")] if isinstance(value, str) else list(value)
    if not values or any(type(i) is not int or i < 0 for i in values) or len(set(values)) != len(values):
        raise ValueError("Declare a nonempty unique physical GPU list")
    return values


def execution_lanes(devices, replicas, learning_gpus=None, replica_gpus=None):
    if type(devices) is not int or devices < 1 or type(replicas) is not int or replicas not in (1, 2):
        raise ValueError("Declare positive devices and one or two sampling replicas")
    parent = gpu_list(learning_gpus) or list(range(devices))
    child = gpu_list(replica_gpus)
    if len(parent) != devices:
        raise ValueError("Learning GPU count differs from the benchmarked devices")
    if replicas == 1:
        if child is not None:
            raise ValueError("Single-replica execution cannot declare an unused second GPU group")
        child = []
    else:
        child = child or list(range(devices, 2 * devices))
        if len(child) != devices or set(parent) & set(child):
            raise ValueError("Replica GPUs must be equally sized and disjoint")
    return {"learning": parent, "replica": child, "projects": list(parent)}


def make_jobs(config, selected, selection_path, output):
    h1_root = Path(selected["run_root"])
    owner = read(h1_root / "resident/owner.json")
    base = owner["base_identity"]
    model, manifest = str(Path(base["path"]).resolve()), str(checked(base["manifest"]))
    candidate = selected["candidate_id"]
    optimized = bool(config.get("optimization_admission"))
    protocol = read(checked(selected["protocol_ref"]))
    devices = config.get("optimized_devices")
    if devices is None:
        devices = protocol["runtime"]["profile"]["devices"]
    replicas_count = config.get("sampling_replicas", 2)
    lanes = execution_lanes(devices, replicas_count, config.get("learning_gpus"), config.get("replica_gpus")) if optimized else LANES[candidate]
    if not optimized and protocol["runtime"]["profile"]["devices"] != len(lanes["learning"]):
        raise ValueError(
            "Selected device placement differs from the predeclared continuation lanes"
        )
    common = [config["python"], str(Path(config["source"]) / "scripts/online_learning_v015.py")]
    jobs = {}
    for name in ("migration", "projects", "pilot"):
        directory = output / name
        prefix = output / "launches" / name
        gpus = lanes["projects" if name == "projects" else "learning"]
        if name == "projects":
            command = [
                config["python"],
                "-m",
                "scripts.retail_project_model_v017",
                "--selection",
                str(selection_path),
                "--candidate",
                candidate,
                "--model",
                model,
                "--weight-manifest",
                manifest,
                "--harness",
                selected["harness"],
                "--output",
                str(directory),
            ]
        else:
            plan = (
                output
                / "plans"
                / ("migration.json" if name == "migration" else "pilot-admitted.json")
            )
            command = common + [
                "--protocol",
                str(plan),
                "--model",
                model,
                "--weight-manifest",
                manifest,
                "--output",
                str(directory),
            ]
        if optimized and name == "projects":
            command += ["--optimization-admission", str(checked(config["optimization_admission"])),
                        "--optimization-replicas", str(replicas_count), "--devices", str(devices)]
        waiting = name == "migration" or (name == "projects" and not optimized)
        replicas = lanes.get("replica", []) if name != "projects" else []
        jobs[name] = {
            "name": name,
            "status": "waiting_resources" if waiting else "blocked_on_learning" if name == "projects" else "blocked_on_actual_migration",
            "command": command,
            "output": str(directory),
            "prefix": str(prefix),
            "gpus": gpus,
            "required_gpus": gpus + replicas,
            "replica_gpus": replicas,
            "minimum_free_mib": MIN_FREE_MIB[candidate],
            "resource_wait_started_at": time.time() if waiting else None,
            "launch_attempted": False,
            "launch_attempt_count": 0,
            "actual_report": None,
            "actual_status": None,
            "exit_code": None,
        }
    return jobs, model, manifest


def launch_job(config, state, job, output):
    if job["launch_attempted"] or job["launch_attempt_count"] != 0:
        raise ValueError("An attempted job may never be restarted")
    assert_source(config["source"], config["source_commit"])
    launcher = checked(config["launcher"])
    prefix = Path(job["prefix"])
    if (
        Path(job["output"]).exists()
        or prefix.with_suffix(".log").exists()
        or prefix.with_suffix(".launch.json").exists()
    ):
        raise FileExistsError("Existing downstream output prohibits a new launch")
    job.update(
        status="launch_intent",
        launch_attempted=True,
        launch_attempt_count=1,
        launch_intent_at=time.time(),
    )
    write(output / "state.json", state)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        **config["environment"],
        "CUDA_VISIBLE_DEVICES": ",".join(map(str, job["gpus"])),
    }
    # Child processes inherit this explicit physical lane; the collector checks
    # equal widths/disjointness and never changes the original model placement.
    if job.get("replica_gpus"):
        environment["PROWORKSIM_REPLICA_GPUS"] = ",".join(map(str, job["replica_gpus"]))
    else:
        environment.pop("PROWORKSIM_REPLICA_GPUS", None)
    try:
        with prefix.with_suffix(".observer.log").open("x") as log:
            child = subprocess.Popen(
                [config["python"], str(launcher), str(prefix), *job["command"]],
                cwd=config["source"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        job.update(status="running", launcher_pid=child.pid, launched_at=time.time())
    except OSError as error:
        job.update(
            status="launch_failed", error={"type": type(error).__name__, "message": str(error)}
        )
    write(output / "state.json", state)


def observe_job(job):
    if job["status"] != "running":
        return
    launch_path = Path(job["prefix"]).with_suffix(".launch.json")
    launch = read(launch_path)
    if launch:
        if launch.get("command") != job["command"] or launch.get(
            "CUDA_VISIBLE_DEVICES"
        ) != ",".join(map(str, job["gpus"])):
            raise ValueError("Downstream actual launcher binding differs")
        job["actual_child_pid"] = launch.get("pid")
    if not launch or not finite(launch.get("end")) or type(launch.get("exit_code")) is not int:
        return
    directory = Path(job["output"])
    report_path = directory / ("report.json" if job["name"] == "projects" else "online/report.json")
    report = read(report_path)
    job.update(
        exit_code=launch["exit_code"],
        ended_at=launch["end"],
        launch_record=ref(launch_path),
        actual_report=ref(report_path) if report else None,
        actual_status=(report or {}).get("status"),
        status="complete"
        if launch["exit_code"] == 0 and (report or {}).get("status") == "complete"
        else "failed_or_incomplete",
    )
    if (directory / "interruption.json").exists():
        job["interruption"] = ref(directory / "interruption.json")


def learning_report(config, state, name, output):
    job = state["jobs"][name]
    if job.get("reporter_attempted"):
        return
    job["reporter_attempted"] = True
    directory = Path(job["output"])
    if (
        not (directory / "launch-protocol.json").exists()
        or not (directory / "online/report.json").exists()
    ):
        job["readonly_report"] = {
            "status": "skipped",
            "reason": "No actual online report and protocol to analyze",
        }
        return
    destination = output / f"{name}-readonly"
    code = command_step(
        config,
        state,
        name + "-report",
        [
            config["python"],
            "-m",
            "scripts.harness_learning_report_v017",
            "--run",
            str(directory),
            "--output",
            str(destination),
        ],
        output,
    )
    job["readonly_report"] = {
        "status": "complete" if code == 0 else "failed",
        "directory": str(destination),
        "exit_code": code,
    }


def release_projects_after_learning(jobs):
    """Only the fixed three-job continuation; never overlap projects with replicas."""
    projects = jobs["projects"]
    if projects["status"] != "blocked_on_learning":
        return False
    active = {"running", "launch_intent", "waiting_resources", "blocked_on_actual_migration"}
    if any(jobs[name]["status"] in active for name in ("migration", "pilot")):
        return False
    projects.update(status="waiting_resources", resource_wait_started_at=time.time(),
                    learning_terminal_before_project_launch={
                        name: jobs[name]["status"] for name in ("migration", "pilot")})
    return True


def run(config, state, output):
    # No partial H1 scores influence any scheduling decision in this loop.
    while True:
        ended, launches = h1_finished(config["h1_launches"])
        state.update(
            status="waiting_actual_H1_end",
            observed_at=time.time(),
            H1_launch_status={
                c: {k: (row or {}).get(k) for k in ("pid", "start", "end", "exit_code")}
                for c, row in launches.items()
            },
        )
        write(output / "state.json", state)
        if ended:
            break
        time.sleep(POLL_SECONDS)
    command = [
        config["python"],
        "-m",
        "scripts.harness_report_v017",
        "--output",
        str(output / "H1"),
    ]
    for candidate in CANDIDATES:
        command += [
            "--run",
            candidate + "=" + config["h1_runs"][candidate],
            "--launch",
            candidate + "=" + config["h1_launches"][candidate],
        ]
    if command_step(config, state, "H1-report", command, output):
        state["status"] = "stopped_H1_report_failure"
        return 1
    selection_path = output / "H1/selection.json"
    selection = read(selection_path)
    state.update(selection=ref(selection_path), selection_status=selection.get("status"))
    if selection.get("status") != "selected":
        state["status"] = "stopped_no_selected_combination"
        return 0
    selected = selection["selected"]
    protocol_path = checked(selected["protocol_ref"])
    command = [
        config["python"],
        "-m",
        "scripts.build_harness_learning_v019",
        "--selection",
        str(selection_path),
        "--protocol",
        str(protocol_path),
        "--output",
        str(output / "plans"),
    ]
    command += ["--optimization-admission", str(checked(config["optimization_admission"])),
                "--replicas", str(config["sampling_replicas"])]
    if config.get("optimized_devices") is not None:
        command += ["--devices", str(config["optimized_devices"])]
    if command_step(config, state, "build-plans", command, output):
        state["status"] = "stopped_plan_construction_failure"
        return 1
    jobs, model, manifest = make_jobs(config, selected, selection_path, output)
    state.update(
        status="selected_stages_active",
        selected_candidate=selected["candidate_id"],
        selected_harness=selected["harness"],
        jobs=jobs,
        model_path=model,
        weight_manifest=ref(manifest),
    )
    from proworksim.harness_learning_admission import validate_h2_launch

    while True:
        for job in jobs.values():
            observe_job(job)
        migration, pilot = jobs["migration"], jobs["pilot"]
        if pilot["status"] == "blocked_on_actual_migration" and migration["status"] in {
            "complete",
            "failed_or_incomplete",
            "launch_failed",
        }:
            if not migration_allows_admission(migration):
                pilot.update(
                    status="not_started_migration_not_complete",
                    reason="Actual migration failed or did not complete; no pilot launch",
                )
            else:
                try:
                    assert_source(config["source"], config["source_commit"])
                    admitted = admit_pilot(
                        output / "plans/pilot-planned.json",
                        checked(migration["actual_report"]),
                        output / "plans/pilot-admitted.json",
                        model=model,
                        manifest=manifest,
                        validator=validate_h2_launch,
                    )
                    write(output / "pilot-admission.json", admitted)
                    pilot.update(
                        status="waiting_resources",
                        resource_wait_started_at=time.time(),
                        admission=ref(output / "pilot-admission.json"),
                    )
                except Exception as error:
                    failure = {
                        "status": "rejected",
                        "type": type(error).__name__,
                        "reason": str(error),
                        "pilot_attempted": False,
                    }
                    write(output / "pilot-admission-rejected.json", failure)
                    pilot.update(status="not_started_migration_admission_failed", reason=failure)
        # Projects retain their own measurement even if learning fails, but only
        # after both learning jobs have reached terminal states and released GPUs.
        release_projects_after_learning(jobs)
        for name in ("migration", "pilot"):
            if jobs[name]["status"] in {"complete", "failed_or_incomplete", "launch_failed"}:
                learning_report(config, state, name, output)
        waiting = [job for job in jobs.values() if job["status"] == "waiting_resources"]
        if waiting:
            raw = query_resources()
            samples = {
                "raw": raw,
                "decisions": {
                    job["name"]: resource_decision(raw, job.get("required_gpus", job["gpus"]), job["minimum_free_mib"])
                    for job in waiting
                },
            }
            # Record the literal competition sample before any launch/timeout.
            with (output / "resource-waits.jsonl").open("a") as stream:
                stream.write(json.dumps(samples) + "\n")
                stream.flush()
            for job in waiting:
                decision = samples["decisions"][job["name"]]
                job["last_resource_decision"] = decision
                if time.time() - job["resource_wait_started_at"] >= RESOURCE_WAIT_SECONDS:
                    job.update(
                        status="resource_wait_timeout",
                        reason="Declared48h resource waiting limit reached; no job signalled",
                    )
                    state.update(
                        status="observer_resource_wait_timeout", downstream_not_signalled=True
                    )
                    write(output / "state.json", state)
                    return 2
                if decision["ready"]:
                    launch_job(config, state, job, output)
        active = any(
            job["status"]
            in {"running", "launch_intent", "waiting_resources", "blocked_on_actual_migration", "blocked_on_learning"}
            for job in jobs.values()
        )
        state["observed_at"] = time.time()
        if not active:
            state["status"] = (
                "complete"
                if all(job["status"] == "complete" for job in jobs.values())
                else "complete_with_unfinished_or_failed_stages"
            )
            write(output / "state.json", state)
            return 0 if state["status"] == "complete" else 1
        write(output / "state.json", state)
        time.sleep(POLL_SECONDS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--optimization-admission", type=Path, required=True,
                        help="Actual frozen-source v0.19 numerical/performance gate; selected failed candidate stops")
    parser.add_argument("--replicas", type=int, choices=(1, 2), required=True)
    parser.add_argument("--devices", type=int, help="Benchmarked devices per sampler; default is original selected H1 count")
    parser.add_argument("--learning-gpus", help="Explicit comma-separated physical parent GPUs")
    parser.add_argument("--replica-gpus", help="Explicit equally sized disjoint group, only for replicas=2")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = config_for(args.project, args.source, output, args.optimization_admission,
                        replicas=args.replicas, devices=args.devices,
                        learning_gpus=args.learning_gpus, replica_gpus=args.replica_gpus)
    (output / "tmp").mkdir()
    write(output / "config.json", config)
    state = {
        "version": VERSION,
        "started_at": time.time(),
        "status": "initialized",
        "config": ref(output / "config.json"),
        "source_commit": config["source_commit"],
        "jobs": {},
        "selection": None,
        "scope": "Planned episodes are not executed episodes; actual downstream reports and launch exits are recorded separately.",
    }
    write(output / "state.json", state)

    def interrupted(signum, frame):
        raise KeyboardInterrupt("Observer interrupted; downstream sessions are not signalled")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        return run(config, state, output)
    except KeyboardInterrupt as error:
        state.update(status="observer_detached", reason=str(error), downstream_not_signalled=True)
        return 130
    except Exception as error:
        state.update(
            status="observer_error",
            error={"type": type(error).__name__, "message": str(error)},
            downstream_not_signalled=True,
        )
        return 1
    finally:
        state["last_written_at"] = time.time()
        write(output / "state.json", state)


if __name__ == "__main__":
    sys.exit(main())
