"""N4 public-only procedural worker: four declared cases and separate unavailable probe."""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.public_worker import run_public_worker
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

CASES = ("existing", "published", "requestable", "missing")
VALUES = {"existing": 13, "published": 27, "requestable": 33, "unavailable": 41}
BASE_CHECKS = (
    "expected_outcome",
    "authentic_transcript",
    "advertised_tools_only",
    "only_public_port",
    "submitted_content_or_waiting_exit",
)
EXTRA_CHECKS = {
    "existing": ("json_source_read_and_adopted",),
    "published": ("published_v2_selected_instead_of_v3_draft", "xlsx_source_read"),
    "requestable": (
        "request_has_only_public_route_and_work",
        "actual_wait_and_resolved_condition",
        "initial_private_input_becomes_readable",
    ),
    "missing": ("missing_route_recorded_as_capability_gap", "no_fabricated_request_or_delivery"),
    "unavailable": (
        "request_has_only_public_route_and_work",
        "explicit_unavailable_condition",
        "unavailable_input_stays_private",
    ),
}
PROTOCOL = {
    "suite": "public-worker-N4-v0.7",
    "main_cases": list(CASES),
    "supplemental_cases": ["unavailable"],
    "checks": {case: BASE_CHECKS + EXTRA_CHECKS[case] for case in (*CASES, "unavailable")},
    "worker_interface": ["session.tools", "session.observe", "session.call"],
    "transcript": "Exact returns recorded at time of call, independently captured by a minimal port; no historical observation reconstruction",
    "inputs": "Work IDs, input alias, paths/cell, policies, references and values are obtained from public observations and exact reads",
    "independent_expected_scalars": VALUES,
    "worlds": "One independent single-writer world with two projects for each case",
    "limitations": [
        "Transparent finite procedural worker; no general planning or model capability claim",
        "No arbitrary filesystem, hidden world object, state or spec interface given to worker",
        "Missing route is a waiting exit and explicit capability gap, not a successful delivery",
        "Unavailable-route probe is separate from the four main cases",
    ],
}


def write_json(path, data):
    atomic_write(path, json_bytes(data))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def must(session, action, **arguments):
    response = session.call(action, **arguments)
    if not response.get("ok"):
        raise AssertionError((action, arguments, response))
    return response["result"]


def public_port(session):
    """An opaque object exposing just three methods; audit sink is external."""
    captured = []

    def record(kind, value):
        captured.append({"sequence": len(captured), "kind": kind, "value": copy.deepcopy(value)})

    class Port:
        __slots__ = ()

        def observe(self):
            result = session.observe()
            record("observation", result)
            return result

        def tools(self):
            result = session.tools()
            record("tools", result)
            return result

        def call(self, action, request_key=None, **arguments):
            result = session.call(action, request_key=request_key, **arguments)
            record(
                "tool_call",
                {
                    "action": action,
                    "arguments": arguments,
                    "request_key": request_key,
                    "response": result,
                },
            )
            return result

    return Port(), captured


def simple_package(pid, owner):
    return {
        "project_id": pid,
        "goal": "Finite publicly described handoff",
        "participants": [owner, "manager"],
        "objects": [],
        "adoptions": [],
        "works": [
            {
                "work_id": "work-1",
                "owner": owner,
                "approval_policy": "delivery_only",
                "deliverable_contract": {"min_files": 1, "max_files": 1},
            }
        ],
        "grants": [
            {"actor_id": owner, "power": p, "subject": "artifact"}
            for p in ("create_object", "adopt", "share", "publish")
        ],
        "provenance": {"kind": "synthetic", "source_evidence_refs": []},
    }


def setup(root, case):
    world = WorldCore.create(
        root,
        WorldSpec(
            "public-worker-" + case,
            {a: {} for a in ("alice", "bob", "manager")},
            applications=["files", "spreadsheets"],
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    manager = world.session("manager")
    a = simple_package("A", "alice")
    b = simple_package("B", "bob")
    alias = {
        "existing": "ledger-input",
        "published": "released-budget",
        "requestable": "requested-fact",
        "missing": "missing-fact",
        "unavailable": "unavailable-fact",
    }[case]
    check = {
        "kind": "json_matches_source_field",
        "path": ["result"],
        "reference_path": ["source_ref"],
        "adoption_alias": alias,
        "source_path": ["metrics", "amount"],
    }
    if case == "published":
        check.update(kind="json_matches_source_cell", sheet="Summary", cell="B3")
        check.pop("source_path")
    b["works"][0].update(
        requirements={"input_policy": "current_published" if case == "published" else "fixed"},
        deliverable_contract={
            "min_files": 1,
            "max_files": 1,
            "allowed_kinds": ["json"],
            "allowed_roles": ["report"],
            "required_fields": ["result", "source_ref"],
            "content_checks": [check],
        },
    )
    must(manager, "install_project", package=a)
    if case == "published":
        must(manager, "install_project", package=b)
        producer = world.session("alice", "A")
        source = must(
            producer,
            "create_object",
            alias="model",
            filename="model.xlsx",
            kind="xlsx",
            data={"cells": {"Summary!B1": 20, "Summary!B2": 6, "Summary!B3": "=B1-B2"}},
        )
        must(
            producer,
            "share",
            object_id=source["object_id"],
            version_id="v1",
            target_project="B",
            actor_ids=["bob", "manager"],
            follow_updates=True,
        )
        must(
            world.session("bob", "B"),
            "adopt",
            alias=alias,
            object_id=source["object_id"],
            version_id="v1",
            policy="current_published",
            work_ids=["work-1"],
        )
        must(producer, "sheet_update", alias="model", cells={"Summary!B1": 33})
        must(producer, "publish", alias="model", version_id="v2", target_projects=["B"])
        must(producer, "sheet_update", alias="model", cells={"Summary!B1": 999})
    else:
        if case != "missing":
            private = case in {"requestable", "unavailable"}
            b["objects"] = [
                {
                    "alias": alias,
                    "filename": alias + ".json",
                    "kind": "json",
                    "owner": "manager" if private else "bob",
                    "readers": ["manager"] if private else ["bob", "manager"],
                    "writers": ["manager"] if private else ["bob"],
                    "data": {"metrics": {"amount": VALUES[case]}},
                }
            ]
            if private:
                b["information_routes"] = [
                    {
                        "route_id": "request-" + alias,
                        "work_id": "work-1",
                        "provider": "manager",
                        "object_alias": alias,
                        "purpose": "evidence",
                        "delay": 3,
                        "availability": "unavailable" if case == "unavailable" else "available",
                    }
                ]
                b["grants"].append(
                    {
                        "actor_id": "manager",
                        "power": "provide",
                        "subject": "evidence",
                        "work_nodes": ["work-1"],
                        "object_ids": [alias],
                    }
                )
        must(manager, "install_project", package=b)
    return world, alias


def run_case(output, case):
    root = output / case
    root.mkdir(parents=True)
    checks, error, outcome, evaluation = [], None, None, None
    transcript_ref = None
    expected_names = BASE_CHECKS + EXTRA_CHECKS[case]

    def check(name, observed, expected=True):
        assert name in expected_names and not any(c["name"] == name for c in checks)
        checks.append(
            {
                "name": name,
                "observed": observed,
                "expected": expected,
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    try:
        world, alias = setup(root / "world", case)
        initial = world.store.load()
        write_json(root / "initial-state.json", initial)
        port, captured = public_port(world.session("bob", "B"))
        outcome = run_public_worker(port)
        transcript_ref = write_json(root / "transcript.json", outcome["transcript"])
        write_json(root / "captured-port-returns.json", captured)
        check(
            "expected_outcome",
            outcome["status"],
            "waiting" if case in {"missing", "unavailable"} else "submitted",
        )
        check("authentic_transcript", outcome["transcript"] == captured)
        defs = next(row["value"] for row in captured if row["kind"] == "tools")
        names = {item["name"] for item in defs}
        calls = [row["value"] for row in captured if row["kind"] == "tool_call"]
        observations = [row["value"] for row in captured if row["kind"] == "observation"]
        check("advertised_tools_only", all(call["action"] in names for call in calls))
        check(
            "only_public_port",
            sorted(name for name in dir(port) if not name.startswith("_")),
            ["call", "observe", "tools"],
        )
        final = world.store.load()
        if outcome["status"] == "submitted":
            evaluation = world.evaluate_submission(
                "B", outcome["work_id"], outcome["submission_id"]
            )
            write_json(root / "evaluation.json", evaluation)
            check(
                "submitted_content_or_waiting_exit",
                [
                    evaluation["passed"],
                    evaluation["checks"][0].get("actual"),
                    evaluation["checks"][0].get("expected"),
                ],
                [True, VALUES[case], VALUES[case]],
            )
        else:
            check(
                "submitted_content_or_waiting_exit",
                final["work_items"]["B::work-1"]["submissions"],
                [],
            )
        actions = [call["action"] for call in calls]
        if case == "existing":
            check("json_source_read_and_adopted", "read_object" in actions and "adopt" in actions)
        elif case == "published":
            check(
                "published_v2_selected_instead_of_v3_draft",
                outcome.get("source_reference", {}).get("version_id"),
                "v2",
            )
            check("xlsx_source_read", "sheet_read" in actions)
        elif case == "missing":
            check(
                "missing_route_recorded_as_capability_gap",
                outcome.get("capability_gap"),
                "missing_information_route",
            )
            check("no_fabricated_request_or_delivery", calls, [])
        else:
            requests = [call for call in calls if call["action"] == "request_information"]
            check(
                "request_has_only_public_route_and_work",
                len(requests) == 1 and set(requests[0]["arguments"]) == {"route_id", "work_id"},
            )
            conditions = final["condition_specs"].values()
            if case == "requestable":
                check(
                    "actual_wait_and_resolved_condition",
                    "wait" in actions and any(c["status"] == "resolved" for c in conditions),
                )
                check(
                    "initial_private_input_becomes_readable",
                    [
                        alias in observations[0]["workspaces"]["B"],
                        alias in observations[-1]["workspaces"]["B"],
                    ],
                    [False, True],
                )
            else:
                check(
                    "explicit_unavailable_condition",
                    any(c["status"] == "unavailable" for c in conditions),
                )
                check(
                    "unavailable_input_stays_private",
                    all(alias not in obs["workspaces"]["B"] for obs in observations),
                )
        write_json(root / "final-state.json", final)
    except Exception:
        error = traceback.format_exc()
    done = {check["name"] for check in checks}
    checks += [
        {"name": name, "passed": False, "not_executed": True}
        for name in expected_names
        if name not in done
    ]
    result = {
        "case": case,
        "checks": checks,
        "error": error,
        "outcome": {k: v for k, v in (outcome or {}).items() if k != "transcript"},
        "transcript": transcript_ref,
        "evaluation": evaluation,
        "passed": error is None and all(c["passed"] for c in checks),
    }
    write_json(root / "result.json", result)
    return result


def run(output, workers=4):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", PROTOCOL)
    before = code_identity()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda case: run_case(output, case), (*CASES, "unavailable")))
    main, supplement = results[:-1], results[-1]
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "cases": main,
        "supplemental_unavailable": supplement,
        "main_case_count": len(main),
        "main_pass_count": sum(r["passed"] for r in main),
        "main_check_count": sum(len(r["checks"]) for r in main),
        "main_checks_passed": sum(c["passed"] for r in main for c in r["checks"]),
        "model_calls": 0,
        "gpu_used": False,
        "training_performed": False,
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report = run(args.output, args.workers)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "main_case_count",
                    "main_pass_count",
                    "main_check_count",
                    "main_checks_passed",
                )
            }
        )
    )
    raise SystemExit(
        0
        if report["main_pass_count"] == len(CASES) and report["supplemental_unavailable"]["passed"]
        else 1
    )
