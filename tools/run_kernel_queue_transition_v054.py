"""One explicit zero-formal-kernel transition from GPU6 source r3 to source r4.

This host-only entrypoint does not alter the sealed original router, workers,
queue bindings or scoring watcher. It may replace only an unactivated router.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re

from proworksim import software_benchmark_fault_queue_v054 as fault
from proworksim import software_benchmark_kernel_queue_v054 as kernel
from proworksim import software_benchmark_queue_v054 as base
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v054-zero-formal-kernel-router-transition-r1"
RELATIVE_TOOL = "tools/run_kernel_queue_transition_v054.py"
COMMON = ("original_bindings", "original_deferred_policy", "old_registration", "gpu_index", "queue_root")


def validate_transition(seal_ref, initial=False):
    seal = base.load_ref(seal_ref)
    if (seal.get("version") != VERSION or seal.get("zero_kernel_formal_required") is not True
            or seal.get("queue_root") != str(base.QUEUE)
            or seal.get("tool", {}).get("path") != str(base.ROOT / RELATIVE_TOOL)):
        raise ValueError("Unsupported kernel transition seal")
    if initial:
        checked(seal["tool"])
    if base.stat_id(seal["tool"]["path"]) != seal["tool_stat"]:
        raise ValueError("Sealed kernel transition tool changed")
    old = kernel.validate_policy(seal["old_router_policy"], initial=initial)
    new = kernel.validate_policy(seal["new_router_policy"], initial=initial)
    if (any(old.get(key) != new.get(key) for key in COMMON)
            or old["new_source_root"] == new["new_source_root"]
            or old["activation_path"] == new["activation_path"]
            or old["gpu_index"] != 6):
        raise ValueError("Transition changed shared experiment identity or reused activation/source")
    return seal, old, new


def create_transition(old_policy, new_policy, previous_controller_unit, output):
    if not re.fullmatch(r"proworksim-v054-[a-z0-9-]+\.service", previous_controller_unit):
        raise ValueError("Unexpected previous controller unit")
    tool = reference(base.ROOT / RELATIVE_TOOL)
    value = {"version": VERSION, "utc": base.now(), "queue_root": str(base.QUEUE),
             "old_router_policy": reference(old_policy), "new_router_policy": reference(new_policy),
             "previous_controller_unit": previous_controller_unit, "tool": tool,
             "tool_stat": base.stat_id(tool["path"]), "zero_kernel_formal_required": True,
             "generation_replayed": False, "old_workers_signalled": False,
             "transition_root": str(base.QUEUE / "kernel-router-transition-r1")}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    seal = write_new(output, value)
    validate_transition(seal, initial=True)
    return seal


def zero_formal_guard(state, old_policy, new_policy, claims):
    """Check existing immutable signals; no hash/model/test rescoring occurs."""
    if any(Path(policy["activation_path"]).exists() for policy in (old_policy, new_policy)):
        raise ValueError("An activation exists; this zero-formal transition is forbidden")
    roots = [Path(policy["new_source_root"]) for policy in (old_policy, new_policy)]
    for row in state["rows"]:
        if ("kernel_runtime_revision" in row or row.get("kernel_preclaim_waits")
                or "kernel_execution_bindings" in row["generation"]):
            raise ValueError("Kernel generation was dispatched; preserve its revision, never migrate")
        for name in ("original_execution_bindings", "next_execution_bindings"):
            ref = row.get(name)
            if ref and any(Path(ref["path"]).is_relative_to(root) for root in roots):
                raise ValueError("A row is already bound to a kernel revision")
    if any(event.get("kernel_activation") is not None for event in state.get("generation_dispatches", [])):
        raise ValueError("A kernel generation dispatch already exists")
    for claim in claims:
        configuration = claim.get("binding", {}).get("configuration", {})
        path = configuration.get("path")
        if path and any(Path(path).is_relative_to(root) for root in roots):
            raise ValueError("A formal claim already binds a kernel source")
    return {"kernel_activation_count": 0, "kernel_dispatch_count": 0, "kernel_claim_count": 0}


class TransitionCoordinator(kernel.KernelCoordinator):
    def __init__(self, seal_ref, *, system=None, adopting=False):
        self.transition_ref = seal_ref
        self.transition, self.old_router_policy, self.router_policy = validate_transition(seal_ref, initial=True)
        self.router_policy_ref = self.transition["new_router_policy"]
        self.activation_ref = None
        self.activation = None
        # KernelCoordinator's default constructor intentionally rejects a policy
        # replacement. This one explicitly sealed adoption uses the same original
        # deferred-fault constructor and the same durable controller lock.
        fault.ResilientCoordinator.__init__(self, self.router_policy["original_deferred_policy"], system=system)
        expected = self.transition["old_router_policy"] if adopting else self.router_policy_ref
        if self.state.get("kernel_router", {}).get("policy") != expected:
            self.lease.close()
            raise ValueError("Queue is not at the exact expected transition boundary")
        if not adopting and self.state["kernel_router"].get("transition") != seal_ref:
            self.lease.close()
            raise ValueError("The new router has not adopted this exact transition")

    def validate_state(self):
        super().validate_state()
        validate_transition(self.transition_ref)

    def adopt_transition(self):
        if self.system.active(self.transition["previous_controller_unit"]):
            raise ValueError("Previous coordinator must be stopped; workers remain running")
        claims = [base.read(path) for path in
                  (base.ROOT / "runs/software-benchmark-v054/episode-claims").glob("*/claim.json")]
        guard = zero_formal_guard(self.state, self.old_router_policy, self.router_policy, claims)
        rows_before = deepcopy(self.state["rows"])
        old_router = deepcopy(self.state["kernel_router"])
        active = []
        for row in self.state["rows"]:
            for endpoint, record in [(None, row["generation"]), *row["scores"].items()]:
                if record["status"] not in base.ACTIVE:
                    continue
                job = base.load_ref(record["job"])
                expected = "generation" if endpoint is None else "score"
                if (job["bindings"] != self.bindings_ref or job["kind"] != expected
                        or job["unit"] != record["unit"]
                        or Path(record["job"]["path"]) != Path(record["worker_directory"]) / "job.json"):
                    raise ValueError("In-flight job is not an original immutable worker")
                active.append({"slot_id": row["slot"]["slot_id"], "endpoint": endpoint,
                               "job": record["job"], "unit": record["unit"]})
        root = Path(self.transition["transition_root"])
        root.mkdir(parents=True, exist_ok=False)
        snapshot = write_new(root / "state-before-transition.json", self.state)
        evidence = write_new(root / "adoption.json", {"version": VERSION, "utc": base.now(),
            "transition": self.transition_ref, "previous_router": old_router,
            "new_router_policy": self.router_policy_ref, "state_before": snapshot,
            "original_bindings": self.bindings_ref, "inherited_original_workers": active,
            "zero_formal_guard": guard, "controller_lock_owned": True,
            "prior_controller_stopped": True, "formal_claims": 0, "model_calls": 0,
            "old_workers_signalled": False, "rows_rewritten": False})
        self.state.setdefault("kernel_router_history", []).append(old_router)
        self.state["kernel_router"] = {"version": kernel.VERSION, "policy": self.router_policy_ref,
            "adoption": evidence, "transition": self.transition_ref,
            "gpu6_original_dispatch_disabled": True}
        self.state.setdefault("operator_policy_adoptions", []).append(evidence)
        if self.state["rows"] != rows_before:
            raise AssertionError("Transition unexpectedly changed a formal row")
        self.save()
        return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--old-policy", type=Path, required=True)
    freeze.add_argument("--new-policy", type=Path, required=True)
    freeze.add_argument("--previous-controller-unit", required=True)
    freeze.add_argument("--output", type=Path, required=True)
    for name in ("adopt", "run"):
        command = sub.add_parser(name)
        command.add_argument("--transition", type=Path, required=True)
        command.add_argument("--transition-sha256", required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.command == "freeze":
        options = vars(args).copy()
        options.pop("command")
        print(json.dumps(create_transition(**options)))
        return 0
    seal = reference(args.transition)
    if seal["sha256"] != args.transition_sha256:
        raise ValueError("Transition seal identity differs")
    coordinator = TransitionCoordinator(seal, adopting=args.command == "adopt")
    try:
        if args.command == "adopt":
            print(json.dumps(coordinator.adopt_transition()))
            return 0
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
