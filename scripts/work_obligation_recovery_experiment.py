"""Two representative v0.8 process cuts at binding and successor commit boundaries.

Each case copies one genuine checkpoint for its control and killed child. The
comparison normalizes only diagnostic wall_seconds and state_digests. This driver
does not rewrite command identities, business IDs, histories or observations.
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
from proworksim.core.adoption import binding_key
from proworksim.core.journal import validate_committed_prefix
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore
from maintenance_experiment import setup as maintenance_setup
from work_binding_experiment import Evidence, adopt, base, publish_v2, report

CUTS = {"binding_update": "after_command_commit", "maintenance_successor": "after_event_commit"}
EXIT_CODE = 73
CHECKS = (
    "checkpoint_copies_byte_identical",
    "real_process_cut_reached",
    "cut_has_expected_committed_prefix",
    "journal_prefix_consistent",
    "full_state_matches_control",
    "all_file_bytes_match_control",
    "public_result_matches_control",
    "actual_public_observations_match_control",
    "new_mechanism_effect_and_historical_context_preserved",
    "retry_has_no_formal_effect",
)
PROTOCOL = {
    "suite": "work-obligation-recovery-v0.8",
    "measurement_version": "actual-observations-v2",
    "observation_evidence": "WorldCore.observe is read-only: state.observations may be empty and is not used as evidence of historical observation coverage. Immediately capture three actual pre-cut role observations as control/recovery-prior-observations.json inside the checkpoint, copy them byte-for-byte, and require their nonempty work/version facts and unchanged hashes after control/recovery. New actual post-cut observations are compared separately.",
    "cuts": CUTS,
    "checks": CHECKS,
    "exit_code": EXIT_CODE,
    "checkpoint": "Each case has one actual two-project single-writer checkpoint; control and child copies match every file byte except absent advisory world.lock",
    "binding_update": "B's current-published exact-work binding v1 changes to released v2; a second work keeps fixed v1 and its accepted submission, with a genuine pending request and original observations retained",
    "maintenance_successor": "A's v2 publication commits, then its separate maintenance event creates one successor of accepted B work before os._exit; retry must not recreate the successor",
    "normalization": ["wall_seconds", "state_digests"],
    "compared": "All other full state fields including bindings, requests, responses, conditions, submissions, approvals, journal, recorded observations, messages and event history; all immutable and mirror byte hashes; command result and new actual observations",
    "legal_actions": ["adopt_version", "publish", "same fixed request-key retry", "observe"],
    "expected_revision_deltas": {"binding_update": 1, "maintenance_successor": 2},
    "failure_exit": "A child that misses the declared hook, any event error, inconsistent prefix or unequal actual observation fails the case; unexecuted checks stay explicit",
    "limitations": [
        "Two representative new mechanism cuts, not all tool/cut combinations",
        "Real process exit, not host power loss, concurrent writers or distributed consensus",
        "Controller fixture uses known contracts; continuing public-only worker evaluated separately",
        "No model/API/GPU/training and no re-run of unrelated legacy crash experiments",
    ],
}


def write_json(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def normalized(value):
    if isinstance(value, dict):
        return {
            key: normalized(child)
            for key, child in value.items()
            if key not in {"wall_seconds", "state_digests"}
        }
    if isinstance(value, list):
        return [normalized(child) for child in value]
    return value


def setup(root, kind):
    if kind == "maintenance_successor":
        world, _ = maintenance_setup(root / "world", "accepted", "maintenance")
        return world
    ev = Evidence("recovery-binding", root)
    source = base(ev, route=True)
    adopt(ev, source, policy="current_published")
    adopt(ev, source, work="B::other-work", policy="fixed")
    report(ev, source)
    ev.call("bob", "B", "submit", work_id="other-work", artifacts=["report"])
    ev.call("bob", "B", "request_information", route_id="data", work_id="work")
    publish_v2(ev)
    ev.observe("bob", "B")
    write_json(
        root / "setup-public-trace.json", {"calls": ev.calls, "observations": ev.observations}
    )
    return ev.world


def execute(world, kind):
    if kind == "binding_update":
        session, tool, arguments = (
            world.session("bob", "B"),
            "adopt_version",
            {"alias": "input", "work_id": "work", "version_id": "v2"},
        )
    else:
        session, tool, arguments = (
            world.session("alice", "A"),
            "publish",
            {"alias": "source", "version_id": "v2", "target_projects": ["A", "B"]},
        )
    result = session.call(tool, request_key="v08-recovery-" + kind, **arguments)
    if (
        not result.get("ok")
        or result.get("pending_event_errors")
        or result.get("event_delivery_errors")
    ):
        raise AssertionError(result)
    return result


def child(root, kind, evidence):
    world = WorldCore(root)

    def fault(phase, context):
        if phase == CUTS[kind]:
            write_json(evidence, {"phase": phase, "context": context, "pid": os.getpid()})
            os._exit(EXIT_CODE)

    world.fault_hook = fault
    execute(world, kind)
    raise AssertionError("Declared fault phase was not reached")


def tree_files(root):
    return {
        str(path.relative_to(root)): digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "world.lock"
    }


def inventory(world):
    versions, mirrors = {}, {}
    for aid, artifact in world.store.load()["artifacts"].items():
        for vid in artifact["versions"]:
            versions[aid + "/" + vid] = digest(world.store.version_path(artifact, vid).read_bytes())
        mirrors[aid] = digest(world.store.current_path(artifact).read_bytes())
    return {"versions": versions, "mirrors": mirrors}


def observations(world):
    return {
        actor + "/" + str(pid): world.session(actor, pid).observe()
        for actor, pid in (("alice", "A"), ("bob", "B"), ("manager", None))
    }


def mechanism_preserved(before, after, kind):
    all_original_versions = all(
        after["artifacts"][aid]["versions"][vid] == metadata
        for aid, artifact in before["artifacts"].items()
        for vid, metadata in artifact["versions"].items()
    )
    pending_request_preserved = before["requests"] == after["requests"]
    if kind == "binding_update":
        key = binding_key("B::work", "input")
        other_key = binding_key("B::other-work", "input")
        specific = (
            before["adoptions"][key]["version_id"] == "v1"
            and after["adoptions"][key]["version_id"] == "v2"
            and len(after["adoptions"][key]["history"])
            == len(before["adoptions"][key]["history"]) + 1
            and after["adoptions"][other_key] == before["adoptions"][other_key]
            and after["work_items"] == before["work_items"]
            and bool(before["requests"])
        )
    else:
        new_work = set(after["work_items"]) - set(before["work_items"])
        specific = (
            len(new_work) == 1
            and after["work_items"]["B::analysis"] == before["work_items"]["B::analysis"]
            and after["work_items"][next(iter(new_work))]["previous_obligation_id"] == "B::analysis"
            and after["adoptions"] == before["adoptions"]
            and after["work_replacements"] == before["work_replacements"]
        )
    return all_original_versions and pending_request_preserved and specific


def run_case(output, kind):
    root = output / kind
    root.mkdir()
    checks, evidence, error, process_record = [], {}, None, None

    def check(name, value, observed=None):
        checks.append(
            {"name": name, "passed": bool(value), "observed": observed, "not_executed": False}
        )

    try:
        base_world = setup(root / "checkpoint", kind)
        actual_prior_observations = observations(base_world)
        prior_relative = Path("control/recovery-prior-observations.json")
        evidence["actual_checkpoint_observations"] = write_json(
            base_world.store.root / prior_relative, actual_prior_observations
        )
        prior_observation_bytes = (base_world.store.root / prior_relative).read_bytes()
        base_state, checkpoint_files = base_world.store.load(), tree_files(base_world.store.root)
        evidence["checkpoint_state"] = write_json(root / "checkpoint-state.json", base_state)
        control_root, fault_root = root / "control-world", root / "fault-world"
        for destination in (control_root, fault_root):
            shutil.copytree(
                base_world.store.root, destination, ignore=shutil.ignore_patterns("world.lock")
            )
        check(
            "checkpoint_copies_byte_identical",
            tree_files(control_root) == tree_files(fault_root) == checkpoint_files,
        )
        control = WorldCore(control_root)
        expected_result = execute(control, kind)
        expected_observations = observations(control)
        expected_state, expected_files = normalized(control.store.load()), inventory(control)
        evidence["control"] = write_json(
            root / "control.json",
            {
                "state": expected_state,
                "files": expected_files,
                "result": expected_result,
                "observations": expected_observations,
            },
        )
        reached = root / "fault-reached.json"
        process = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child",
                str(fault_root),
                "--kind",
                kind,
                "--evidence",
                str(reached),
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
        process_record = {
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        check(
            "real_process_cut_reached",
            process.returncode == EXIT_CODE and reached.exists(),
            process_record,
        )
        crashed = json.loads((fault_root / "control/state.json").read_text())
        evidence["before_resume"] = write_json(root / "before-resume-state.json", crashed)
        check(
            "cut_has_expected_committed_prefix",
            crashed["state_revision"]
            == base_state["state_revision"] + PROTOCOL["expected_revision_deltas"][kind],
            {"base": base_state["state_revision"], "cut": crashed["state_revision"]},
        )
        world = WorldCore(fault_root)
        recovered_result = execute(world, kind)
        actual_observations = observations(world)
        current = world.store.load()
        validate_committed_prefix(current)
        check("journal_prefix_consistent", True)
        check("full_state_matches_control", normalized(current) == expected_state)
        actual_files = inventory(world)
        check("all_file_bytes_match_control", actual_files == expected_files)
        check(
            "public_result_matches_control",
            normalized(recovered_result) == normalized(expected_result),
        )
        check(
            "actual_public_observations_match_control", actual_observations == expected_observations
        )
        prior_work = actual_prior_observations.get("bob/B", {}).get("work_items", {})
        prior_context_valid = all(
            value.get("actor_id") and value.get("work_items")
            for value in actual_prior_observations.values()
        ) and (
            prior_work.get("B::work", {}).get("status") == "blocked"
            and prior_work["B::work"]["requirement_version"] == 1
            and prior_work.get("B::other-work", {}).get("status") == "accepted"
            if kind == "binding_update"
            else prior_work.get("B::analysis", {}).get("status") == "accepted"
            and prior_work["B::analysis"]["requirement_version"] == 1
        )
        prior_observations_retained = (
            (control_root / prior_relative).read_bytes() == prior_observation_bytes
            and (fault_root / prior_relative).read_bytes() == prior_observation_bytes
            and digest((control_root / prior_relative).read_bytes())
            == evidence["actual_checkpoint_observations"]["sha256"]
            and digest((fault_root / prior_relative).read_bytes())
            == evidence["actual_checkpoint_observations"]["sha256"]
        )
        evidence["checkpoint_observation_retention"] = {
            "nonempty_actual_work_context": prior_context_valid,
            "control_sha256": digest((control_root / prior_relative).read_bytes()),
            "recovered_sha256": digest((fault_root / prior_relative).read_bytes()),
            "bytes_retained": prior_observations_retained,
            "state_observations_count_not_used_as_coverage": len(
                base_state.get("observations", [])
            ),
        }
        check(
            "new_mechanism_effect_and_historical_context_preserved",
            mechanism_preserved(base_state, current, kind)
            and prior_context_valid
            and prior_observations_retained,
            evidence["checkpoint_observation_retention"],
        )
        retry_before = copy.deepcopy(current)
        retry = execute(world, kind)
        check(
            "retry_has_no_formal_effect",
            retry == recovered_result
            and world.store.load() == retry_before
            and inventory(world) == actual_files,
        )
        evidence["recovered"] = write_json(
            root / "recovered.json",
            {
                "state": normalized(current),
                "files": actual_files,
                "result": recovered_result,
                "observations": actual_observations,
            },
        )
        evidence["fault_reached"] = json.loads(reached.read_text()) if reached.exists() else None
    except Exception:
        error = traceback.format_exc()
    completed = {check["name"] for check in checks}
    checks.extend(
        {"name": name, "passed": False, "not_executed": True}
        for name in CHECKS
        if name not in completed
    )
    result = {
        "kind": kind,
        "phase": CUTS[kind],
        "checks": checks,
        "evidence": evidence,
        "process": process_record,
        "error": error,
        "passed": error is None and all(check["passed"] for check in checks),
    }
    write_json(root / "result.json", result)
    return result


def run(output, workers=2):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", PROTOCOL)
    before = code_identity()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        cases = list(pool.map(lambda kind: run_case(output, kind), CUTS))
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "cases": cases,
        "case_count": len(cases),
        "cases_passed": sum(case["passed"] for case in cases),
        "check_count": sum(len(case["checks"]) for case in cases),
        "checks_passed": sum(check["passed"] for case in cases for check in case["checks"]),
        "not_executed": sum(check["not_executed"] for case in cases for check in case["checks"]),
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
                    key: report[key]
                    for key in (
                        "case_count",
                        "cases_passed",
                        "check_count",
                        "checks_passed",
                        "not_executed",
                    )
                }
            )
        )
        raise SystemExit(0 if report["cases_passed"] == len(CUTS) else 1)
