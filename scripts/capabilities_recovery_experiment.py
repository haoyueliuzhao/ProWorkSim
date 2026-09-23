"""N4 recovery: two real process cuts for XLSX write and explicit publication.

Control and crash cases are copied from one byte-identical committed checkpoint.
Only diagnostic wall_seconds/state_digests are normalized. All formal fields,
exact file hashes and actual observations are compared without ID remapping.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.journal import validate_committed_prefix
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

CUTS = {"sheet_update": "after_apply", "publish": "after_command_commit"}
CHECKS = (
    "real_process_cut_reached",
    "cut_has_expected_committed_prefix",
    "journal_prefix_consistent",
    "full_state_matches_control",
    "all_file_bytes_match_control",
    "public_result_matches_control",
    "actual_public_observations_match_control",
    "retry_has_no_formal_effect",
)
PROTOCOL = {
    "suite": "new-capabilities-recovery-N4-v0.7",
    "cuts": CUTS,
    "checks_per_cut": CHECKS,
    "exit_code": 73,
    "checkpoint": "One real two-project checkpoint copied without changing IDs or bytes",
    "normalized_fields": ["wall_seconds", "state_digests"],
    "preserved": "Every other state field including releases/shares/adoptions/journal; hashes of every immutable version and current mirror; actual role observations and public command results",
    "scope": "Two necessary new capability cuts only: XLSX bytes staged after Apply before commit; explicit release committed before return. Single writer, os._exit process interruption, no power-loss/distributed/arbitrary-plugin claim",
    "separate_from_worker_denominator": True,
}


def write_json(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def must(session, action, **arguments):
    result = session.call(action, **arguments)
    if not result.get("ok"):
        raise AssertionError(result)
    return result


def simple_package(pid, owner):
    return {
        "project_id": pid,
        "goal": "New-capability recovery fixture",
        "participants": [owner, "manager"],
        "objects": [],
        "works": [
            {
                "work_id": "work-1",
                "owner": owner,
                "approval_policy": "delivery_only",
                "deliverable_contract": {"min_files": 1, "max_files": 1},
            }
        ],
        "grants": [
            {"actor_id": owner, "power": power, "subject": "artifact"}
            for power in ("create_object", "adopt", "share", "publish")
        ],
        "provenance": {"kind": "synthetic", "source_evidence_refs": []},
    }


def setup(root):
    world = WorldCore.create(
        root,
        WorldSpec(
            "capabilities-recovery",
            {a: {} for a in ("alice", "bob", "manager")},
            applications=["files", "spreadsheets"],
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    manager = world.session("manager")
    for pid, owner in (("A", "alice"), ("B", "bob")):
        must(manager, "install_project", package=simple_package(pid, owner))
    alice = world.session("alice", "A")
    created = must(
        alice,
        "create_object",
        alias="model",
        filename="model.xlsx",
        kind="xlsx",
        data={
            "cells": {
                "Results!A1": 11,
                "Results!A2": 4,
                "Results!A3": "=A1-A2",
                "Diagnostic!A1": "=1/0",
            }
        },
    )["result"]
    must(
        alice,
        "share",
        object_id=created["object_id"],
        version_id="v1",
        target_project="B",
        actor_ids=["bob", "manager"],
        follow_updates=True,
    )
    must(alice, "publish", alias="model", version_id="v1", target_projects=["B"])
    must(
        world.session("bob", "B"),
        "adopt",
        alias="input",
        object_id=created["object_id"],
        version_id="v1",
        policy="current_published",
        work_ids=["work-1"],
    )
    must(alice, "sheet_update", alias="model", cells={"Results!A1": 15})
    world.session("bob", "B").observe()
    return world


def execute(world, kind):
    arguments = (
        {"alias": "model", "cells": {"Results!A1": 22, "Results!A3": "=SUM(A1,-A2)"}}
        if kind == "sheet_update"
        else {"alias": "model", "version_id": "v2", "target_projects": ["B"]}
    )
    return must(world.session("alice", "A"), kind, request_key="N4-recovery-" + kind, **arguments)


def child(root, kind, evidence):
    world = WorldCore(root)

    def fault(phase, context):
        if phase == CUTS[kind]:
            write_json(evidence, {"phase": phase, "context": context, "pid": os.getpid()})
            os._exit(73)

    world.fault_hook = fault
    execute(world, kind)
    raise AssertionError("Fault phase was not reached")


def normalized(value):
    value = copy.deepcopy(value)

    def visit(node):
        if isinstance(node, dict):
            for key in tuple(node):
                if key in {"wall_seconds", "state_digests"}:
                    del node[key]
                else:
                    visit(node[key])
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return value


def inventory(world):
    state = world.store.load()
    versions, mirrors = {}, {}
    for aid, artifact in state["artifacts"].items():
        for vid in artifact["versions"]:
            versions[aid + "/" + vid] = digest(world.store.version_path(artifact, vid).read_bytes())
        mirrors[aid] = digest(world.store.current_path(artifact).read_bytes())
    return {"versions": versions, "mirrors": mirrors}


def observations(world):
    return {
        actor + "/" + str(pid): world.session(actor, pid).observe()
        for actor, pid in (("alice", "A"), ("bob", "B"), ("manager", None))
    }


def run_case(output, base_root, kind):
    control_root, fault_root = output / (kind + "-control"), output / (kind + "-fault")
    for destination in (control_root, fault_root):
        shutil.copytree(base_root, destination, ignore=shutil.ignore_patterns("world.lock"))
    base_state = json.loads((base_root / "control/state.json").read_text())
    control = WorldCore(control_root)
    result = execute(control, kind)
    expected = {
        "state": normalized(control.store.load()),
        "files": inventory(control),
        "result": result,
        "observations": observations(control),
    }
    control_ref = write_json(output / (kind + "-control.json"), expected)
    evidence = output / (kind + "-fault-reached.json")
    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            str(fault_root),
            "--kind",
            kind,
            "--evidence",
            str(evidence),
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")
            + os.pathsep
            + str(Path(__file__).resolve().parents[1]),
        },
    )
    checks, error, compared = [], None, None

    def check(name, value):
        checks.append({"name": name, "passed": bool(value), "not_executed": False})

    try:
        check("real_process_cut_reached", process.returncode == 73 and evidence.exists())
        before_resume = json.loads((fault_root / "control/state.json").read_text())
        write_json(output / (kind + "-before-resume-state.json"), before_resume)
        expected_revision = base_state["state_revision"] + (kind == "publish")
        check(
            "cut_has_expected_committed_prefix",
            before_resume["state_revision"] == expected_revision,
        )
        world = WorldCore(fault_root)
        recovered = execute(world, kind)
        current = world.store.load()
        validate_committed_prefix(current)
        check("journal_prefix_consistent", True)
        check("full_state_matches_control", normalized(current) == expected["state"])
        files = inventory(world)
        check("all_file_bytes_match_control", files == expected["files"])
        check("public_result_matches_control", recovered == expected["result"])
        actual_observations = observations(world)
        check(
            "actual_public_observations_match_control",
            actual_observations == expected["observations"],
        )
        before_retry = world.store.load()
        check(
            "retry_has_no_formal_effect",
            execute(world, kind) == recovered
            and before_retry == world.store.load()
            and files == inventory(world),
        )
        compared = write_json(
            output / (kind + "-recovered.json"),
            {
                "state": normalized(current),
                "files": files,
                "result": recovered,
                "observations": actual_observations,
                "quarantined_versions": sorted(
                    str(p.relative_to(fault_root))
                    for p in (fault_root / "control/uncommitted").rglob("*")
                    if p.is_file()
                ),
            },
        )
    except Exception:
        error = traceback.format_exc()
    completed = {c["name"] for c in checks}
    checks += [
        {"name": name, "passed": False, "not_executed": True}
        for name in CHECKS
        if name not in completed
    ]
    return {
        "kind": kind,
        "phase": CUTS[kind],
        "checks": checks,
        "error": error,
        "process": {
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        },
        "control": control_ref,
        "recovered": compared,
        "fault_reached": json.loads(evidence.read_text()) if evidence.exists() else None,
        "passed": error is None and all(c["passed"] for c in checks),
    }


def run(output, workers=2):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", PROTOCOL)
    before = code_identity()
    base = setup(output / "checkpoint")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        cases = list(pool.map(lambda kind: run_case(output, base.store.root, kind), CUTS))
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "cases": cases,
        "case_count": len(cases),
        "cases_passed": sum(c["passed"] for c in cases),
        "check_count": sum(len(c["checks"]) for c in cases),
        "checks_passed": sum(item["passed"] for c in cases for item in c["checks"]),
        "model_calls": 0,
        "gpu_used": False,
        "training_performed": False,
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--kind", choices=tuple(CUTS))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.kind, args.evidence)
    else:
        report = run(args.output, args.workers)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("case_count", "cases_passed", "check_count", "checks_passed")
                }
            )
        )
        raise SystemExit(0 if report["cases_passed"] == len(CUTS) else 1)
