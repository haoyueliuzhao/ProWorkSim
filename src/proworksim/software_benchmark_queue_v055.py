"""Durable, CPU-only six-condition queue with independent scoring and API cap.

Workers have unique systemd units and durable intents. A coordinator restart
adopts existing workers; a missing completion becomes a deferred exception, not
an automatic repeat of an API episode. Scoring uses the already locked candidate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime, timezone

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_deepseek_api_v055 import BudgetLedger
from .software_benchmark_network_v055 import concurrency_limits, direct_environment_command, disk_admission, host_capacity
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "runs/software-benchmark-v055"
VERSION = "v055-six-condition-queue-r1"
CONDITIONS = {arm + "-" + mode for arm in ("REF", "MATCH", "PROJECT")
              for mode in ("thinking", "nonthinking")}


def now():
    return datetime.now(timezone.utc).isoformat()


def load(reference_value):
    return json.loads(checked(reference_value).read_bytes())


def validate_plan(plan):
    if (plan.get("version") != VERSION or plan.get("execution_authorized") is not True
            or set(plan["conditions"]) != CONDITIONS
            or not 1 <= plan["generation_concurrency"] <= 32
            or not 1 <= plan["scoring_concurrency"] <= 4
            or plan.get("maximum_api_concurrency") != 64
            or plan.get("preparation_concurrency", 2) != 2
            or plan.get("budget_cny") != 2000):
        raise ValueError("Only the qualified, capped six-condition API plan is accepted")
    slots = load(plan["slots"])["slots"]
    if (len(slots) != 3000 or len({row["slot_id"] for row in slots}) != 3000
            or Counter(row["condition_id"] for row in slots) != Counter({key: 500 for key in CONDITIONS})):
        raise ValueError("All 500 tasks in all six conditions must remain in the planned denominator")
    panels = [{row["instance_id"] for row in slots if row["condition_id"] == condition}
              for condition in sorted(CONDITIONS)]
    if any(len(panel) != 500 or panel != panels[0] for panel in panels):
        raise ValueError("Six conditions must contain the same 500 distinct tasks")
    for index in range(0, 3000, 6):
        block = slots[index:index + 6]
        if (len({row["instance_id"] for row in block}) != 1
                or {row["condition_id"] for row in block} != CONDITIONS):
            raise ValueError("Budget-limited dispatch requires predeclared six-condition task blocks")
    for condition, ref in plan["conditions"].items():
        if load(ref)["condition_id"] != condition:
            raise ValueError("Condition identity differs from its immutable reference")
    for ref in plan["frozen_sources"]:
        checked(ref)
    template = load(plan["template"])
    if (template.get("all_solver_admissions_passed") is not True
            or template.get("max_api_concurrency") != 64
            or template.get("ledger_path") != plan["ledger_path"]):
        raise ValueError("Controller admission and global ledger must be shared by all six groups")
    root = Path(plan["queue_root"]).resolve()
    if not root.is_relative_to(RUN_ROOT):
        raise ValueError("New queue must not write into prior experiments")
    return slots, template


def materialize_config(plan, template, slot, output):
    """Only public task data reaches the controller; hidden data stays scorer-side."""
    task = next(row for row in load(template["public_tasks"]) if row["instance_id"] == slot["instance_id"])
    registry = load(template["public_test_registry"])
    entry = next(row for row in registry["entries"] if row["instance_id"] == slot["instance_id"])
    image = next(row for row in load(template["image_inventory"])["images"]
                 if row["instance_id"] == slot["instance_id"])
    condition = load(plan["conditions"][slot["condition_id"]])
    value = {**template, "version": "v055-deepseek-slot-config-r1", **slot,
        "thinking": condition["thinking"], "slots": plan["slots"],
        "configuration": plan["conditions"][slot["condition_id"]],
        "frozen_sources": plan["frozen_sources"], "public_task": task,
        "public_test_entry": entry, "preparation_only": False,
        "scorer_request_base": {**template["scorer_request_base"], "image": image,
                                "baseline_mapping": entry["baseline_mapping"]}}
    return write_new(output, value)


def active(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=ActiveState,MainPID"], capture_output=True, text=True, timeout=15)
    if result.returncode:
        return False
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return values.get("ActiveState") in {"active", "activating", "deactivating"} or int(values.get("MainPID", 0)) > 0


def worker(job_ref):
    job = load(job_ref)
    directory = Path(job["directory"])
    if not directory.resolve().is_relative_to(RUN_ROOT):
        raise ValueError("Worker directory must be independent v055 state")
    completion = directory / "completion.json"
    if completion.exists():
        raise FileExistsError("A completed generation/scoring job is never relaunched")
    started = now()
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        try:
            result = subprocess.run(job["argv"], stdout=stdout, stderr=stderr, timeout=job["timeout_seconds"])
            value = {"returncode": result.returncode, "status": "process_exited"}
        except Exception as error:
            value = {"returncode": None, "status": "technical_unknown",
                     "error": {"type": type(error).__name__, "message": str(error)}}
    write_new(completion, {"version": VERSION, "job": job_ref, "started_utc": started,
                          "finished_utc": now(), **value})


def prepare_instance(request_ref):
    """Add one missing template under the original exact-key exclusive lock."""
    from .software_benchmark_native_lazy_v054 import ensure_native_instance
    from .software_benchmark_prewarm_v054 import preparation_state
    request = load(request_ref)
    value = {"version": "v055-zero-model-native-preparation-r1",
        "instance_id": request["instance_id"], "request": request_ref,
        "model_calls": 0, "formal_claims": 0, "grader_calls": 0, "started_utc": now()}
    cache = Path(request["cache_root"])
    try:
        state = preparation_state(request["instance_id"], mapping_reference=request["baseline_mapping"],
                                  cache_root=cache)
        if state["status"] == "failed":
            value.update(status="deferred_environment_failure", prior=state)
        elif state["status"] == "preparing":
            value.update(status="resource_wait", reason="another_exact_key_preparer_owns_lock")
        elif state["status"] != "qualified" and shutil.disk_usage(cache).free < 128 * 1024**3:
            value.update(status="resource_wait", reason="disk_free_below_128GiB")
        else:
            prepared = ensure_native_instance(request["instance_id"],
                mapping_reference=request["baseline_mapping"], cache_root=cache,
                stdlib=Path(request["stdlib"]), public_tasks_reference=request["public_tasks"],
                docker_socket=request["docker_socket"])
            value.update(status="qualified", reused=(state["status"] == "qualified"), prepared=prepared)
    except BlockingIOError:
        value.update(status="resource_wait", reason="concurrent_exact_key_lock_race_no_initializer_entered")
    except Exception as error:
        value.update(status="deferred_environment_failure",
                     error={"type": type(error).__name__, "message": str(error)})
    value["finished_utc"] = now()
    write_new(Path(request["output"]) / "preparation-result.json", value)


class Coordinator:
    def __init__(self, plan_ref):
        self.plan_ref, self.plan = plan_ref, load(plan_ref)
        slots, self.template = validate_plan(self.plan)
        self.root = Path(self.plan["queue_root"])
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease = (self.root / "coordinator.lock").open("a")
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.state_path = self.root / "state.json"
        self.registry = {row["instance_id"]: row for row in load(self.template["public_test_registry"])["entries"]}
        self.ledger = BudgetLedger(self.plan["ledger_path"], max_concurrency=64)
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_bytes())
            if self.state["plan"] != plan_ref or [row["slot"] for row in self.state["rows"]] != slots:
                raise ValueError("Existing queue belongs to a different frozen experiment")
        else:
            self.state = {"version": VERSION, "plan": plan_ref, "created_utc": now(),
                "rows": [{"slot": slot, "generation": {"status": "pending"}, "scores": []} for slot in slots],
                "exceptions": [], "dispatch_stopped": False}
            self.save()
        self.state.setdefault("preparation", {name: {"readiness": {"status": "unknown"}, "attempts": []}
                                              for name in self.registry})

    def save(self):
        self.state["updated_utc"] = now()
        atomic_write(self.state_path, json_bytes(self.state))

    def launch(self, row, record, *, kind, request=None):
        slot = row["slot"]
        identity = slot["slot_id"] + ("-generation" if kind == "generation" else "-score-" + request["sha256"])
        suffix = digest(identity.encode())[:24]
        directory = self.root / "workers" / (kind + "-" + suffix)
        directory.mkdir(parents=True, exist_ok=False)
        unit = "proworksim-v055-" + kind + "-" + suffix + ".service"
        python = str(ROOT / ".venv/bin/python")
        if kind == "generation":
            config = materialize_config(self.plan, self.template, slot, directory / "config.json")
            argv = [python, "-m", "proworksim.software_benchmark_runner_v055",
                    "--config", config["path"], "--output", str(directory / "episode")]
            timeout = 6600
        else:
            argv = [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project",
                "/usr/bin/env", "PYTHONPATH=" + str(ROOT / "src"),
                str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"), "-B", "-m",
                "proworksim.software_benchmark_scorer_v055", "--request", checked(request)]
            argv = list(map(str, argv))
            timeout = 2100
        argv = direct_environment_command(argv)
        job_ref = write_new(directory / "job.json", {"version": VERSION, "kind": kind,
            "slot": slot, "plan": self.plan_ref, "directory": str(directory), "unit": unit,
            "argv": argv, "timeout_seconds": timeout, "request": request})
        record.update(status="running", job=job_ref, unit=unit, directory=str(directory), dispatched_utc=now())
        self.save()  # Durable intent precedes launch; ambiguity is never automatically repeated.
        try:
            subprocess.run(["systemd-run", "--user", "--quiet", "--unit=" + unit,
                "--property=Restart=no", "--property=KillMode=control-group",
                "--property=TimeoutStopSec=40", "--property=RuntimeMaxSec=" + str(timeout + 60),
                "--property=WorkingDirectory=" + str(ROOT), "--setenv=PYTHONPATH=" + str(ROOT / "src"),
                "--", python, "-m", "proworksim.software_benchmark_queue_v055", "worker",
                "--job", job_ref["path"], "--sha256", job_ref["sha256"]],
                check=True, capture_output=True, text=True, timeout=20)
        except Exception as error:
            # A timed-out systemd client may have successfully created the unit.
            record["launch_observation"] = {"type": type(error).__name__, "message": str(error)}
        self.save()

    def defer(self, row, record, reason):
        record.update(status="technical_unknown", reason=reason, finished_utc=now())
        self.state["exceptions"].append({"slot_id": row["slot"]["slot_id"],
            "kind": "score" if "request" in record else "generation", "reason": reason,
            "job": record.get("job"), "request": record.get("request"), "created_utc": now()})

    def refresh_preparation(self):
        from .software_benchmark_prewarm_v054 import preparation_state
        for name, record in self.state["preparation"].items():
            job = record.get("worker")
            if job and job["status"] == "running":
                directory = Path(job["directory"])
                completion = directory / "completion.json"
                result_path = directory / "preparation-result.json"
                if completion.exists():
                    result = json.loads(result_path.read_bytes()) if result_path.exists() else {
                        "status": "deferred_environment_failure", "reason": "preparer_result_missing"}
                    job.update(status=result["status"], completion=reference(completion), finished_utc=now())
                    if result_path.exists():
                        job["result"] = reference(result_path)
                    record["attempts"].append(dict(job))
                    if result["status"] == "deferred_environment_failure":
                        record["readiness"] = {"status": "failed", "instance_id": name,
                                               "worker_result": job.get("result"), "reason": result.get("reason")}
                elif not active(job["unit"]):
                    job.update(status="deferred_environment_failure", finished_utc=now())
                    record["attempts"].append(dict(job))
                    record["readiness"] = {"status": "failed", "instance_id": name,
                                           "reason": "preparer_missing_without_completion"}
            if record["readiness"]["status"] not in {"qualified", "failed"}:
                try:
                    record["readiness"] = preparation_state(name,
                        mapping_reference=self.registry[name]["baseline_mapping"],
                        cache_root=Path(self.template["lazy_native_preparation"]["cache_root"]))
                except (OSError, ValueError) as error:
                    record["readiness"] = {"status": "failed", "instance_id": name,
                        "reason": "cache_observation_invalid", "error": {"type": type(error).__name__, "message": str(error)}}
            if record["readiness"]["status"] == "failed" and not record.get("exception_recorded"):
                self.state["exceptions"].append({"kind": "environment", "instance_id": name,
                    "reason": "native_preparation_deferred", "evidence": record["readiness"],
                    "formal_claims": 0, "model_calls": 0, "created_utc": now()})
                record["exception_recorded"] = True
        counts = Counter(record["readiness"]["status"] for record in self.state["preparation"].values())
        self.state["environment_coverage"] = {"planned_distinct_tasks": 500, "observed_utc": now(),
            "task_status_counts": dict(counts), "all_six_conditions_share_one_qualified_template_per_task": True}

    def launch_preparation(self, instance_id):
        record = self.state["preparation"][instance_id]
        ordinal = len(record["attempts"]) + 1
        suffix = digest((instance_id + ":" + str(ordinal)).encode())[:24]
        directory = self.root / "workers" / ("preparation-" + suffix)
        directory.mkdir(parents=True, exist_ok=False)
        unit = "proworksim-v055-preparation-" + suffix + ".service"
        request = write_new(directory / "request.json", {"instance_id": instance_id,
            "baseline_mapping": self.registry[instance_id]["baseline_mapping"],
            "cache_root": self.template["lazy_native_preparation"]["cache_root"],
            "stdlib": self.template["stdlib"], "public_tasks": self.template["public_tasks"],
            "docker_socket": "unix://" + self.template["scorer_request_base"]["docker_socket"],
            "output": str(directory), "model_calls_authorized": 0, "formal_claims_authorized": 0})
        python = str(ROOT / ".venv/bin/python")
        argv = [python, "-m", "proworksim.software_benchmark_queue_v055", "prepare-instance",
                "--request", request["path"], "--sha256", request["sha256"]]
        job_ref = write_new(directory / "job.json", {"version": VERSION, "kind": "preparation",
            "instance_id": instance_id, "plan": self.plan_ref, "directory": str(directory),
            "unit": unit, "argv": direct_environment_command(argv), "timeout_seconds": 3600})
        record["worker"] = {"status": "running", "job": job_ref, "unit": unit,
                            "directory": str(directory), "dispatched_utc": now()}
        self.save()
        try:
            subprocess.run(["systemd-run", "--user", "--quiet", "--unit=" + unit,
                "--property=Restart=no", "--property=KillMode=control-group", "--property=CPUQuota=400%",
                "--property=MemoryMax=17179869184", "--property=TasksMax=16384",
                "--property=TimeoutStopSec=40", "--property=RuntimeMaxSec=3660",
                "--property=WorkingDirectory=" + str(ROOT), "--setenv=PYTHONPATH=" + str(ROOT / "src"),
                "--", python, "-m", "proworksim.software_benchmark_queue_v055", "worker",
                "--job", job_ref["path"], "--sha256", job_ref["sha256"]],
                check=True, capture_output=True, text=True, timeout=20)
        except Exception as error:
            record["worker"]["launch_observation"] = {"type": type(error).__name__, "message": str(error)}
        self.save()

    def collect(self, row, record, *, kind):
        if record["status"] != "running":
            return
        directory = Path(record["directory"])
        if not (directory / "completion.json").exists():
            if not active(record["unit"]):
                self.defer(row, record, "worker_missing_without_completion")
            return
        done = json.loads((directory / "completion.json").read_bytes())
        if done["job"] != record["job"]:
            raise ValueError("Worker completion belongs to another immutable job")
        record["completion"] = reference(directory / "completion.json")
        if kind == "generation":
            path = directory / "episode/result.json"
            if not path.exists():
                self.defer(row, record, "generation_result_absent")
                return
            result = json.loads(path.read_bytes())
            if result.get("slot_id") != row["slot"]["slot_id"]:
                raise ValueError("Generation identity crossed slots")
            record["result"] = reference(path)
            record["controller_status"] = result.get("controller_status")
            record["administratively_censored"] = result.get("controller_status") == "budget_exhausted"
            if done["returncode"] != 0 or result.get("status") != "closed":
                self.defer(row, record, "generation_technical_unknown")
                return
            record.update(status="closed", finished_utc=now())
            row["scores"] = [{"status": "pending", "request": ref} for ref in result["scoring_requests"]]
        else:
            request = load(record["request"])
            pointer = Path(request["receipt_output"])
            if done["returncode"] != 0 or not pointer.exists():
                self.defer(row, record, "official_score_missing_or_ambiguous")
                return
            linked = json.loads(pointer.read_bytes())
            identity, receipt = load(linked["identity"]), load(linked["receipt"])
            if (identity.get("slot_id") != request["slot_id"]
                    or identity.get("condition_id") != request["condition_id"]
                    or identity.get("attempt") != request["attempt"]
                    or identity.get("patch_sha256") != request["patch"]["sha256"]):
                raise ValueError("Official scoring receipt crosses condition/candidate/attempt")
            record["receipt"] = linked["receipt"]
            if receipt["status"] != "official_report":
                self.defer(row, record, "official_score_technical_unknown")
            else:
                record.update(status="official_report", resolved=receipt["resolved"], finished_utc=now())

    def tick(self):
        for row in self.state["rows"]:
            self.collect(row, row["generation"], kind="generation")
            for score in row["scores"]:
                self.collect(row, score, kind="score")
        self.refresh_preparation()
        generating = sum(row["generation"]["status"] == "running" for row in self.state["rows"])
        scoring = sum(score["status"] == "running" for row in self.state["rows"] for score in row["scores"])
        budget, capacity = self.ledger.snapshot(), host_capacity()
        capacity.update(disk_admission(shutil.disk_usage(ROOT).free))
        try:
            legacy = json.loads((ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json").read_bytes())
            legacy_generations = sum(row["generation"]["status"] in {"intent", "running"}
                                     for row in legacy["rows"])
            legacy_graders = sum(score["status"] in {"intent", "running"}
                for row in legacy["rows"] for score in row["scores"].values())
            limits = concurrency_limits(cpu_count=os.cpu_count() or 0,
                memory_available_bytes=capacity["memory_available_bytes"],
                legacy_generations=legacy_generations, legacy_graders=legacy_graders,
                configured_generation=self.plan["generation_concurrency"],
                configured_scoring=self.plan["scoring_concurrency"],
                api_concurrency=self.plan["maximum_api_concurrency"], current_generations=generating)
            capacity.update(limits)
            if not capacity["admit"]:
                capacity.update(desired_generation_concurrency=0, desired_scoring_concurrency=0)
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Missing old-pipeline telemetry is not proof that its CPUs are free.
            capacity.update(admit=False, desired_generation_concurrency=0, desired_scoring_concurrency=0,
                legacy_observation_error={"type": type(error).__name__, "message": str(error)})
        wait_seconds = max(0, budget.get("admission_wait_seconds", 0))
        self.state["budget"], self.state["capacity"] = budget, capacity
        may_dispatch = (not budget["halted"] and budget["can_admit_minimum_request"]
                        and capacity["admit"] and capacity["generation_disk_admitted"] and wait_seconds <= 0)
        self.state["API_admission_wait_seconds"] = wait_seconds
        if budget["halted"] or (wait_seconds <= 0 and not budget["can_admit_minimum_request"]
                               and budget["inflight_count"] == 0):
            self.state["dispatch_stopped"] = True
            self.state["stop_reason"] = "shared_budget_or_accounting_gate"
        preparing = sum(record.get("worker", {}).get("status") == "running"
                        for record in self.state["preparation"].values())
        seen_tasks = set()
        for row in self.state["rows"]:
            name = row["slot"]["instance_id"]
            if name in seen_tasks or preparing >= self.plan.get("preparation_concurrency", 2):
                continue
            seen_tasks.add(name)
            record = self.state["preparation"][name]
            if (capacity["admit"] and capacity["preparation_disk_admitted"] and not self.state["dispatch_stopped"]
                    and record["readiness"]["status"] == "pending"
                    and record.get("worker", {}).get("status") != "running"
                    and shutil.disk_usage(self.template["lazy_native_preparation"]["cache_root"]).free >= 128 * 1024**3):
                self.launch_preparation(name)
                preparing += 1
        for row in self.state["rows"]:
            readiness = self.state["preparation"][row["slot"]["instance_id"]]["readiness"]
            row["environment_status"] = readiness["status"]
            if (may_dispatch and not self.state["dispatch_stopped"]
                    and generating < capacity["desired_generation_concurrency"]
                    and row["generation"]["status"] == "pending" and readiness["status"] == "qualified"
                    and disk_admission(shutil.disk_usage(ROOT).free)["generation_disk_admitted"]):
                self.launch(row, row["generation"], kind="generation")
                generating += 1
            for score in row["scores"]:
                if (capacity["admit"] and scoring < capacity["desired_scoring_concurrency"]
                        and score["status"] == "pending"):
                    self.launch(row, score, kind="score", request=score["request"])
                    scoring += 1
        pending = any(row["generation"]["status"] == "pending" for row in self.state["rows"])
        score_pending = any(score["status"] == "pending" for row in self.state["rows"] for score in row["scores"])
        only_deferred_environments = pending and all(row["environment_status"] == "failed"
            for row in self.state["rows"] if row["generation"]["status"] == "pending")
        done = (generating == scoring == preparing == 0 and not score_pending
                and (not pending or self.state["dispatch_stopped"] or only_deferred_environments))
        if done:
            self.state["status"] = ("budget_closed_with_pending" if self.state["dispatch_stopped"] and pending else
                "primary_finished_with_deferred_environment" if only_deferred_environments else "primary_inventory_finished")
            self.state["ended_utc"] = now()
        self.save()
        return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--sha256", required=True)
    child = commands.add_parser("worker")
    child.add_argument("--job", required=True, type=Path)
    child.add_argument("--sha256", required=True)
    preparation = commands.add_parser("prepare-instance")
    preparation.add_argument("--request", required=True, type=Path)
    preparation.add_argument("--sha256", required=True)
    args = parser.parse_args()
    path = args.plan if args.operation == "run" else args.request if args.operation == "prepare-instance" else args.job
    ref = reference(path)
    if ref["sha256"] != args.sha256:
        raise ValueError("CLI immutable input hash mismatch")
    if args.operation == "worker":
        worker(ref)
    elif args.operation == "prepare-instance":
        prepare_instance(ref)
    else:
        coordinator = Coordinator(ref)
        try:
            while not coordinator.tick():
                time.sleep(5)
        finally:
            coordinator.lease.close()


if __name__ == "__main__":
    main()
