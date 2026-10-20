"""Read existing v053 worker receipts; never run a model, grader or environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_panel_report_v053 import build_report, markdown, recover_native_accounting
from proworksim.software_panel_v053 import sha256, write_new


def checked_json(reference):
    path = Path(reference["path"])
    content = path.read_bytes()
    if sha256(content) != reference["sha256"]:
        raise ValueError("Read-only report source digest changed: " + str(path))
    return json.loads(content)


def load_observations(reports_root, *, panel_sha256, host_state=None, panel_rows=None):
    """Only native worker-level report/interruption files carry a frozen row."""
    root = Path(reports_root)
    observations, started = [], set()
    plan_cache = {}
    for path in sorted(root.rglob("model-entered.json")):
        value = json.loads(path.read_bytes())
        row = value.get("row")
        if row is not None:
            plan_ref = value["source_plan"]
            key = (plan_ref["path"], plan_ref["sha256"])
            if key not in plan_cache:
                plan_cache[key] = checked_json(plan_ref)
            if plan_cache[key]["panel_ref"]["sha256"] != panel_sha256:
                raise ValueError("Model-entry marker belongs to another panel")
            started.add(row["slot_id"])
    for path in sorted([*root.rglob("report.json"), *root.rglob("interruption.json")]):
        content = path.read_bytes()
        value = json.loads(content)
        if "row" not in value or "source_plan" not in value:
            continue
        plan_ref = value["source_plan"]
        key = (plan_ref["path"], plan_ref["sha256"])
        if key not in plan_cache:
            plan_cache[key] = checked_json(plan_ref)
        declared = plan_cache[key]["panel_ref"]["sha256"]
        result_declared = value.get("result", {}).get("panel_sha256", declared)
        if declared != panel_sha256 or result_declared != panel_sha256:
            raise ValueError("Worker receipt belongs to another panel")
        observations.append({
            **value, "panel_sha256": panel_sha256,
            "_run_plan_sha256": plan_ref["sha256"],
            "_source_ref": {"path": str(path), "sha256": sha256(content), "bytes": len(content)},
        })
    if host_state:
        plan_ref = host_state["plan_ref"]
        key = (plan_ref["path"], plan_ref["sha256"])
        if key not in plan_cache:
            plan_cache[key] = checked_json(plan_ref)
        if plan_cache[key]["panel_ref"]["sha256"] != panel_sha256:
            raise ValueError("Host state belongs to another frozen panel")
        frozen_rows = {row["slot_id"]: row for row in panel_rows or []}
        formal_ids = {item["row"]["slot_id"] for item in observations
                      if item["status"] != "resource_wait"}
        for slot in host_state.get("slots", []):
            if slot["status"] not in ("technical_unknown", "complete") or slot["slot_id"] in formal_ids:
                continue
            row = frozen_rows.get(slot["slot_id"])
            if row is None or any(slot.get(field) != value for field, value in row.items()):
                raise ValueError("Unclosed host attempt differs from the frozen slot identity")
            attempts = slot.get("attempts", [])
            if any(attempt.get("model_entered") is True for attempt in attempts[:-1]):
                raise ValueError("A model-entered attempt cannot be followed by a retry")
            account, recovery = None, {"reason": "host_unknown_without_attempt_evidence"}
            if attempts:
                attempt_path = Path(attempts[-1]["path"]).resolve()
                if not attempt_path.is_relative_to(root.resolve()):
                    raise ValueError("Host attempt is outside this report inventory")
                account, recovery = recover_native_accounting(attempt_path, slot_id=row["slot_id"])
                recovery["host_attempt"] = attempts[-1]
            observations.append({
                "row": row, "panel_sha256": panel_sha256,
                "_run_plan_sha256": plan_ref["sha256"], "status": "technical_unknown",
                "R_code": None, "source_plan": plan_ref, "accounting": account,
                "accounting_recovery": recovery,
                "verdict": {"reasons": [
                    "host_terminal_status_without_closed_worker_receipt",
                    slot.get("failure_type") or "worker_receipt_missing"]},
            })
    if len({key[1] for key in plan_cache}) > 1:
        raise ValueError("Different frozen run configurations must be reported separately")
    return observations, started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--reports-root", required=True)
    parser.add_argument("--state", help="Optional frozen snapshot of the v053 host state")
    parser.add_argument("--output", required=True, help="New immutable JSON report path")
    parser.add_argument("--markdown")
    args = parser.parse_args()
    content = Path(args.panel).read_bytes()
    panel = json.loads(content)
    panel_sha256 = sha256(content)
    state_content = Path(args.state).read_bytes() if args.state else None
    state = json.loads(state_content) if state_content else {}
    observations, started = load_observations(
        args.reports_root, panel_sha256=panel_sha256,
        host_state=state, panel_rows=panel["slots"])
    if args.state and checked_json(state["plan_ref"])["panel_ref"]["sha256"] != panel_sha256:
        raise ValueError("Host state belongs to another frozen panel")
    if args.state and any(observation["_run_plan_sha256"] != state["plan_ref"]["sha256"]
                          for observation in observations):
        raise ValueError("Host state and worker receipts use different frozen configurations")
    started.update(state.get("started_slot_ids", []))
    started.update(row["slot_id"] for row in state.get("slots", [])
                   if any(attempt.get("model_entered") is True for attempt in row.get("attempts", [])))
    active = set(state.get("active_slot_ids", [])) | set(state.get("active", {}))
    started.update(active)
    report = build_report(
        panel, observations, panel_sha256=panel_sha256,
        started_slot_ids=started, active_slot_ids=active)
    report["sources"] = {
        "panel": {"path": args.panel, "sha256": panel_sha256, "bytes": len(content)},
        "host_state": {"path": args.state, "sha256": sha256(state_content),
                       "bytes": len(state_content)} if state_content is not None else None,
        "worker_observation_count_including_resource_waits": sum(
            "_source_ref" in observation for observation in observations),
        "host_recovered_observation_count": sum(
            "accounting_recovery" in observation for observation in observations),
    }
    write_new(args.output, report)
    if args.markdown:
        path = Path(args.markdown)
        text = markdown(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text() != text:
            raise FileExistsError("Refuse to overwrite an earlier report")
        if not path.exists():
            path.write_text(text)
    print(json.dumps({
        "output": args.output, "main": report["main"],
        "inventory": report["inventory"], "tokens": report["tokens"]["all_280_slots"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
