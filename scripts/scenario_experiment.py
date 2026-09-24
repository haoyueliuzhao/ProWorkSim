"""R3: replay finite declarative template scenarios through the unified host.

Initial deployment repetitions test construction determinism; they are not new
workflows. Literal finite answers below are independent of policies/evaluators.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.projections import derive_current_work_view
from proworksim.scenarios import (
    ScenarioController,
    bind_runtime,
    build_scenario,
    initial_business_state,
    load_scenario,
    run_scenario,
)
from proworksim.storage import digest, json_bytes

CASES = (
    "finance-direct",
    "finance-route",
    "report-direct",
    "chain-before-submit",
    "chain-pending",
    "chain-accepted",
    "report-pending-start",
    "finance-display-name",
)
COMMON = (
    "deployed_twice",
    "initial_business_state_reproducible",
    "no_fabricated_initial_work_history",
    "deployment_is_actual_public_calls",
    "declared_run_completes",
    "independent_port_capture_matches_experience",
    "original_immutable_bytes_preserved",
    "literal_finite_result",
)
CHAIN = (
    "one_predeclared_external_event",
    "external_effects_exactly_declared",
    "no_controller_downstream_repair_or_approval",
    "phase_produces_declared_work_consequence",
    "only_declared_source_record_changes",
    "downstream_adopts_final_published_comparison",
)
EXTRA = {
    "finance-route": ("private_statement_requires_real_request",),
    "report-pending-start": ("pending_prefix_actually_executed_and_retained",),
    "finance-display-name": ("surface_change_is_only_actor_display_name",),
}
PROTOCOL = {
    "suite": "scenario-R3-v0.10",
    "cases": CASES,
    "common_checks": COMMON,
    "chain_checks": CHAIN,
    "extra_checks": EXTRA,
    "scope": "Two existing finite templates and their shared chain. Three correction stages differ only in event.when; one legal information-route variation and one explicitly surface-only actor-name variation.",
    "construction": "All objects/obligations are package declarations and actual install_project calls. Shares and initial source publication are actual setup public calls. Initial comparison is an empty draft, never preapproved.",
    "truth": "Initial finance has nine keys: matched1, converted1, conflict1, incomparable3, missing2, ambiguous1. Correction changes only cost R3 90->80, giving matched2/conflict0. Final linked report expresses conflict0/incomparable3 for2026H1. Independent report expresses revenue120(up)/cost70(down).",
    "normalization": "Only root instance/branch/parent IDs, interactions wall_seconds, and receipt/transition state_digests excluded. Logical clocks, actions, operation IDs, revisions, authority, object identities, versions and immutable bytes are compared.",
    "controller": "Predicates inspect only declared world work stage, clock or prior event status; effects are predeclared public actions. No evaluation result drives effects, finds issues, changes downstream files or supplies worker answers.",
    "counts": "Eight primary scenario runs plus eight initial-build repetitions; repetition is determinism evidence, surface variation is not a new structure. Check counts are assertions, not independent worlds or capability scores.",
    "limits": [
        "Finite synthetic facts and sentence contracts",
        "Rule policies, no model/API/GPU/training",
        "Completed-opportunity prefix/resume only; no arbitrary process crash recovery",
    ],
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def versions(world):
    return {
        oid + ":" + vid: digest(world.store.version_path(a, vid).read_bytes())
        for oid, a in world.state["artifacts"].items()
        for vid in a["versions"]
    }


def current_docs(world):
    views = derive_current_work_view(world.state)
    result = {}
    for wid, item in world.state["work_items"].items():
        if views[wid]["status"] == "superseded" or not item["submissions"]:
            continue
        if any(
            other.get("previous_obligation_id") == wid
            for other in world.state["work_items"].values()
        ):
            continue
        sub = item["submissions"][-1]
        data = {}
        for oid, vid in sub["artifact_versions"].items():
            data.update(
                json.loads(world.store.version_path(world.state["artifacts"][oid], vid).read_text())
            )
        result[item["project_id"]] = {
            "work_id": wid,
            "submission_id": sub["submission_id"],
            "data": data,
            "submission": sub,
        }
    return result


def truth(docs, chain):
    result = {}
    for pid, item in docs.items():
        data = item["data"]
        if "reconciliation" in data:
            table = data["reconciliation"]
            expected = {
                "matched": 2 if chain else 1,
                "converted": 1,
                "conflict": 0 if chain else 1,
                "incomparable": 3,
                "missing": 2,
                "ambiguous": 1,
            }
            rows = {r["key"][1]: r for r in table["rows"]}
            result[pid] = (
                table["summary"] == expected
                and set(rows)
                == {
                    "absent",
                    "cash",
                    "cost",
                    "duplicate",
                    "fx",
                    "prior",
                    "sales",
                    "scope",
                    "unknown",
                }
                and rows["cost"]["delta"] == (0 if chain else -10)
                and rows["cost"]["left_value"] == 80
                and rows["cost"]["right_value"] == (80 if chain else 90)
            )
        if "report" in data:
            sections = {s["section_id"]: s for s in data["report"]["sections"]}
            expected = (
                {"conflict": (0, "unassessed"), "incomparable": (3, "unassessed")}
                if chain
                else {"revenue": (120, "up"), "cost": (70, "down")}
            )
            result[pid] = all(
                sections[k]["claims"][0]["value"] == v
                and sections[k]["claims"][0]["period"] == "2026H1"
                and sections[k]["claims"][0]["trend"] == trend
                and "2026H1" in sections[k]["body"]
                and ": " + str(v) + ";" in sections[k]["body"]
                for k, (v, trend) in expected.items()
            )
    return bool(result) and all(result.values()), result


def run_case(output, name):
    folder = output / name
    folder.mkdir(parents=True, exist_ok=False)
    planned = (
        list(COMMON)
        + (list(CHAIN) if name.startswith("chain-") else [])
        + list(EXTRA.get(name, ()))
    )
    result = {"case": name, "checks": [], "planned": planned, "source_before": code_identity()}

    def check(key, passed, details=None):
        result["checks"].append({"name": key, "passed": bool(passed), "details": details})

    try:
        declaration = load_scenario(
            Path(__file__).resolve().parents[1] / "examples/scenarios-v10" / (name + ".json")
        )
        write_json(folder / "spec.json", declaration)
        built = build_scenario(declaration, folder / "world")
        repeated = build_scenario(declaration, folder / "initial-repeat")
        check(
            "deployed_twice",
            built.status == repeated.status == "ready",
            [built.diagnostics, repeated.diagnostics],
        )
        initial = initial_business_state(built.world)
        repeat = initial_business_state(repeated.world)
        check(
            "initial_business_state_reproducible",
            initial == repeat,
            {
                "first_sha256": digest(json_bytes(initial)),
                "repeat_sha256": digest(json_bytes(repeat)),
            },
        )
        state = built.world.state
        check(
            "no_fabricated_initial_work_history",
            not state["issues"]
            and not state["issue_responses"]
            and not state["issue_decisions"]
            and all(not w["submissions"] for w in state["work_items"].values()),
        )
        check(
            "deployment_is_actual_public_calls",
            all(e["result"].get("ok") for e in built.deployment_log)
            and len(built.deployment_log)
            == len(declaration["projects"]) + len(declaration["setup"]),
        )
        original = versions(built.world)
        capture = {}
        runtime = bind_runtime(built, captured=capture)
        controller = ScenarioController(built, recorder=runtime.recorder)
        outcome = run_scenario(built, runtime, controller)
        check(
            "declared_run_completes",
            outcome["status"] == "completed",
            {
                "status": outcome["status"],
                "actions": outcome["actions"],
                "opportunities": outcome["opportunities"],
            },
        )
        events = outcome["experience"]["events"]
        actual = {
            label: [
                {"kind": e["kind"], "payload": e["payload"]}
                for e in events
                if e.get("worker_id") == label
                and e["kind"] in {"public_tools", "public_observation", "tool_call"}
            ]
            for label in capture
        }
        check("independent_port_capture_matches_experience", actual == capture)
        after = versions(built.world)
        check(
            "original_immutable_bytes_preserved",
            all(after.get(key) == value for key, value in original.items()),
        )
        docs = current_docs(built.world)
        ok, details = truth(docs, name.startswith("chain-"))
        check("literal_finite_result", ok, details)
        if name.startswith("chain-"):
            external = controller.log
            check(
                "one_predeclared_external_event",
                len(external) == 1 and external[0]["status"] == "executed",
            )
            effects = external[0]["effects"]
            check(
                "external_effects_exactly_declared",
                [{k: e[k] for k in ("actor", "project", "tool", "arguments")} for e in effects]
                == declaration["events"][0]["effects"],
            )
            check(
                "no_controller_downstream_repair_or_approval",
                all(
                    e["project"] == "FINANCE"
                    and e["tool"] in {"write_object", "publish"}
                    and e["arguments"].get("alias") == "statement"
                    for e in effects
                ),
            )
            state = built.world.state
            finance = [w for w in state["work_items"].values() if w["project_id"] == "FINANCE"]
            report = [w for w in state["work_items"].values() if w["project_id"] == "REPORT"]
            if name == "chain-accepted":
                consequence = (
                    len(finance) == 2
                    and len(report) == 2
                    and not state["work_replacements"]
                    and all(
                        w["submissions"][0]["review"]["decision"] == "accepted"
                        for w in (
                            state["work_items"]["FINANCE::reconcile"],
                            state["work_items"]["REPORT::research"],
                        )
                    )
                )
            else:
                consequence = (
                    len(finance) == 2
                    and len(report) == 1
                    and "FINANCE::reconcile" in state["work_replacements"]
                )
            check(
                "phase_produces_declared_work_consequence",
                consequence,
                {
                    "finance_work_ids": [w["work_item_id"] for w in finance],
                    "report_work_ids": [w["work_item_id"] for w in report],
                    "replacements": state["work_replacements"],
                },
            )
            oid = state["workspaces"]["FINANCE"]["statement"]
            artifact = state["artifacts"][oid]
            before = json.loads(built.world.store.version_path(artifact, "v1").read_text())
            later = json.loads(built.world.store.version_path(artifact, "v2").read_text())
            expected = copy.deepcopy(before)
            expected["records"][2]["value"] = 80
            check("only_declared_source_record_changes", later == expected)
            report_sub = docs["REPORT"]["submission"]
            comparison = state["workspaces"]["FINANCE"]["comparison"]
            releases = [r for r in state["releases"] if r["object_id"] == comparison]
            adopted = [
                b for b in report_sub["adoption_snapshot"].values() if b["alias"] == "comparison"
            ]
            check(
                "downstream_adopts_final_published_comparison",
                len(adopted) == 1 and adopted[0]["version_id"] == releases[-1]["version_id"],
            )
        if name == "finance-route":
            calls = [
                e["payload"]
                for e in events
                if e["kind"] == "tool_call" and e.get("worker_id") == "analyst"
            ]
            first = next(
                e["payload"]
                for e in events
                if e["kind"] == "public_observation" and e.get("worker_id") == "analyst"
            )
            check(
                "private_statement_requires_real_request",
                "statement" not in first["workspaces"]["FINANCE"]
                and any(
                    c["action"] == "request_information" and c["response"].get("ok") for c in calls
                )
                and any(
                    r["status"] == "resolved" for r in built.world.state["condition_specs"].values()
                ),
            )
        if name == "report-pending-start":
            prefix = built.prefix
            start, end = prefix["experience_range"]
            prefix_events = events[start:end]
            check(
                "pending_prefix_actually_executed_and_retained",
                prefix["prefix_executed"]
                and prefix["status"] == "reached"
                and prefix["experience_sha256"] == digest(json_bytes(prefix_events))
                and any(
                    e["kind"] == "tool_call" and e["payload"]["action"] == "submit"
                    for e in prefix_events
                ),
            )
        if name == "finance-display-name":
            other = load_scenario(
                Path(__file__).resolve().parents[1] / "examples/scenarios-v10/finance-direct.json"
            )
            compared = copy.deepcopy(declaration)
            compared["scenario_id"] = other["scenario_id"]
            compared.pop("variation")
            compared["world"]["actors"]["analyst"]["display_name"] = "analyst"
            check("surface_change_is_only_actor_display_name", compared == other)
        write_json(folder / "run.json", outcome)
        write_json(folder / "port-capture.json", capture)
        write_json(folder / "deployment.json", built.deployment_log)
        write_json(folder / "final-products.json", docs)
    except Exception as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    result["unexecuted"] = [
        key for key in planned if key not in {c["name"] for c in result["checks"]}
    ]
    result["passed"] = sum(c["passed"] for c in result["checks"])
    result["total"] = len(planned)
    result["source_after"] = code_identity()
    result["ok"] = result["passed"] == result["total"] and not result.get("error")
    write_json(folder / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    write_json(args.output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda name: run_case(args.output, name), CASES))
    summary = {
        "protocol": PROTOCOL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_before": before,
        "source_after": code_identity(),
        "cases": results,
        "passed": sum(r["passed"] for r in results),
        "total": sum(r["total"] for r in results),
        "ok": all(r["ok"] for r in results),
    }
    write_json(args.output / "report.json", summary)
    print(json.dumps({k: summary[k] for k in ("passed", "total", "ok")}))
    raise SystemExit(0 if summary["ok"] else 1)


if __name__ == "__main__":
    main()
