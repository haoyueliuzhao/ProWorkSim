"""Host-only native r2 activation: hold MATCH until admitted; REF remains live.

Inherits the separately sealed host hold tick without changing any existing
worker. Activation routes only future REF/MATCH through the r2 episode wrapper.
PROJECT and all previously entered tasks retain their original implementation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import time

from . import software_benchmark_queue_v055 as original
from . import software_benchmark_queue_host_v055_r2 as held
from .software_benchmark_queue_v055 import ROOT, load, now, materialize_config
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_network_v055 import direct_environment_command
from .storage import digest

VERSION = "v055-native-dispatch-hold-and-route-host-r2"


class NativeHostCoordinator(held.HostCoordinator):
    def __init__(self, revision_ref):
        self.revision_ref, self.revision = revision_ref, load(revision_ref)
        if self.revision.get("version") != VERSION:
            raise ValueError("Unknown native host revision")
        for item in self.revision["files"]:
            checked(item)
        original.Coordinator.__init__(self, self.revision["original_plan"])
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
                raise ValueError("An adopted native solver activation cannot disappear")
            return
        ref = reference(path)
        if self.activation_ref is not None:
            if ref != self.activation_ref:
                raise ValueError("An adopted native solver activation cannot change")
            return
        value = load(ref)
        if (value.get("version") != "v055-native-solver-activation-r2"
                or value.get("original_plan") != self.plan_ref
                or set(value.get("arms", [])) != {"REF", "MATCH"}
                or value.get("admitted") is not True
                or not isinstance(value.get("runtime_revision"), str) or not value["runtime_revision"]):
            raise ValueError("Native activation lacks its independent qualified identity")
        if load(value["qualification"]).get("passed") is not True:
            raise ValueError("Failed native qualification cannot release MATCH or change REF")
        frozen = {item["path"]: item for item in self.plan["frozen_sources"]}
        for item in value["files"]:
            checked(item)
            if item["path"] in frozen and item != frozen[item["path"]]:
                raise ValueError("Native r2 cannot rewrite an original frozen dependency")
        for name, expected in (("generation_entrypoint", "run_deepseek_episode_v055_r2.py"),
                               ("controller_entrypoint", "run_deepseek_controller_v055_r2.py")):
            entry = checked(value[name])
            if value[name] not in value["files"] or not entry.is_relative_to(ROOT) or entry.name != expected:
                raise ValueError("Native r2 entrypoints must be separately frozen local files")
        self.activation, self.activation_ref = value, ref
        self.state["native_solver_activation"] = ref
        self.state["activated_solver_arms"] = ["REF", "MATCH"]
        self.save()

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
            if slot["arm"] in {"REF", "MATCH"} and self.activation is not None:
                value = load(config)
                value.update(solver_activation=self.activation_ref,
                    runtime_revision=self.activation["runtime_revision"],
                    frozen_sources=[*value["frozen_sources"], *self.activation["files"], self.activation_ref])
                config = write_new(directory / "config.json", value)
                record["runtime_revision"] = self.activation_ref
            argv = [python, "-m", "proworksim.software_benchmark_runner_v055",
                    "--config", config["path"], "--output", str(directory / "episode")]
            if slot["arm"] in {"REF", "MATCH"} and self.activation is not None:
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--plan", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--activation", required=True, type=Path)
    freeze.add_argument("--previous-controller", required=True)
    run = commands.add_parser("run")
    run.add_argument("--revision", required=True, type=Path)
    run.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        plan = reference(args.plan)
        if load(plan)["version"] != original.VERSION:
            raise ValueError("Host revision requires the original plan")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ref = write_new(args.output, {"version": VERSION, "created_utc": now(),
            "original_plan": plan, "hold_until_activation": ["MATCH"],
            "routed_after_activation": ["REF", "MATCH"], "PROJECT_runner_unchanged": True,
            "activation_path": str(args.activation.resolve()),
            "previous_controller_unit": args.previous_controller,
            "files": [reference(__file__), reference(ROOT / "tools/run_deepseek_queue_native_host_v055_r2.py"),
                      reference(held.__file__), reference(original.__file__)],
            "existing_workers_adopted": True, "model_calls": 0, "automatic_model_replay": False})
        print(json.dumps(ref))
        return
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Native host revision SHA mismatch")
    coordinator = NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    main()
