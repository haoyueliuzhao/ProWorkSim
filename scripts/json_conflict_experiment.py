"""P0: explicit JSON truth cases through actual bound project sessions.

This same standalone script can run with a complete archived v0.7 source tree.
No state fixtures, evaluator monkeypatches, formula engine or model are used.
"""

import argparse
import copy
import hashlib
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import proworksim.domains.work_product as evaluator
from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, json_bytes
from proworksim.world_core import WorldCore

CASES = {
    "nested_true_one": {
        "source": 1,
        "values": [True, 1],
        "conflicts": ["metrics"],
        "passed": False,
    },
    "nested_false_zero": {
        "source": 0,
        "values": [False, 0],
        "conflicts": ["metrics"],
        "passed": False,
    },
    "equal_nested_numeric": {"source": 6, "values": [6, 6.0], "conflicts": [], "passed": True},
    "different_nested_numeric": {
        "source": 6,
        "values": [6, 7],
        "conflicts": ["metrics"],
        "passed": False,
    },
    "array_boolean_numeric": {
        "source": [1],
        "values": [[True], [1]],
        "conflicts": ["metrics"],
        "passed": False,
    },
    "equal_nested_arrays": {
        "source": [{"rate": [1, 2]}],
        "values": [[{"rate": [1, 2]}], [{"rate": [1.0, 2]}]],
        "conflicts": [],
        "passed": True,
    },
    "array_order_differs": {
        "source": [1, 2],
        "values": [[1, 2], [2, 1]],
        "conflicts": ["metrics"],
        "passed": False,
    },
    "single_file": {"source": 6, "values": [6], "conflicts": [], "passed": True},
    "split_delivery": {
        "source": 6,
        "values": [6],
        "layout": "split",
        "conflicts": [],
        "passed": True,
    },
}
PROTOCOL = {
    "suite": "json-conflicts-P0-v0.8",
    "cases": CASES,
    "expected_origin": "Literal values and verdicts declared in CASES before execution; no UUT equality or formula engine generates truth",
    "allowed_actions": [
        "install_project",
        "create_object",
        "write_object",
        "share",
        "publish",
        "adopt",
        "submit",
    ],
    "construction": "Each branch creates one WorldCore and A/B projects; A source is genuinely written to v2, shared and published; B uses a fixed exact v2 binding. Every contributing JSON declares the same exact source dependency.",
    "orders": "Two-file cases create both files in the same order then submit forward or reverse in separate worlds. Single-file case runs once.",
    "alternative_paths": "Identical overlapping fields and disjoint top-level split delivery are legal; no deep merge or selecting whichever file is correct",
    "rejections": "Conflicting top-level values must fail even when one supplied value equals the reference. No environment or access rejection is expected.",
    "comparison": "Explicit expected conflict keys, explicit expected passed, real fixed source/submission/dependency binding, unchanged state and byte hashes; paired evaluations compare verdicts/conflict keys and contract-check diagnostics, excluding read-set enumeration order and identity-bearing binding_files.",
    "numeric_policy": "Finite int/float numerical equivalence; no bool/number equivalence, tolerance, array reordering or recursive object merging",
    "limitations": [
        "One world and two projects per case/order; single writer",
        "Finite declared JSON content cases, no professional-quality inference",
        "No API, GPU, training, XLSX or new recovery cuts in P0",
    ],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    atomic_write(path, json_bytes(value))


def package(pid):
    owner = "alice" if pid == "A" else "bob"
    return {
        "project_id": pid,
        "goal": "Explicit finite nested JSON conflict protocol",
        "participants": ["alice", "bob", "manager"],
        "objects": [],
        "works": [
            {
                "work_id": "work-1",
                "owner": owner,
                "goal": "Deliver exact nested source value",
                "approval_policy": "delivery_only",
                "purpose": "delivery",
                "requirement_dimension": "requirements",
                "deliverable_contract": {
                    "min_files": 1,
                    "max_files": 2,
                    "allowed_roles": ["report"],
                    "allowed_kinds": ["json"],
                    "required_fields": ["metrics", "source_ref"],
                    "content_checks": [
                        {
                            "kind": "json_matches_source_field",
                            "path": ["metrics", "margin"],
                            "reference_path": ["source_ref"],
                            "source_path": ["rate"],
                            "adoption_alias": "input",
                        }
                    ],
                },
            }
        ],
        "grants": [
            {"actor_id": owner, "power": power, "subject": "artifact"}
            for power in ("create_object", "share", "publish", "adopt")
        ],
        "provenance": {
            "kind": "synthetic",
            "source_evidence_refs": [],
            "note": "Preregistered literal truth; not a professional trace",
        },
        "close_policy": {"pending_obligations": "retain"},
    }


def files(world):
    result = {}
    for aid, artifact in world.store.load()["artifacts"].items():
        for vid in artifact["versions"]:
            result[aid + "@" + vid] = sha(world.store.version_path(artifact, vid))
        result[aid + "@mirror"] = sha(world.store.current_path(artifact))
    return result


def comparable(result):
    checks = copy.deepcopy(result["checks"])
    for check in checks:
        check.pop("binding_files", None)
    return {
        "passed": result["passed"],
        "conflicting_fields": result["conflicting_fields"],
        "checks": checks,
        "errors": result["errors"],
        "missing_fields": result["missing_fields"],
    }


def run_branch(output, name, reverse=False):
    case = CASES[name]
    output.mkdir(parents=True, exist_ok=False)
    calls, checks = [], []
    record = {
        "case": name,
        "order": "reverse" if reverse else "forward",
        "world_root": str(output / "world"),
        "calls": calls,
        "checks": checks,
        "error": None,
    }

    def call(session, action, **arguments):
        response = session.call(action, **arguments)
        calls.append(
            {
                "actor": session.actor_id,
                "project": session.project_id,
                "tool": action,
                "arguments": copy.deepcopy(arguments),
                "response": copy.deepcopy(response),
            }
        )
        if not response.get("ok"):
            raise AssertionError(str(calls[-1]))
        return response["result"]

    def check(name, actual, expected):
        checks.append(
            {"name": name, "actual": actual, "expected": expected, "passed": actual == expected}
        )

    try:
        world = WorldCore.create(
            output / "world",
            WorldSpec(
                world_id="json-conflicts-P0",
                actors={actor: {} for actor in ("alice", "bob", "manager")},
                applications=["files"],
                publication_policy="explicit",
                bootstrap_grants=[
                    {"actor_id": "manager", "scope": "world", "power": "install_project"}
                ],
            ),
        )
        admin = world.session("manager")
        for pid in ("A", "B"):
            call(admin, "install_project", package=package(pid))
        a, b = world.session("alice", "A"), world.session("bob", "B")
        call(
            a,
            "create_object",
            alias="source",
            filename="source.json",
            kind="json",
            data={"rate": None},
        )
        source = call(a, "write_object", alias="source", data={"rate": case["source"]})
        ref = {
            "object_id": source.get("object_id", source.get("artifact_id")),
            "version_id": source["version_id"],
        }
        call(a, "share", **ref, target_project="B", actor_ids=["bob"], follow_updates=False)
        call(a, "publish", **ref, target_projects=["B"])
        call(b, "adopt", alias="input", **ref, policy="fixed", work_ids=["work-1"])
        payloads = [{"metrics": {"margin": value}, "source_ref": ref} for value in case["values"]]
        if case.get("layout") == "split":
            payloads = [{"metrics": {"margin": case["values"][0]}}, {"source_ref": ref}]
        aliases = []
        for index, data in enumerate(payloads):
            alias = f"report-{index + 1}"
            call(
                b,
                "create_object",
                alias=alias,
                filename=alias + ".json",
                kind="json",
                data=data,
                dependencies=[ref],
                deliverable_role="report",
            )
            aliases.append(alias)
        if reverse:
            aliases.reverse()
        submitted = call(b, "submit", work_id="work-1", artifacts=aliases)
        before, hashes = world.store.load(), files(world)
        result = world.evaluate_submission("B", "work-1", submitted["submission_id"])
        record.update(
            evaluation=result,
            source_ref=ref,
            file_hashes=hashes,
            comparison=comparable(result),
            submitted_aliases=aliases,
        )
        item = before["work_items"]["B::work-1"]
        sub = next(
            s for s in item["submissions"] if s["submission_id"] == submitted["submission_id"]
        )
        record["submission"] = sub
        snapshots = list(sub["adoption_snapshot"].values())
        bound = any(
            snapshot["object_id"] == ref["object_id"]
            and snapshot["version_id"] == "v2"
            and "B::work-1" in snapshot["work_ids"]
            for snapshot in snapshots
        )
        dependencies = all(
            any(
                dependency.get("object_id", dependency.get("artifact_id")) == ref["object_id"]
                and dependency["version_id"] == ref["version_id"]
                for dependency in before["artifacts"][aid]["versions"][vid]["derived_from"]
            )
            for aid, vid in sub["artifact_versions"].items()
        )
        check("literal_conflict_truth", result["conflicting_fields"], case["conflicts"])
        check("literal_pass_truth", result["passed"], case["passed"])
        check(
            "real_exact_binding_and_dependencies",
            bound and dependencies and ref["version_id"] == "v2",
            True,
        )
        check(
            "evaluation_preserves_state_and_all_bytes",
            before == world.store.load() and hashes == files(world),
            True,
        )
    except Exception as exc:
        record["error"] = {
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    record["not_executed_count"] = 4 - len(checks)
    record["passed"] = (
        record["error"] is None and len(checks) == 4 and all(check["passed"] for check in checks)
    )
    write(output / "report.json", record)
    return record


def run_experiment(output, workers=4, provenance_commit=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write(output / "protocol.json", PROTOCOL)
    before = code_identity()
    jobs = [
        (name, reverse)
        for name, case in CASES.items()
        for reverse in (
            [False] if len(case["values"]) == 1 and case.get("layout") != "split" else [False, True]
        )
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        branches = list(
            pool.map(
                lambda job: run_branch(
                    output / (job[0] + ("-reverse" if job[1] else "-forward")), *job
                ),
                jobs,
            )
        )
    pairs = []
    for name in CASES:
        pair = [branch for branch in branches if branch["case"] == name]
        if len(pair) == 2:
            pairs.append(
                {
                    "case": name,
                    "name": "order_independent_evaluation_diagnostics",
                    "passed": all(branch["error"] is None for branch in pair)
                    and pair[0].get("comparison") == pair[1].get("comparison"),
                }
            )
    all_checks = [check for branch in branches for check in branch["checks"]] + pairs
    report = {
        "protocol": PROTOCOL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_before": before,
        "source_after": code_identity(),
        "provenance_commit": provenance_commit,
        "evaluator_module_path": evaluator.__file__,
        "evaluator_module_sha256": sha(Path(evaluator.__file__)),
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha(Path(__file__)),
        "case_count": len(CASES),
        "branch_count": len(branches),
        "branches": branches,
        "order_comparisons": pairs,
        "check_count": len(jobs) * 4 + len(pairs),
        "check_pass_count": sum(check["passed"] for check in all_checks),
        "not_executed_count": sum(branch["not_executed_count"] for branch in branches),
        "passed": all(branch["passed"] for branch in branches)
        and all(pair["passed"] for pair in pairs),
        "resources": {"model_calls": 0, "GPU_used": False, "training": False},
    }
    if provenance_commit:
        report["archived_source_note"] = (
            "Complete git archive extracted outside working tree; source_commit obtained from archive invocation, not git metadata in extracted directory"
        )
    write(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--provenance-commit")
    args = parser.parse_args()
    report = run_experiment(args.output, args.workers, args.provenance_commit)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "passed",
                    "case_count",
                    "branch_count",
                    "check_count",
                    "check_pass_count",
                    "not_executed_count",
                )
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
