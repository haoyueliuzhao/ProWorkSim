"""Real process interruption at ten preregistered single-writer commit cuts."""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.core.journal import canonical_digest, validate_committed_prefix
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import atomic_write, digest, json_bytes

SEED = 823
MATRIX = {
    "write": ["version_staged", "after_apply", "after_command_commit"],
    "submit": ["after_apply", "after_command_commit"],
    "reply": ["before_event_commit", "after_event_commit"],
    "revision": ["version_staged", "after_apply", "after_command_commit"],
}
EXIT_CODE = 73


class Paused(Exception):
    pass


class BeforeSubmission:
    def __init__(self, world):
        self.session = world.session()

    def observe(self):
        return self.session.observe()

    def call(self, action, **arguments):
        if action == "submit":
            raise Paused
        return self.session.call(action, **arguments)


def prepare(world):
    try:
        run_baseline(BeforeSubmission(world))
    except Paused:
        return
    raise AssertionError("Preparation did not reach an actual submit boundary")


def act(world, actor, action, args, key):
    response = world.act(actor, action, args, request_key=key)
    if not response["ok"] or response.get("pending_event_errors"):
        raise AssertionError(response)
    return response


def setup(root, kind):
    path = compile_world(
        design(SEED, delivery="file", information="clarification" if kind == "reply" else "mail"),
        root,
    )
    world = World(path)
    if kind in {"submit", "revision"}:
        prepare(world)
    elif kind == "reply":
        bid = act(
            world,
            "analyst",
            "block_work",
            {
                "work_item_id": "work-1",
                "reason": "Need scoped confirmation",
                "kind": "scope",
                "requested_role": "manager",
            },
            "prepare-block",
        )["result"]["blocker_id"]
        act(
            world,
            "analyst",
            "mail_send",
            {
                "to": "manager",
                "body": "Supply applicable approval",
                "topic": "scope",
                "work_item_id": "work-1",
                "blocker_id": bid,
            },
            "prepare-request",
        )
    else:
        # A real wrong formula is part of the common committed checkpoint. The
        # recovery protocol must not recalculate or repair these historical bytes.
        act(
            world,
            "analyst",
            "sheet_update",
            {"cells": {"RecoveryProbe!A1": "=1/0"}},
            "prepare-worker-error",
        )
    return world


def command(kind):
    return {
        "write": (
            "analyst",
            "write_file",
            {"artifact_id": "memo", "content": '{"deliberately_invalid_memo":true}'},
            "write-once",
        ),
        "submit": ("analyst", "submit", {"work_item_id": "work-1"}, "submit-once"),
        "reply": ("analyst", "wait", {"ticks": 1}, "deliver-reply-once"),
        "revision": (
            "manager",
            "revise_requirements",
            {
                "work_item_ids": ["work-1"],
                "growth_delta": 0.02,
                "reason": "Finite recovery witness",
            },
            "revise-once",
        ),
    }[kind]


def child(path, kind, phase, evidence):
    world = World(path)

    def fault(reached, context):
        if reached == phase:
            atomic_write(
                Path(evidence), json_bytes({"cut": phase, "context": context, "pid": os.getpid()})
            )
            os._exit(EXIT_CODE)  # Real process death: no finally blocks or in-memory rollback.

    world.fault_hook = fault
    act(world, *command(kind))
    raise AssertionError("The preregistered fault cut was not reached")


def finish(world, kind):
    if kind == "submit":
        act(world, "analyst", "wait", {"ticks": 2}, "finish-review")
    errors = world.recover()["pending_event_errors"]
    if errors:
        raise AssertionError(errors)


def file_inventory(world):
    state = world.store.load()
    versions = {}
    mirrors = {}
    for aid, artifact in state["artifacts"].items():
        for vid in artifact["versions"]:
            versions[f"{aid}/{vid}"] = digest(world.store.version_path(artifact, vid).read_bytes())
        mirrors[aid] = digest(world.store.current_path(artifact).read_bytes())
    return {"versions": versions, "mirrors": mirrors}


def normalize(state):
    """Keep identities and all business/observation records; remove diagnostics only."""
    result = copy.deepcopy(state)

    def walk(value):
        if isinstance(value, dict):
            for key in tuple(value):
                if key in {"wall_seconds", "state_digests"}:
                    del value[key]
                else:
                    walk(value[key])
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result


def run(output, workers=4):
    root = Path(output).resolve()
    if root.exists():
        raise ValueError("Output must be a new directory")
    root.mkdir(parents=True)
    identity = code_identity()
    protocol = {
        "seed": SEED,
        "matrix": MATRIX,
        "fault_case_count": 10,
        "control_count": 4,
        "process_exit_code": EXIT_CODE,
        "normalization": ["wall_seconds", "diagnostic state_digests"],
        "preserved": "all other state fields including identities, primary facts, projections, journal/results, actual observations; every immutable version and current mirror byte hash",
        "boundary": "one writer per isolated directory, real os._exit, existing JSON/immutable-version filesystem; not power loss, machine loss, distributed consensus or arbitrary plugin transactions",
        "expected_checks_per_fault": 6,
        "supplemental_exception_probe": {
            "cases": 1,
            "checks": 4,
            "reason": "Separate post-commit acknowledgement exception regression; not one of the ten os._exit cuts",
        },
        "scope": "one common trusted checkpoint per action family, copied byte-for-byte to control and fault worlds; stable command identities for new actions",
    }
    atomic_write(root / "protocol.json", json_bytes(protocol))
    bases, controls, responses = {}, {}, {}
    for kind in MATRIX:
        base = setup(root / f"{kind}-checkpoint", kind)
        bases[kind] = base.store.root
        target = root / f"{kind}-control"
        shutil.copytree(base.store.root, target, ignore=shutil.ignore_patterns("world.lock"))
        world = World(target)
        responses[kind] = act(world, *command(kind))
        finish(world, kind)
        validate_committed_prefix(world.store.load())
        controls[kind] = {
            "state": normalize(world.store.load()),
            "files": file_inventory(world),
            "result": responses[kind],
            "world": str(target),
        }
        atomic_write(target / "comparison.json", json_bytes(controls[kind]))

    def trial(job):
        kind, phase = job
        target = root / f"{kind}-{phase}"
        shutil.copytree(bases[kind], target, ignore=shutil.ignore_patterns("world.lock"))
        evidence = target / "fault-reached.json"
        checks = []

        def check(name, condition):
            checks.append({"name": name, "passed": bool(condition)})
            if not condition:
                raise AssertionError(name)

        try:
            execution = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--child",
                    str(target),
                    "--kind",
                    kind,
                    "--phase",
                    phase,
                    "--evidence",
                    str(evidence),
                ],
                capture_output=True,
                text=True,
            )
            check(
                "actual_process_cut_reached",
                execution.returncode == EXIT_CODE and evidence.exists(),
            )
            committed_before_resume = json.loads((target / "control/state.json").read_text())
            world = World(target)
            resumed_result = act(world, *command(kind))
            finish(world, kind)
            current = world.store.load()
            validate_committed_prefix(current)
            check("committed_prefix_consistent", True)
            check(
                "state_matches_uninterrupted_control", normalize(current) == controls[kind]["state"]
            )
            check(
                "immutable_and_materialized_bytes_match_control",
                file_inventory(world) == controls[kind]["files"],
            )
            check(
                "public_command_result_matches_control", resumed_result == controls[kind]["result"]
            )
            before_retry = copy.deepcopy(current)
            check(
                "second_retry_has_no_formal_effect",
                act(world, *command(kind)) == resumed_result and world.store.load() == before_retry,
            )
            error = None
            atomic_write(
                target / "comparison.json",
                json_bytes(
                    {
                        "state": normalize(current),
                        "files": file_inventory(world),
                        "result": resumed_result,
                    }
                ),
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            committed_before_resume = locals().get("committed_before_resume", {})
        result = {
            "kind": kind,
            "phase": phase,
            "world": str(target),
            "checks": checks,
            "passed": error is None,
            "error": error,
            "process_output": {
                "stdout": execution.stdout,
                "stderr": execution.stderr,
                "exit_code": execution.returncode,
            },
            "reached_cut": json.loads(evidence.read_text()) if evidence.exists() else None,
            "committed_revision_before_resume": committed_before_resume.get("state_revision", 0),
        }
        atomic_write(target / "result.json", json_bytes(result))
        return result

    jobs = [(kind, phase) for kind, phases in MATRIX.items() for phase in phases]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(trial, jobs))
    supplement = {"kind": "post_commit_delivery_exception", "checks": []}
    try:
        world = World(
            compile_world(design(827, scenario="during_update"), root / "post-commit-exception")
        )

        def fail_ack(phase, context):
            if phase == "after_event_commit":
                raise ValueError("Injected acknowledgement failure after event commit")

        world.fault_hook = fail_ack
        arguments = {"cells": {"RecoveryProbe!A1": 1}}
        result = world.act(
            "analyst", "sheet_update", arguments, request_key="committed-before-ack-error"
        )
        supplement["checks"].append(
            {
                "name": "command_commit_distinct_from_ack_failure",
                "passed": result["ok"] and result["command_committed"],
            }
        )
        supplement["checks"].append(
            {
                "name": "event_reported_as_committed",
                "passed": not result.get("pending_event_errors")
                and result["event_delivery_errors"][0]["event_committed"],
            }
        )
        recovered = World(world.store.root)
        committed = recovered.store.load()
        validate_committed_prefix(committed)
        supplement["checks"].append(
            {
                "name": "committed_versions_still_reopen",
                "passed": committed["artifacts"]["basis"]["current_version"] == "v3"
                and committed["artifacts"]["scope"]["current_version"] == "v2",
            }
        )
        retried = recovered.act(
            "analyst", "sheet_update", arguments, request_key="committed-before-ack-error"
        )
        supplement["checks"].append(
            {
                "name": "retry_preserves_committed_formal_effects",
                "passed": recovered.store.load() == committed
                and retried == {k: v for k, v in result.items() if k != "event_delivery_errors"},
            }
        )
        supplement.update(
            world=str(world.store.root),
            command_result=result,
            retry_result=retried,
            files=file_inventory(recovered),
            passed=all(c["passed"] for c in supplement["checks"]),
        )
    except Exception as exc:
        supplement.update(passed=False, error=f"{type(exc).__name__}: {exc}")
    report = {
        "experiment": "bounded-single-writer-recovery",
        "supplemental_exception_probe": supplement,
        "protocol": protocol,
        "code_before": identity,
        "code_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "workers": workers,
        "model_calls": 0,
        "gpu_used": False,
        "case_count": len(results),
        "passed": sum(r["passed"] for r in results),
        "check_count": sum(len(r["checks"]) for r in results),
        "checks_passed": sum(c["passed"] for r in results for c in r["checks"]),
        "controls": {
            kind: {
                "world": data["world"],
                "state_digest": canonical_digest(data["state"]),
                "files": data["files"],
                "result": data["result"],
            }
            for kind, data in controls.items()
        },
        "results": results,
    }
    atomic_write(root / "report.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--child")
    parser.add_argument("--kind", choices=tuple(MATRIX))
    parser.add_argument("--phase")
    parser.add_argument("--evidence")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.kind, args.phase, args.evidence)
    else:
        report = run(args.output, args.workers)
        print(
            json.dumps(
                {
                    "cases": report["case_count"],
                    "passed": report["passed"],
                    "checks": report["check_count"],
                }
            )
        )
        raise SystemExit(
            0
            if report["passed"] == report["case_count"]
            and report["supplemental_exception_probe"]["passed"]
            else 1
        )
