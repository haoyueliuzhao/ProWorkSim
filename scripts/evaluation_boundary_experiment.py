"""R0: actual public-session deliveries, fixed source bytes, read-only assessment.

Runs against the installed source, including a full archived v0.9 PYTHONPATH.
Fault injection is an explicitly trusted measurement action, never worker input.
"""

import argparse
import copy
import hashlib
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.domains import reconciliation
from proworksim.storage import digest
from proworksim.templates.reconciliation import literal_truth, package
from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.world_core import WorldCore

CASES = {
    "normal": "pass",
    "business_error": "content_failure",
    "target_null": "structure_failure",
    "rows_null": "structure_failure",
    "row_null": "structure_failure",
    "key_nested": "structure_failure",
    "evidence_null": "structure_failure",
    "evidence_entry_null": "structure_failure",
    "summary_null": "structure_failure",
    "unresolved_nested": "structure_failure",
    "source_unavailable": "source_unavailable",
    "unassessed": "unassessed",
    "internal_error": "evaluator_error",
    "internal_type_error": "evaluator_error",
}
CHECKS = (
    "real_session_delivery",
    "exact_sources_bound_and_read",
    "correct_status",
    "truth_or_fault_distinguished",
    "repeated_assessment_equal",
    "business_facts_unchanged",
    "source_and_delivery_bytes_unchanged",
)
PROTOCOL = {
    "suite": "evaluation-boundary-R0-v0.10",
    "cases": CASES,
    "checks_per_case": CHECKS,
    "planned_checks": len(CASES) * len(CHECKS),
    "faults": "source_unavailable redirects one read-only exact source path; internal errors replace the domain evaluator with a raising function only during evaluation",
    "scope": "No policy receives independent evaluation; all deliveries use real read/adopt/write/submit sessions. Null source-value rows in normal case remain legitimate explicit unknowns, not errors.",
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def public_port(session, capture):
    class Port:
        __slots__ = ()

        def tools(self):
            value = session.tools()
            capture.append({"kind": "tools", "value": copy.deepcopy(value)})
            return value

        def observe(self):
            value = session.observe()
            capture.append({"kind": "observation", "value": copy.deepcopy(value)})
            return value

        def call(self, action, **arguments):
            value = session.call(action, **arguments)
            capture.append(
                {
                    "kind": "call",
                    "action": action,
                    "arguments": copy.deepcopy(arguments),
                    "response": copy.deepcopy(value),
                }
            )
            return value

    return Port()


def run_case(name, output):
    directory = Path(output) / name
    directory.mkdir(parents=True, exist_ok=False)
    capture, controller, checks, evaluations = [], [], [], []
    result = {
        "case": name,
        "expected_status": CASES[name],
        "checks": checks,
        "evaluations": evaluations,
        "construction_error": None,
    }
    world = None
    try:
        world = WorldCore.create(
            directory / "world",
            WorldSpec(
                world_id="R0-" + name,
                actors={"analyst": {}, "reviewer": {}},
                bootstrap_grants=[
                    {"actor_id": "reviewer", "scope": "world", "power": "install_project"}
                ],
            ),
        )
        config = package(review=True)
        if name == "unassessed":
            config["works"][0]["deliverable_contract"]["content_checks"] = []
        installation = world.session("reviewer", None).call("install_project", package=config)
        controller.append({"kind": "declared_setup", "response": installation})
        assert installation["ok"], installation
        port = public_port(world.session("analyst", "A"), capture)
        if name != "unassessed":
            worker = ReconciliationWorker(port)
            delivery = worker.run("A::reconcile")
            assert delivery["status"] == "submitted", delivery
            data, sub = delivery["data"], delivery["submission"]
        else:
            # No evaluator contract exists. This is a declared controller-built
            # finite JSON delivery, not a claimed policy solution.
            refs = {}
            for alias in ("ledger", "statement", "definitions"):
                aid = port.observe()["workspaces"]["A"][alias]
                adopted = port.call(
                    "adopt",
                    alias=alias,
                    object_id=aid,
                    version_id="v1",
                    policy="fixed",
                    work_ids=["A::reconcile"],
                )
                assert adopted["ok"], adopted
                read = port.call(
                    "read_object", alias=alias, version_id="v1", work_id="A::reconcile"
                )
                assert read["ok"], read
                refs[alias] = {"object_id": aid, "version_id": "v1"}
            data = {
                "reconciliation": {"note": "No finite content target declared"},
                "sources": refs,
            }
            created = port.call(
                "create_object",
                alias="comparison",
                filename="comparison.json",
                kind="json",
                deliverable_role="reconciliation",
                data=data,
                dependencies=list(refs.values()),
                work_id="A::reconcile",
            )
            assert created["ok"], created
            submitted = port.call("submit", work_id="A::reconcile", artifacts=["comparison"])
            assert submitted["ok"], submitted
            sub = submitted["result"]
        data = copy.deepcopy(data)
        rows = data["reconciliation"].get("rows", [])
        if name == "business_error":
            next(row for row in rows if row["key"][1] == "cost")["right_value"] = 80
        elif name == "target_null":
            data["reconciliation"] = None
        elif name == "rows_null":
            data["reconciliation"]["rows"] = None
        elif name == "row_null":
            data["reconciliation"]["rows"] = [None]
        elif name == "key_nested":
            rows[0]["key"] = [{}, []]
        elif name == "evidence_null":
            rows[0]["evidence"] = None
        elif name == "evidence_entry_null":
            rows[0]["evidence"] = [None]
        elif name == "summary_null":
            data["reconciliation"]["summary"] = None
        elif name == "unresolved_nested":
            data["reconciliation"]["unresolved"] = [[{}, "x"]]
        if name not in {
            "normal",
            "source_unavailable",
            "internal_error",
            "internal_type_error",
            "unassessed",
        }:
            for action, arguments in (
                (
                    "withdraw",
                    {
                        "work_id": "A::reconcile",
                        "submission_id": sub["submission_id"],
                        "reason": "Declared malformed or business-negative delivery",
                    },
                ),
                (
                    "write_object",
                    {
                        "alias": "comparison",
                        "work_id": "A::reconcile",
                        "data": data,
                        "dependencies": list(data["sources"].values()),
                    },
                ),
                ("submit", {"work_id": "A::reconcile", "artifacts": ["comparison"]}),
            ):
                value = port.call(action, **arguments)
                assert value["ok"], value
                if action == "submit":
                    sub = value["result"]
        before = copy.deepcopy(world.store.load())
        paths = [
            world.store.version_path(obj, vid)
            for obj in before["artifacts"].values()
            for vid in obj["versions"]
        ]
        hashes = {str(path): digest(path.read_bytes()) for path in paths}
        immutable_sub = next(
            s
            for s in before["work_items"]["A::reconcile"]["submissions"]
            if s["submission_id"] == sub["submission_id"]
        )
        write_json(directory / "submitted.json", data)
        write_json(directory / "submission.json", immutable_sub)
        write_json(
            directory / "sources.json",
            {
                alias: {
                    "reference": ref,
                    "content": json.loads(
                        world.store.version_path(
                            before["artifacts"][ref["object_id"]], ref["version_id"]
                        ).read_bytes()
                    ),
                }
                for alias, ref in data["sources"].items()
            },
        )

        def evaluate():
            try:
                return world.evaluate_submission("A", "A::reconcile", sub["submission_id"])
            except Exception as exc:
                return {
                    "escaped_exception": type(exc).__name__,
                    "reason": str(exc),
                    "traceback": traceback.format_exc(),
                }

        if name in {"internal_error", "internal_type_error"}:
            fault = RuntimeError if name == "internal_error" else TypeError
            controller.append(
                {
                    "kind": "evaluation_fault_injection",
                    "fault": fault.__name__,
                    "boundary": "domain.evaluate_check",
                    "world_mutation": False,
                }
            )

            def fail(*args, **kwargs):
                raise fault("Declared evaluator-internal defect, unrelated to delivered arithmetic")

            with patch.object(reconciliation, "evaluate_check", fail):
                evaluations.extend([evaluate(), evaluate()])
        elif name == "source_unavailable":
            actual = world.store.version_path
            unavailable = data["sources"]["ledger"]["object_id"]
            controller.append(
                {
                    "kind": "read_only_storage_outage",
                    "object_id": unavailable,
                    "world_mutation": False,
                }
            )

            def missing(obj, vid):
                return (
                    directory / "deliberately-unavailable-source.json"
                    if obj["artifact_id"] == unavailable
                    else actual(obj, vid)
                )

            with patch.object(world.store, "version_path", missing):
                evaluations.extend([evaluate(), evaluate()])
        else:
            evaluations.extend([evaluate(), evaluate()])
        after = world.store.load()
        truth = None
        if name == "normal":
            actual_truth = {
                row["key"][1]: {
                    key: row[key] for key in ("status", "left_value", "right_value", "delta")
                }
                for row in rows
            }
            truth = (
                actual_truth == literal_truth() and actual_truth["unknown"]["left_value"] is None
            )
        elif name.startswith("internal_"):
            value = evaluations[0]
            truth = (
                value.get("attribution")
                == "evaluation_implementation_or_unclassified_internal_failure"
                and not value.get("passed")
                and len(value.get("read_set", [])) == 4
                and value.get("interrupted_check", {}).get("kind") == "reconciliation_table"
            )
        else:
            truth = evaluations[0].get("status") == CASES[name] and not evaluations[0].get("passed")
        actuals = {
            "real_session_delivery": bool(sub.get("submission_id"))
            and all(r["response"]["ok"] for r in capture if r["kind"] == "call"),
            "exact_sources_bound_and_read": len(immutable_sub["adoption_snapshot"]) == 3
            and sum(r["kind"] == "call" and r["action"] == "read_object" for r in capture) >= 3,
            "correct_status": evaluations[0].get("status") == CASES[name],
            "truth_or_fault_distinguished": truth,
            "repeated_assessment_equal": evaluations[0] == evaluations[1],
            "business_facts_unchanged": before == after,
            "source_and_delivery_bytes_unchanged": hashes
            == {str(path): digest(path.read_bytes()) for path in paths},
        }
        checks.extend(
            {
                "name": check,
                "passed": actuals[check],
                "actual": actuals[check],
                "expected": True,
                "not_executed": False,
            }
            for check in CHECKS
        )
        result["file_hashes"] = hashes
    except Exception:
        result["construction_error"] = traceback.format_exc()
    for check in CHECKS:
        if check not in {item["name"] for item in checks}:
            checks.append({"name": check, "passed": False, "not_executed": True})
    result.update(
        passed=all(check["passed"] for check in checks),
        passed_checks=sum(check["passed"] for check in checks),
        total_checks=len(CHECKS),
        not_executed=sum(check["not_executed"] for check in checks),
    )
    write_json(directory / "public-capture.json", capture)
    write_json(directory / "controller-actions.json", controller)
    write_json(directory / "report.json", result)
    return result


def run(output, workers=4, cases=tuple(CASES)):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    # Monkeypatch-based fault cases are isolated from concurrent domain reads.
    ordinary = [name for name in cases if name not in {"internal_error", "internal_type_error"}]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda name: run_case(name, output), ordinary))
    results.extend(
        run_case(name, output)
        for name in cases
        if name in {"internal_error", "internal_type_error"}
    )
    result = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": results,
        "passed": all(case["passed"] for case in results),
        "passed_checks": sum(case["passed_checks"] for case in results),
        "total_checks": sum(case["total_checks"] for case in results),
        "not_executed": sum(case["not_executed"] for case in results),
    }
    write_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=list(CASES))
    args = parser.parse_args()
    report = run(args.output, args.workers, args.cases)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("passed", "passed_checks", "total_checks", "not_executed")
            }
        )
    )
    raise SystemExit(0 if report["passed"] else 1)
