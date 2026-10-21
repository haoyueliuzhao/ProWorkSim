"""Future native reasoning r3 routing and bounded unused-ready prewarming.

Reuses the sealed host r2 tick, worker launch, collection and resource gates.
No entered worker is signalled or repeated. A refused prewarm is deliberately
counted by that inherited tick until its next pass, which only under-dispatches.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import time

from . import software_benchmark_queue_v055 as original
from . import software_benchmark_queue_native_host_v055_r2 as previous
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_queue_v055 import ROOT, load, now

VERSION = "v055-native-reasoning-and-bounded-prewarm-host-r3"


def prewarm_backlog(state, limit=8):
    """Only wholly unentered, qualified tasks count as unused ready inventory."""
    tasks = defaultdict(list)
    for row in state["rows"]:
        tasks[row["slot"]["instance_id"]].append(row["generation"]["status"])
    unused = sum(len(statuses) == 6 and all(x == "pending" for x in statuses)
                 and state["preparation"][name]["readiness"]["status"] == "qualified"
                 for name, statuses in tasks.items())
    preparing = sum(record.get("worker", {}).get("status") == "running"
                    for record in state["preparation"].values())
    return {"unused_ready_tasks": unused, "preparing_tasks": preparing,
            "unused_ready_backlog_limit": limit, "admit_new_preparation": unused + preparing < limit,
            "already_running_preparers_unchanged": True}


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self, revision_ref):
        self.revision_ref, self.revision = revision_ref, load(revision_ref)
        if self.revision.get("version") != VERSION or self.revision.get("unused_ready_backlog_limit") != 8:
            raise ValueError("Unknown native r3 host policy")
        for item in self.revision["files"]:
            checked(item)
        self.activation = self.activation_ref = None
        original.Coordinator.__init__(self, self.revision["original_plan"])
        self.load_activation()  # Deployment supplies an already-qualified immutable r3 activation.
        history = self.state.setdefault("host_revision_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adopted_utc": now(),
                            "existing_worker_jobs_unchanged": True, "entered_slots_replayed": 0})
        self.state["active_host_revision"] = revision_ref
        self.state["MATCH_dispatch_hold"] = False
        self.save()

    def load_activation(self):
        ref = self.revision["activation"]
        checked(ref)
        if self.activation_ref == ref:
            return
        if self.activation_ref is not None:
            raise ValueError("An adopted r3 activation cannot change")
        value = load(ref)
        if (value.get("version") != "v055-native-solver-activation-r3"
                or value.get("original_plan") != self.plan_ref
                or set(value.get("arms", [])) != {"REF", "MATCH"}
                or value.get("admitted") is not True
                or not isinstance(value.get("runtime_revision"), str) or not value["runtime_revision"]
                or load(value["qualification"]).get("passed") is not True):
            raise ValueError("Native r3 lacks its independent qualified identity")
        frozen = {item["path"]: item for item in self.plan["frozen_sources"]}
        for item in value["files"]:
            checked(item)
            if item["path"] in frozen and item != frozen[item["path"]]:
                raise ValueError("Native r3 cannot rewrite an original frozen dependency")
        for name, expected in (("generation_entrypoint", "run_deepseek_episode_v055_r3.py"),
                               ("controller_entrypoint", "run_deepseek_controller_v055_r3.py")):
            entry = checked(value[name])
            if value[name] not in value["files"] or not entry.is_relative_to(ROOT) or entry.name != expected:
                raise ValueError("Native r3 entrypoints must be separately frozen local files")
        self.activation, self.activation_ref = value, ref
        self.state["native_solver_activation"] = ref
        self.state["activated_solver_arms"] = ["REF", "MATCH"]
        self.save()

    def refresh_preparation(self):
        super().refresh_preparation()
        self.state["prewarm_backlog"] = prewarm_backlog(self.state)

    def launch_preparation(self, instance_id):
        gate = prewarm_backlog(self.state)
        self.state["prewarm_backlog"] = gate
        if not gate["admit_new_preparation"]:
            return
        super().launch_preparation(instance_id)
        self.state["prewarm_backlog"] = prewarm_backlog(self.state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--plan", required=True, type=Path)
    freeze.add_argument("--activation", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--previous-controller", required=True)
    run = commands.add_parser("run")
    run.add_argument("--revision", required=True, type=Path)
    run.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        plan, activation = reference(args.plan), reference(args.activation)
        if load(plan)["version"] != original.VERSION or load(activation).get("admitted") is not True:
            raise ValueError("R3 requires the original plan and admitted activation")
        ref = write_new(args.output, {"version": VERSION, "created_utc": now(),
            "original_plan": plan, "activation": activation, "unused_ready_backlog_limit": 8,
            "previous_controller_unit": args.previous_controller,
            "routed_arms": ["REF", "MATCH"], "PROJECT_runner_unchanged": True,
            "files": [reference(__file__), reference(ROOT / "tools/run_deepseek_queue_native_host_v055_r3.py"),
                      reference(previous.__file__), reference(previous.held.__file__), reference(original.__file__)],
            "existing_workers_adopted": True, "model_calls": 0, "automatic_model_replay": False})
        print(json.dumps(ref))
        return
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Native host r3 revision SHA mismatch")
    coordinator = NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    main()
