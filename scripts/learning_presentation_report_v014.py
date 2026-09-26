"""Read-only E0 presentation/context accounting after every declared run closes.

No model, world operation, evaluator or optimizer is run. Stored scalar/component
rewards are copied unchanged; structural repairs are not business correctness.
"""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from scripts.online_report_v013 import EvidenceFiles, summarize_events

VERSION = "learning-presentation-readonly-v0.14"
READS = {"read_alias", "read_version", "read_object"}


def serialized(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def reference(value):
    if not isinstance(value, dict):
        return None
    oid = value.get("object_id", value.get("artifact_id"))
    return {"object_id": oid, "version_id": value["version_id"]} if oid and value.get("version_id") else None


def feedback_in_request(events, failure, later):
    payload = later["payload"]
    messages = [e["payload"].get("message") for e in events
                if e["kind"] == "model_tool_result" and e.get("worker_id") == failure.get("worker_id")
                and e["sequence"] < later["sequence"]
                and e["payload"].get("call_id") == failure["payload"].get("model_call_id")]
    requests = [e["payload"].get("request") for e in events
                if e["kind"] == "model_attempt" and e["payload"].get("stage") == "finished"
                and e.get("worker_id") == later.get("worker_id")
                and e["payload"].get("call_id") == payload.get("model_call_id")]
    return len(requests) == 1 and any(m in (requests[0] or {}).get("messages", []) for m in messages)


def work_diagnostics(events, start_state, reward):
    """Describe factual progress and tightly bounded feedback repairs only."""
    calls = [e for e in events if e["kind"] == "tool_call"]
    workspace = start_state.get("workspaces", {}).get("TEAM", {})
    aliases = {oid: alias for alias, oid in workspace.items()}
    fixed = {}
    for item in start_state.get("work_items", {}).values():
        for submission in item.get("submissions", [])[-1:]:
            if not submission.get("invalidated"):
                fixed.update(submission.get("artifact_versions", {}))
    reads, fixed_reads, trace, repairs = [], [], [], []
    def successful(event):
        return event["payload"].get("response", {}).get("ok") is True

    def execution_ok(event):
        return successful(event) and event["payload"].get("response", {}).get("result", {}).get("execution_status") == "success"

    for event in calls:
        p = event["payload"]
        action, args, response = p["action"], p.get("arguments", {}), p.get("response", {})
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        row = {"sequence": event["sequence"], "member": event.get("worker_id"), "tool": action,
               "ok": response.get("ok"), "alias": args.get("alias"),
               "work_id": args.get("work_id"), "execution_status": result.get("execution_status")}
        if response.get("ok") is False:
            row["error"] = copy.deepcopy(response.get("error"))
        if action in READS and successful(event):
            ref = reference(result.get("reference"))
            read = {**row, "reference": ref, "alias": aliases.get((ref or {}).get("object_id"))}
            reads.append(read)
            if event.get("worker_id") == "reviewer" and ref and ref["object_id"] in fixed:
                fixed_reads.append({**read, "fixed_version_id": fixed[ref["object_id"]],
                                    "matches_fixed": ref["version_id"] == fixed[ref["object_id"]]})
        if action in {"submit", "inspect_submission"} and successful(event):
            fixed.update(result.get("artifact_versions", {}))
            row.update(submission_id=result.get("submission_id"), artifact_versions=result.get("artifact_versions"))
        if action == "adopt":
            row["reference"] = reference(args)
        if action == "write_object":
            row["basis_read_before_write"] = any(r["member"] == event.get("worker_id") and r["alias"] == "basis" for r in reads)
            models = args.get("data", {}).get("models", []) if isinstance(args.get("data"), dict) else []
            row["recorded_model_sql"] = [{"name": m.get("name"), "sql": m.get("sql")} for m in models if isinstance(m, dict)]
        trace.append(row)
        error = response.get("error", {})
        rejected = response.get("ok") is False
        sql_failed = successful(event) and action in {"sql_build", "sql_query"} and result.get("execution_status") not in {None, "success"}
        if not rejected and not sql_failed:
            continue
        later = [e for e in calls if e["sequence"] > event["sequence"] and e.get("worker_id") == event.get("worker_id")]
        seen = [e for e in later if feedback_in_request(events, event, e)]
        repair = {"member": event.get("worker_id"), "failure_sequence": event["sequence"],
                  "tool": action, "error": copy.deepcopy(error or result.get("error")),
                  "later_calls_with_actual_feedback": [e["sequence"] for e in seen],
                  "status": "no_verified_obligation_repair", "evidence_sequences": []}
        missing = re.search(r"SQL input requires this work's exact adoption: (\S+)", str(error.get("message", "")))
        if missing:
            alias = missing.group(1)
            adopted = next((e for e in seen if e["payload"]["action"] == "adopt" and successful(e)
                            and e["payload"].get("arguments", {}).get("alias") == alias
                            and args.get("work_id") in e["payload"].get("arguments", {}).get("work_ids", [])), None)
            resumed = next((e for e in seen if adopted and e["sequence"] > adopted["sequence"]
                            and e["payload"]["action"] == "sql_build" and execution_ok(e)
                            and e["payload"].get("arguments", {}).get("work_id") == args.get("work_id")), None)
            if resumed:
                repair.update(status="verified_adoption_prerequisite_then_execution", evidence_sequences=[adopted["sequence"], resumed["sequence"]], required_alias=alias)
        if sql_failed:
            edited = next((e for e in seen if e["payload"]["action"] == "write_object" and successful(e)
                           and e["payload"].get("arguments", {}).get("alias") == args.get("code_alias")), None)
            resumed = next((e for e in seen if edited and e["sequence"] > edited["sequence"]
                            and e["payload"]["action"] == action and execution_ok(e)
                            and e["payload"].get("arguments", {}).get("work_id") == args.get("work_id")), None)
            if resumed:
                repair.update(status="verified_code_edit_then_sql_execution", evidence_sequences=[edited["sequence"], resumed["sequence"]])
        if repair["status"] == "no_verified_obligation_repair":
            accepted = next((e for e in seen if e["payload"]["action"] == action and successful(e)), None)
            if accepted:
                repair.update(status="same_operation_accepted_only", evidence_sequences=[accepted["sequence"]])
        repairs.append(repair)
    stops = []
    for event in events:
        if event["kind"] == "model_attempt" and event["payload"].get("stage") == "finished":
            body = event["payload"].get("response", {}).get("body", {})
            if body.get("error", {}).get("code") == "context_length_exceeded":
                prior = [r for r in trace if r["sequence"] < event["sequence"] and r["member"] == event.get("worker_id")]
                stops.append({"member": event.get("worker_id"), "sequence": event["sequence"],
                              "generation_started": body.get("generation_started"), "error": body["error"],
                              "last_world_call": prior[-1] if prior else None,
                              "final_unmet_terms": [c["term_id"] for c in (reward or {}).get("components", []) if c.get("achieved") is False],
                              "interpretation": "Observed context stop and final unmet outcomes coexist; this does not establish that extra context would complete them."})
    return {"reads": reads, "reviewer_fixed_version_reads": fixed_reads,
            "reviewer_fixed_version_mismatches": [r for r in fixed_reads if not r["matches_fixed"]],
            "tool_trace": trace, "feedback_repairs": repairs, "context_stops": stops,
            "repair_status_counts": dict(Counter(r["status"] for r in repairs)),
            "limits": "Fixed-version mismatch is an observed read of another version, not proof of intent. A successful adoption/build or changed tool is not business correctness; saved reward components are reported separately."}


def projection_accounting(folder, files, events):
    actual = {e["payload"].get("response", {}).get("command_id"): e["payload"].get("response")
              for e in events if e["kind"] == "tool_call"}
    per_tool = defaultdict(Counter)
    issues, refs = [], []
    for path in sorted((folder / "public-projections").glob("*/call-*.json")):
        row = files.read(path)
        raw, public = row["raw_response"], row["public_response"]
        command = public.get("command_id")
        if command not in actual or public != actual[command]:
            issues.append({"path": str(path), "reason": "projected_response_not_identical_to_actual_retained_tool_return"})
        for key, value in (("raw_response", raw), ("public_response", public)):
            if hashlib.sha256(serialized(value)).hexdigest() != row[key + "_sha256"]:
                issues.append({"path": str(path), "reason": key + "_hash_mismatch"})
        counts = per_tool[row["action"]]
        counts["calls"] += 1
        counts["raw_bytes"] += len(serialized(raw))
        counts["public_bytes"] += len(serialized(public))
        counts["changed_returns"] += raw != public
        refs.append(str(path))
    total = sum(per_tool.values(), Counter())
    return {"totals": dict(total), "per_tool": {k: dict(v) for k, v in per_tool.items()},
            "issues": issues, "refs": refs,
            "scope": "Sum of each executed public return once; not recurrent prompt bytes, tokenizer counts or imagined constant-length trajectories."}


def build_report(inputs):
    files, runs = EvidenceFiles(), []
    for label, path in inputs.items():
        root = Path(path).resolve()
        saved = files.read(root / "online/report.json")
        if saved.get("status") != "complete":
            raise ValueError(f"Run {label} has not completed; no partial final comparison is emitted")
        protocol = files.read(root / "online/protocol.json")
        run = {"label": label, "root": str(root), "source": files.read(root / "source-before.json"),
               "protocol": protocol, "runner_report": saved, "slots": []}
        for wi, window in enumerate(protocol["windows"]):
            collection = root / f"online/window-{wi}/collection"
            declaration = files.read(collection / "declaration.json")
            summary = files.read(collection / "summary.json")
            for si, slot in enumerate(window["slots"]):
                folder = collection / f"slot-{si}"
                manifest = files.read(folder / "episode/manifest.json")
                if manifest.get("status") != "closed":
                    raise ValueError("A declared episode is not closed")
                history_path = folder / "episode" / manifest["experience"]["path"]
                history = files.read(history_path)
                if files.refs[str(history_path.resolve())]["sha256"] != manifest["experience"]["sha256"]:
                    raise ValueError("Original closed experience hash changed")
                events = history["events"][manifest["experience"]["start"]:manifest["experience"]["end"]]
                rollout = files.read(folder / "team-rollout.json", optional=True)
                reward = (rollout or {}).get("reward_eligibility")
                actual = summarize_events(events, declared_transport=saved.get("transport_kind"), actor_identity=declaration["actor_identity"])
                row = {"case_id": slot.get("case_id"), "slot_id": slot["slot_id"], "sampling_seed": slot["sampling_seed"],
                       "presentation": window.get("presentation"), "max_length": protocol["recipe"]["max_length"],
                       "active_members": declaration["slots"][si]["active_members"],
                       "actor_identity": declaration["actor_identity"], "episode_ref": str(folder / "episode"),
                       "reward": copy.deepcopy(reward), "work_validity": copy.deepcopy((rollout or {}).get("work_validity")),
                       "boundary": next((r.get("boundary") for r in summary["slots"] if r["slot_id"] == slot["slot_id"]), None),
                       "tokens_and_attempts": actual["totals"], "member_tokens_and_attempts": actual["members"],
                       "tool_counts": actual["tools"], "next_generation_feedback": actual["rejection_followups"],
                       "projections": projection_accounting(folder, files, events),
                       "work_diagnostics": work_diagnostics(events, files.read(folder / "episode/start/control/state.json"), reward)}
                first_observations = {}
                for event in events:
                    member = event.get("worker_id")
                    if event["kind"] != "public_observation" or member in first_observations:
                        continue
                    observed = copy.deepcopy(event["payload"])
                    normalized = {k: v for k, v in observed.items() if k not in {"instance_id", "branch_id"}}
                    first_observations[member] = {
                        "sequence": event["sequence"],
                        "actual_sha256": hashlib.sha256(serialized(observed)).hexdigest(),
                        "without_instance_branch_sha256": hashlib.sha256(serialized(normalized)).hexdigest(),
                        "instance_id": observed.get("instance_id"), "branch_id": observed.get("branch_id"),
                    }
                row["first_public_observations"] = first_observations
                run["slots"].append(row)
        totals = Counter()
        for row in run["slots"]:
            totals.update(row["tokens_and_attempts"])
        run["totals"] = dict(totals)
        run["reward_values"] = [r["reward"].get("reward") if r["reward"] else None for r in run["slots"]]
        run["context_stops"] = sum(len(r["work_diagnostics"]["context_stops"]) for r in run["slots"])
        run["episodes_with_context_stop"] = sum(bool(r["work_diagnostics"]["context_stops"]) for r in run["slots"])
        runs.append(run)
    paired = []
    for case in sorted({s["case_id"] for run in runs for s in run["slots"]}):
        arms = [{"label": run["label"], **{k: s[k] for k in ("case_id", "sampling_seed", "presentation", "max_length", "actor_identity", "tokens_and_attempts", "projections", "reward", "work_diagnostics", "first_public_observations")}}
                for run in runs for s in run["slots"] if s["case_id"] == case]
        paired.append({"case_id": case, "arms": arms,
                       "same_sampling_seed": len({s["sampling_seed"] for s in arms}) == 1,
                       "exact_first_per_member_observations_equal": len({tuple(sorted((m, v["actual_sha256"]) for m, v in s["first_public_observations"].items())) for s in arms}) == 1,
                       "first_per_member_observations_equal_ignoring_instance_branch_ids": len({tuple(sorted((m, v["without_instance_branch_sha256"]) for m, v in s["first_public_observations"].items())) for s in arms}) == 1,
                       "before_first_actor_action_observations_equal_ignoring_instance_branch_ids": len({min(s["first_public_observations"].values(), key=lambda v: v["sequence"])["without_instance_branch_sha256"] for s in arms}) == 1,
                       "same_base_and_adapter": len({(s["actor_identity"]["base_manifest_sha256"], s["actor_identity"]["adapter_sha256"]) for s in arms}) == 1})
    contrasts = []
    for index, left in enumerate(runs):
        for right in runs[index + 1:]:
            recipes = [copy.deepcopy(r["protocol"]["recipe"]) for r in (left, right)]
            lengths = [r.pop("max_length") for r in recipes]
            plans = [[{key: value for key, value in slot.items() if key != "slot_id"}
                      for window in r["protocol"]["windows"] for slot in window["slots"]]
                     for r in (left, right)]
            presentations = [[w.get("presentation") for w in r["protocol"]["windows"]] for r in (left, right)]
            contrasts.append({
                "left": left["label"], "right": right["label"],
                "same_source": left["source"] == right["source"],
                "same_recipe_except_context_cap": recipes[0] == recipes[1],
                "same_predeclared_cases_and_sampling_seeds": plans[0] == plans[1],
                "same_presentation": presentations[0] == presentations[1],
                "same_context_cap": lengths[0] == lengths[1],
                "interpretation": "Recorded declarations, not proof of deterministic hardware execution or causal attribution beyond the frozen contrast.",
            })
    return {"version": VERSION, "mode": "read_only_stored_facts_no_rescoring", "runs": runs, "paired_cases": paired, "contrasts": contrasts,
            "references": files.refs, "limitations": [
                "Declared presentation contrast is full8 versus compact8; context-cap contrast is compact8 versus compact12. Other pairings vary multiple intended factors.",
                "Independent world copies have distinct visible instance/branch identifiers, even when business observations agree after removing them. Thus equal case seeds are not byte-identical inputs; early trajectory differences cannot be uniquely attributed to presentation or context.",
                "No evaluator, policy, optimizer, SQL or GPU computation is executed; original scalar/components are copied without reassessment.",
                "HTTP-shaped resident attempts are counted as direct transport, not actual network HTTP.",
                "Different tools or accepted commands alone do not prove repaired business obligations. Context stops are observed boundaries, not counterfactual causes.",
                "New development cases belong to one constructed source family, not independent-source generalization. E0 is frozen inference, not evidence of training gain.",
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="LABEL=RUN_DIRECTORY")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = dict(value.split("=", 1) for value in args.input)
    if len(inputs) != len(args.input):
        raise ValueError("Condition labels must be unique")
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(Path(root).resolve()) for root in inputs.values()):
        raise ValueError("Write a new report outside all original input trees")
    report = build_report(inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(serialized(report))
    print(json.dumps({"output": str(output), "runs": len(report["runs"]), "cases": len(report["paired_cases"])}))


if __name__ == "__main__":
    main()
