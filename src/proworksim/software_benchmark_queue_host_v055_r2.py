"""Independent host revision: hold future MATCH, then route only qualified r2.

Original slots, ledger, source files and in-flight worker jobs are unchanged.
Only tick/launch are copied from the sealed r1 coordinator; the dispatch gate and
an optional immutable per-MATCH activation are the explicit differences.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from . import software_benchmark_queue_v055 as original
from .software_benchmark_queue_v055 import ROOT, load, now, materialize_config
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_network_v055 import concurrency_limits, direct_environment_command, disk_admission, host_capacity
from .storage import digest

VERSION = "v055-MATCH-dispatch-hold-and-route-host-r2"


class HostCoordinator(original.Coordinator):
    def __init__(self, revision_ref):
        self.revision_ref, self.revision = revision_ref, load(revision_ref)
        if self.revision.get("version") != VERSION:
            raise ValueError("Unknown host-only revision")
        for item in self.revision["files"]:
            checked(item)
        super().__init__(self.revision["original_plan"])
        self.activation = self.activation_ref = None
        history = self.state.setdefault("host_revision_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adopted_utc": now(),
                            "existing_worker_jobs_unchanged": True, "entered_slots_replayed": 0})
        self.state["active_host_revision"] = revision_ref
        self.state["MATCH_dispatch_hold"] = True
        self.save()

    def load_activation(self):
        path = Path(self.revision["activation_path"])
        if not path.exists():
            if self.activation is not None:
                raise ValueError("An adopted solver activation cannot disappear")
            return
        ref = reference(path)
        if self.activation_ref is not None:
            if ref != self.activation_ref:
                raise ValueError("An adopted solver activation cannot change")
            return
        value = load(ref)
        if (value.get("version") != "v055-MATCH-solver-activation-r2"
                or value.get("original_plan") != self.plan_ref
                or value.get("arm") != "MATCH" or value.get("admitted") is not True
                or not isinstance(value.get("runtime_revision"), str)
                or not value["runtime_revision"]):
            raise ValueError("MATCH activation lacks its independent qualified identity")
        qualification = load(value["qualification"])
        if qualification.get("passed") is not True:
            raise ValueError("A failed solver qualification cannot release MATCH")
        frozen = {item["path"]: item for item in self.plan["frozen_sources"]}
        for item in value["files"]:
            checked(item)
            if item["path"] in frozen and item != frozen[item["path"]]:
                raise ValueError("A solver revision cannot rewrite an original frozen dependency")
        entry = checked(value["generation_entrypoint"])
        if (value["generation_entrypoint"] not in value["files"] or not entry.is_relative_to(ROOT)
                or not entry.name.endswith("v055_r2.py")):
            raise ValueError("Only a separately sealed local r2 runner may be activated")
        self.activation, self.activation_ref = value, ref
        self.state["MATCH_solver_activation"] = ref
        self.save()

    def generation_allowed(self, row):
        return row["slot"]["arm"] != "MATCH" or self.activation is not None

    def launch(self, row, record, *, kind, request=None):
        slot = row["slot"]
        identity = slot["slot_id"] + ("-generation" if kind == "generation" else "-score-" + request["sha256"])
        suffix = digest(identity.encode())[:24]
        directory = self.root / "workers" / (kind + "-" + suffix)
        directory.mkdir(parents=True, exist_ok=False)
        unit = "proworksim-v055-" + kind + "-" + suffix + ".service"
        python = str(ROOT / ".venv/bin/python")
        if kind == "generation":
            config = materialize_config(self.plan, self.template, slot, directory / "base-config.json")
            if slot["arm"] == "MATCH" and self.activation is not None:
                value = load(config)
                value.update(solver_activation=self.activation_ref,
                    runtime_revision=self.activation["runtime_revision"],
                    frozen_sources=[*value["frozen_sources"], *self.activation["files"], self.activation_ref])
                config = write_new(directory / "config.json", value)
                record["runtime_revision"] = self.activation_ref
            argv = [python, "-m", "proworksim.software_benchmark_runner_v055",
                    "--config", config["path"], "--output", str(directory / "episode")]
            if slot["arm"] == "MATCH" and self.activation is not None:
                argv = [python, checked(self.activation["generation_entrypoint"]),
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

    def tick(self):
        self.load_activation()
        self.state["MATCH_dispatch_hold"] = self.activation is None
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
                    and self.generation_allowed(row)
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
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--plan", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--activation", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--revision", required=True, type=Path)
    run.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        plan = reference(args.plan)
        value = load(plan)
        if value["version"] != original.VERSION:
            raise ValueError("Host revision requires the original six-condition queue plan")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        rule = write_new(args.output, {"version": VERSION, "created_utc": now(),
            "original_plan": plan, "hold_arms_until_activation": ["MATCH"],
            "activation_path": str(args.activation.resolve()),
            "previous_controller_unit": "proworksim-v055-deepseek-six-conditions-r1.service",
            "files": [reference(__file__), reference(ROOT / "tools/run_deepseek_queue_host_v055_r2.py"),
                      reference(original.__file__)],
            "existing_workers_adopted": True, "model_calls": 0, "automatic_model_replay": False})
        print(json.dumps(rule))
        return
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Host revision SHA mismatch")
    coordinator = HostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    main()
