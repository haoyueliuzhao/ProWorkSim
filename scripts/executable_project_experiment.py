"""Public-project prototype: real SQL, four-project change, and admission controls."""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.projections import derive_current_work_view
from proworksim.core.world import WorldSpec
from proworksim.episode import begin_episode, finish_episode, assess_historical_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.scenarios import build_scenario, bind_runtime, run_scenario
from proworksim.storage import digest
from proworksim.templates.executable_project import package, scenario_spec, sql_project
from proworksim.world_core import WorldCore

CASES = ("static", "dynamic", "equivalent_sql", "wrong_sql", "tests_tampered", "result_forged")
CHAIN_CHECKS = (
    "declared_world_ready",
    "actual_runtime_completes",
    "all_fixed_accepted_products_pass_independently",
    "pinned_public_seed_row_counts",
    "actual_starter_binder_error_then_code_edit",
    "real_build_and_query_files_are_versioned",
    "submissions_pin_executed_code_and_result",
    "no_fabricated_initial_approval",
    "initial_immutable_versions_unchanged",
    "actual_port_capture_equals_experience",
    "independent_literal_completed_revenue",
)
DYNAMIC_CHECKS = (
    "one_declared_request_change",
    "controller_only_changes_request",
    "P0_unchanged_by_customer_grain_change",
    "P1_P2_bind_new_request_exactly",
    "P2_actual_version_located_feedback",
    "P1_observes_actual_feedback",
    "monthly_400_customer_rows_and_four_periods",
    "accepted_predecessor_payloads_preserved",
)
CONTROL_CHECKS = (
    "actual_code_write",
    "actual_build_success",
    "actual_editable_tests_green",
    "actual_fixed_submission",
    "expected_independent_outcome",
    "original_versions_preserved",
    "trusted_execution_marker_matches_case",
)
PROTOCOL = {
    "suite": "executable-projects-v0.11",
    "upstream_commit": "36bde6cba69d962b83be1d52fc65a0dce1cb4ebb",
    "cases": CASES,
    "chain_checks": CHAIN_CHECKS,
    "dynamic_checks": DYNAMIC_CHECKS,
    "control_checks": CONTROL_CHECKS,
    "source": "Official dbt-labs/jaffle_shop_duckdb Apache-2.0 fictional example; original100 customers,99 orders,113 payments. Research-designed organization and change are not upstream enterprise process.",
    "execution": "Actual SELECT/CTE SQL files, fresh DuckDB1.5.5, build tests and queries. Managed JSON versions preserve SQL/config, exact sources, real output tables, errors and logical DB reconstruction material. No full dbt adapter or arbitrary shell.",
    "independent_truth": "Separate Python finite business computation; tables compared as multisets of column/value records. SQL text, row order and column order are not the target. Editable local tests and formal delivery-only acceptance are not independent correctness.",
    "change": "After all initial work accepted, predeclared P2 request changes customer to customer_month. P1/P2/P3 maintenance follows exact public publication rules. P2 colleague reads fixed old P1 metrics and actual new request, locates absent period column; controller does not edit P1/P2 SQL or results.",
    "controls": "Actual source-preserving but nonequivalent SQL, equivalent SQL, an always-green replacement local test with bad SQL, and rewriting an otherwise correct result without trusted execution metadata. These are declared program controls, not model runs.",
    "limits": [
        "One public synthetic project family, not independent enterprise diversity",
        "Single writer per world; workers are fixed rule policies",
        "Logical database reconstruction, not bit-identical external DB-file recovery",
        "No model/API/GPU/RL in this suite",
    ],
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def versions(world):
    return {
        oid + ":" + vid: digest(world.store.version_path(a, vid).read_bytes())
        for oid, a in world.state["artifacts"].items()
        for vid in a["versions"]
    }


def product(world, wid):
    item = world.state["work_items"][wid]
    sub = item["submissions"][-1]
    oid = world.state["workspaces"][item["project_id"]]["result"]
    vid = sub["artifact_versions"][oid]
    return json.loads(world.store.version_path(world.state["artifacts"][oid], vid).read_text()), sub


def table_records(table):
    return [dict(zip([c["name"] for c in table["columns"]], row)) for row in table["rows"]]


def literal_total_from_archived_csv():
    import csv

    base = Path(__file__).resolve().parents[1] / "examples/public-projects-v11/upstream/seeds"
    with (base / "raw_orders.csv").open(newline="") as f:
        orders = {int(r["id"]): r for r in csv.DictReader(f)}
    with (base / "raw_payments.csv").open(newline="") as f:
        payments = list(csv.DictReader(f))
    return sum(
        int(r["amount"]) for r in payments if orders[int(r["order_id"])]["status"] == "completed"
    )


def chain(folder, name, check):
    declaration = scenario_spec(changed=name == "dynamic")
    write(folder / "scenario.json", declaration)
    deployed = build_scenario(declaration, folder / "world")
    check("declared_world_ready", deployed.status == "ready", deployed.diagnostics)
    if deployed.status != "ready":
        raise ValueError(str(deployed.diagnostics))
    world = deployed.world
    initial = versions(world)
    initial_p0 = copy.deepcopy(world.state["work_items"]["P0::build"])
    check(
        "no_fabricated_initial_approval",
        all(not item["submissions"] for item in world.state["work_items"].values()),
    )
    raw_oid = world.state["workspaces"]["P0"]["raw"]
    raw = json.loads(world.store.version_path(world.state["artifacts"][raw_oid], "v1").read_text())
    check(
        "pinned_public_seed_row_counts",
        {k: len(t["rows"]) for k, t in raw["tables"].items()}
        == {"raw_customers": 100, "raw_orders": 99, "raw_payments": 113},
    )
    captured = {}
    runtime = bind_runtime(deployed, captured=captured)
    outcome = run_scenario(deployed, runtime)
    check(
        "actual_runtime_completes",
        outcome["status"] == "completed",
        {
            "status": outcome["status"],
            "actions": outcome["actions"],
            "opportunities": outcome["opportunities"],
        },
    )
    evaluations = {}
    products = {}
    for wid, view in derive_current_work_view(world.state).items():
        if view["status"] == "accepted":
            item = world.state["work_items"][wid]
            sub = item["submissions"][-1]
            evaluations[wid] = world.evaluate_submission(
                item["project_id"], wid, sub["submission_id"]
            )
            products[wid] = product(world, wid)[0]
    check(
        "all_fixed_accepted_products_pass_independently",
        len(evaluations) >= 4 and all(e["passed"] for e in evaluations.values()),
        {k: e["status"] for k, e in evaluations.items()},
    )
    calls = [e for e in runtime.recorder.events if e["kind"] == "tool_call"]
    p1 = [e["payload"] for e in calls if e.get("worker_id") == "P1"]
    errors = [
        c
        for c in p1
        if c["action"] == "sql_build"
        and c["response"].get("ok")
        and c["response"]["result"].get("error", {})
        and c["response"]["result"]["error"]["type"] == "BinderException"
    ]
    check(
        "actual_starter_binder_error_then_code_edit",
        bool(errors)
        and any(
            c["action"] == "write_object" and c["arguments"].get("alias") == "code" for c in p1
        ),
    )
    check(
        "real_build_and_query_files_are_versioned",
        all(
            any(e.get("worker_id") == pid and e["payload"]["action"] == "sql_build" for e in calls)
            and any(
                e.get("worker_id") == pid and e["payload"]["action"] == "sql_query" for e in calls
            )
            for pid in ("P0", "P1", "P2", "P3")
        )
        and all(
            data["database"]["file_created"]
            and any(path.endswith(".sql") for path in data["files"])
            for data in products.values()
        ),
    )
    pinned = True
    for wid in products:
        data, sub = product(world, wid)
        ref = data["execution"]["code_reference"]
        pinned &= sub["artifact_versions"].get(ref["object_id"]) == ref["version_id"]
    check("submissions_pin_executed_code_and_result", pinned)
    after = versions(world)
    check(
        "initial_immutable_versions_unchanged", all(after.get(k) == v for k, v in initial.items())
    )
    recorded = {
        label: [
            {"kind": e["kind"], "payload": e["payload"]}
            for e in runtime.recorder.events
            if e.get("worker_id") == label
            and e["kind"] in {"tool_call", "public_tools", "public_observation"}
        ]
        for label in captured
    }
    check("actual_port_capture_equals_experience", captured == recorded)
    p1data = next(reversed([data for wid, data in products.items() if wid.startswith("P1::")]))
    total = sum(r["revenue_cents"] for r in table_records(p1data["tables"]["metrics"]))
    check(
        "independent_literal_completed_revenue",
        total == literal_total_from_archived_csv(),
        {"actual_cents": total, "independent_csv_cents": literal_total_from_archived_csv()},
    )
    if name == "dynamic":
        logs = outcome["controller"]["log"]
        check(
            "one_declared_request_change",
            len(logs) == 1
            and logs[0]["event_id"] == "request-monthly-interface"
            and logs[0]["status"] == "executed",
        )
        check(
            "controller_only_changes_request",
            all(
                e["actor"] == "customer_analyst"
                and e["project"] == "P2"
                and e["arguments"].get("alias") == "request"
                and e["tool"] in {"write_object", "publish"}
                for e in logs[0]["effects"]
            ),
        )
        p0 = world.state["work_items"]["P0::build"]
        check(
            "P0_unchanged_by_customer_grain_change",
            p0["requirement_version"] == initial_p0["requirement_version"]
            and len(p0["submissions"]) == 1,
        )
        latest = {
            pid: next(reversed([wid for wid in products if wid.startswith(pid + "::")]))
            for pid in ("P1", "P2", "P3")
        }
        check(
            "P1_P2_bind_new_request_exactly",
            all(
                product(world, latest[pid])[1]["adoption_snapshot"][latest[pid] + "::request"][
                    "version_id"
                ]
                == "v2"
                for pid in ("P1", "P2")
            ),
        )
        issues = list(world.state["issues"].values())
        check(
            "P2_actual_version_located_feedback",
            any(
                i["project_id"] == "P1"
                and i["raised_by"] == "customer_analyst"
                and i["locator"] == ["tables", "metrics", "columns"]
                for i in issues
            ),
            issues,
        )
        issue_ids = {i["issue_id"] for i in issues}
        check(
            "P1_observes_actual_feedback",
            bool(issue_ids)
            and any(
                e["kind"] == "public_observation"
                and e.get("worker_id") == "P1"
                and bool(issue_ids & set(e["payload"]["issues"]))
                for e in runtime.recorder.events
            ),
        )
        counts = {
            pid: len(next(iter(products[wid]["tables"].values()))["rows"])
            for pid, wid in latest.items()
        }
        check(
            "monthly_400_customer_rows_and_four_periods",
            counts == {"P1": 400, "P2": 400, "P3": 4},
            counts,
        )
        preserved = True
        for pid in ("P1", "P2"):
            sid = world.state["work_items"][pid + "::build"]["submissions"][0]["submission_id"]
            inspected = [
                e["payload"]["response"]["result"]
                for e in calls
                if e.get("worker_id") == pid
                and e["payload"]["action"] == "inspect_submission"
                and e["payload"]["arguments"]["submission_id"] == sid
            ]
            preserved &= (
                bool(inspected)
                and inspected[0] == world.state["work_items"][pid + "::build"]["submissions"][0]
            )
        check("accepted_predecessor_payloads_preserved", preserved)
    write(folder / "run.json", outcome)
    write(folder / "port-capture.json", captured)
    write(folder / "evaluations.json", evaluations)
    write(folder / "products.json", products)


def control(folder, name, check):
    world = WorldCore.create(
        folder / "world",
        WorldSpec(
            "sql-control",
            {"operator": {}, "data_engineer": {}},
            applications=["files", "sql"],
            bootstrap_grants=[
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        ),
    )
    payload = package("P0")
    payload["works"][0]["requirements"]["public_delivery"] = {}
    installed = world.session("operator").call("install_project", package=payload)
    if not installed["ok"]:
        raise ValueError(str(installed))
    initial = versions(world)
    captured = []
    port = capture_port(world.session("data_engineer", "P0"), captured)
    recorder = ExperienceRecorder()
    cursor = 0

    def collect():
        nonlocal cursor
        for e in captured[cursor:]:
            recorder.record(e["kind"], e["payload"], worker_id="controlled_SQL_worker")
        cursor = len(captured)

    def call(action, **args):
        result = port.call(action, **args)
        collect()
        if not result["ok"]:
            raise ValueError(str(result))
        return result["result"]

    port.tools()
    port.observe()
    collect()
    episode = folder / "episode"
    begin_episode(
        world,
        episode,
        experience=recorder.snapshot(),
        work_ids=["P0::build"],
        work_nodes=["P0::build"],
        scenario={"case": name, "suite": PROTOCOL["suite"]},
        policies={"kind": "declared program SQL control"},
    )
    oid = world.state["workspaces"]["P0"]["raw"]
    call("adopt", alias="raw", object_id=oid, version_id="v1", policy="fixed", work_ids=["build"])
    code = sql_project("P0", tampered_tests=name == "tests_tampered")
    if name == "equivalent_sql":
        code["models"][0]["sql"] = (
            "WITH source AS (SELECT * FROM raw_customers) SELECT last_name,id AS customer_id,first_name FROM source ORDER BY id DESC"
        )
    if name in {"wrong_sql", "tests_tampered"}:
        code["models"][0]["sql"] += " WHERE id <> 1"
    call("write_object", alias="code", data=code, work_id="build")
    check("actual_code_write", True)
    built = call(
        "sql_build",
        work_id="build",
        code_alias="code",
        output_alias="result",
        input_aliases=["raw"],
    )
    check("actual_build_success", built["execution_status"] == "success")
    check(
        "actual_editable_tests_green",
        bool(built["tests"])
        and all(t["passed"] and not t["failure_rows"]["rows"] for t in built["tests"]),
        built["tests"],
    )
    if name == "result_forged":
        result = call("read_object", alias="result")["data"]
        call("write_object", alias="result", data=result, work_id="build")
    submitted = call("submit", work_id="build", artifacts=["code", "result"])
    check("actual_fixed_submission", bool(submitted["submission_id"]))
    evaluated = world.evaluate_submission("P0", "build", submitted["submission_id"])
    expected = (
        "pass"
        if name == "equivalent_sql"
        else "structure_failure"
        if name == "result_forged"
        else "content_failure"
    )
    check(
        "expected_independent_outcome",
        evaluated["status"] == expected,
        {"expected": expected, "actual": evaluated["status"], "passed": evaluated["passed"]},
    )
    after = versions(world)
    check("original_versions_preserved", all(after.get(k) == v for k, v in initial.items()))
    artifact = world.state["artifacts"][world.state["workspaces"]["P0"]["result"]]
    proof = artifact["versions"][artifact["current_version"]].get("execution_provenance")
    check(
        "trusted_execution_marker_matches_case",
        proof is None if name == "result_forged" else proof is not None,
    )
    manifest = finish_episode(
        world,
        episode,
        experience=recorder.snapshot(),
        termination={"status": "fixed_submission", "control": name},
    )
    historical = assess_historical_episode(episode)
    write(folder / "episode-manifest.json", manifest)
    write(folder / "assessment.json", historical)
    write(folder / "evaluation.json", evaluated)
    write(folder / "build.json", built)
    write(folder / "port-capture.json", captured)


def run_case(root, name):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=False)
    planned = (
        list(CHAIN_CHECKS) + (list(DYNAMIC_CHECKS) if name == "dynamic" else [])
        if name in {"static", "dynamic"}
        else list(CONTROL_CHECKS)
    )
    result = {"case": name, "source_before": code_identity(), "planned": planned, "checks": []}

    def check(key, passed, details=None):
        result["checks"].append({"name": key, "passed": bool(passed), "details": details})

    try:
        (chain if name in {"static", "dynamic"} else control)(folder, name, check)
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    result["unexecuted"] = [
        key for key in planned if key not in {c["name"] for c in result["checks"]}
    ]
    result["passed"] = sum(c["passed"] for c in result["checks"])
    result["total"] = len(planned)
    result["ok"] = result["passed"] == result["total"] and not result.get("error")
    result["source_after"] = code_identity()
    write(folder / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / "protocol.json", PROTOCOL)
    before = code_identity()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        cases = list(pool.map(lambda name: run_case(args.output, name), args.cases))
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "cases": cases,
        "passed": sum(c["passed"] for c in cases),
        "total": sum(c["total"] for c in cases),
        "ok": all(c["ok"] for c in cases),
    }
    write(args.output / "report.json", report)
    print(json.dumps({k: report[k] for k in ["passed", "total", "ok"]}))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
