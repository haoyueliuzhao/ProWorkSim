"""Read compact selected summaries and bounded existing official failure evidence."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/software-benchmark-v137/review-sprint-causes-r1"
ROWS = ROOT / "artifacts/software-benchmark-v136/cash-excluded-mechanism-r1/per-task.json"
SUMMARY = ROOT / "artifacts/software-benchmark-v136/cash-excluded-mechanism-r1/summary.json"
S1 = ROOT / "artifacts/software-benchmark-v128/independent-count-audit-r1/selected-per-task.json"


def read(path, expected=None, maximum=2_000_000):
    path = Path(path).resolve()
    if path.stat().st_size > maximum:
        raise ValueError("This analysis does not read large retained objects")
    raw = path.read_bytes()
    ref = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if expected is not None and ref != expected:
        raise ValueError("The retained evidence changed")
    return raw, ref


def obj(path, expected=None):
    raw, ref = read(path, expected)
    return json.loads(raw), ref


def failure_sections(text, test_ids):
    lines = text.splitlines()
    evidence = []
    for test_id in test_ids:
        suffix = test_id.split("::")[-1]
        start = next((n for n, line in enumerate(lines)
                      if line.startswith("____") and suffix in line), None)
        if start is None:
            continue
        end = next((n for n in range(start + 1, len(lines))
                    if lines[n].startswith("____") or lines[n].startswith("====")), len(lines))
        evidence.append({"test_id": test_id, "first_line": start + 1,
                         "last_line": min(end, start + 90),
                         "text": "\n".join(lines[start:min(end, start + 90)])})
    return evidence


def event_summary(row):
    child, ref = obj(row["controller_result"]["path"], row["controller_result"])
    events = []
    for index, outcome in enumerate(child["managed_boundary"]["outcomes"]):
        decision = outcome.get("decision") or {}
        action = decision.get("action")
        response = outcome.get("response") or {}
        result = response.get("result") or {}
        if action not in {
            "replace_file", "write_file", "create_file", "delete_file", "run_tests", "fix_patch",
            "handoff_patch", "integrate_patch", "org_review_patch", "submit_integration",
            "org_sprint_plan", "org_sprint_start", "staff_done",
        }:
            continue
        event = {"outcome_index": index, "worker_id": outcome.get("worker_id"),
            "action": action, "action_performed": outcome.get("action_performed"),
            "model_call_id": decision.get("model_call_id"), "action_id": response.get("action_id"),
            "ok": response.get("ok"), "error": response.get("error"),
            "source_reference": result.get("source_reference"), "patch_id": result.get("patch_id"),
            "paths": result.get("paths"), "files_sha256": result.get("files_sha256")}
        if action == "run_tests":
            event.update({key: result.get(key) for key in (
                "report_id", "executed", "passed", "validation_status", "counts", "test_evidence")})
            # First-page output is evidence only, never the verdict parser.
            event["first_page_excerpt"] = (result.get("page") or {}).get("text", "")[:2100]
        if action == "org_review_patch":
            event["review_record"] = result
            event["review_reason_is_agent_claim_not_external_verdict"] = True
        events.append(event)
    return {"slot_index": row["slot_index"], "instance_id": row["instance_id"],
            "source": ref, "events": events}


def main():
    rows, rows_ref = obj(ROWS)
    summary, summary_ref = obj(SUMMARY)
    s1_rows, s1_ref = obj(S1)
    s1 = {row["instance_id"]: row for row in s1_rows if row["arm"] == "PROJECT"}
    selected = [row for row in rows if row["group"] in {"REVIEW", "SPRINT"}]
    by_index = {row["slot_index"]: row for row in selected}
    failures = []
    for row in selected:
        if row["code_classification"] != "failed":
            continue
        receipt, receipt_ref = obj(row["official_code"]["receipt"]["path"], row["official_code"]["receipt"])
        report = receipt["official_result"][1][row["instance_id"]]
        if (receipt["slot_id"] != row["slot_id"] or report["resolved"] is not False
                or report["patch_successfully_applied"] is not True or report["infra_failure"] is not False):
            raise ValueError("A selected normal code failure changed classification")
        lock, lock_ref = obj(row["official_code"]["candidate_lock"]["path"], row["official_code"]["candidate_lock"])
        patch, patch_ref = read(lock["patch_receipt"]["patch"]["path"], lock["patch_receipt"]["patch"])
        score_dir = Path(receipt_ref["path"]).parent
        files = list(score_dir.rglob("test_output.txt"))
        if len(files) != 1:
            raise ValueError("Expected one retained official test log")
        log, log_ref = read(files[0])
        tests = report["tests_status"]
        failed_ids = tests["FAIL_TO_PASS"]["failure"] + tests["PASS_TO_PASS"]["failure"]
        category = ("unchanged_designated_final_tree" if not patch
                    else "target_fixed_but_existing_behavior_regressed"
                    if not tests["FAIL_TO_PASS"]["failure"] and tests["PASS_TO_PASS"]["failure"]
                    else "target_behavior_still_fails")
        failures.append({"slot_index": row["slot_index"], "slot_id": row["slot_id"],
            "instance_id": row["instance_id"], "group": row["group"],
            "failure_category": category, "actual_tokens": row["actual_tokens"],
            "actual_calls": row["actual_calls"], "S1_passed": row["S1_PROJECT_resolved"],
            "delivery_passed": row["delivery_classification"] == "passed",
            "legal_delivery_evidence": row["legal_delivery_evidence"],
            "tests": {key: {"success_count": len(value["success"]),
                             "failure_count": len(value["failure"]), "failure_ids": value["failure"]}
                      for key, value in tests.items()},
            "official_receipt": receipt_ref, "candidate_lock": lock_ref,
            "candidate_patch": patch_ref, "official_log": log_ref,
            "patch_excerpt": patch.decode("utf-8"),
            "failure_log_sections": failure_sections(log.decode("utf-8"), failed_ids),
            "baseline_equals_terminal_snapshot": lock["baseline"]["sha256"] == lock["candidate"]["sha256"],
            "base_git_tree_equals_candidate": lock["patch_receipt"]["base_git_tree"] == lock["patch_receipt"]["candidate_git_tree"],
            "ordinary_framework_stdout_failures_not_automatically_scoring_failures": True})
    if len(failures) != 10:
        raise ValueError("Expected five REVIEW and five SPRINT failures")
    traces = {str(index): event_summary(by_index[index]) for index in (9037, 9032, 9147, 9128, 9008)}
    prior = s1["pytest-dev__pytest-6197"]
    prior_receipt, prior_ref = obj(prior["score_evidence"]["path"], prior["score_evidence"])
    prior_patch_file = next(Path(prior_ref["path"]).parent.rglob("patch.diff"))
    prior_patch, prior_patch_ref = read(prior_patch_file)
    result = {
        "version": "v137-selected-REVIEW-SPRINT-causes-r1",
        "sources": {"selected_behavior": rows_ref, "selected_summary": summary_ref,
                    "selected_S1": s1_ref, "analysis_source": read(__file__)[1]},
        "groups": {},
        "S1_pytest6197_comparator": {"selected_record": prior, "receipt": prior_ref,
            "resolved": prior_receipt["resolved"], "patch": prior_patch_ref,
            "patch_text": prior_patch.decode("utf-8"),
            "fact": "S1 keeps the __init__.py branch and distinguishes explicit initial paths/package hierarchy; REVIEW removes the blanket __init__.py allowance and regresses Package parent identity, SPRINT only changes yield placement and leaves both target tests failing."},
        "confirmed_interface_observation": {
            "cases": [9037, 9032],
            "fact": "The v130 public-test observer emits unknown_collection when it sees more than one complete framework report. Retained calls show report_count8/2/9/3 in9037 and84/84 in9032; some first-page stdout summaries say passed.",
            "interpretation": "This is a feedback limitation for pytest's nested self-tests, and creates additional interpretation work. The report-count gate is directly observed; the amount of score or token loss it causes has not been measured.",
            "not_claimed": "stdout passed is not substituted for framework evidence; no historical public or official result is rewritten."},
        "case_explanations": {
            "REVIEW": [
                {"slot_index": 9037, "facts": ["Both issue-specific tests pass, but existing test_pkgfile fails: Module parent is Session rather than Package.", "The review accepts patch-1/sourcev5 at outcome62 after10 public-test calls; legal submission succeeds at65, but official evaluation still fails.", "Team81 calls/4,413,798tokens versus S154 calls/3,253,060tokens on the same task."], "inference": "The reviewer did not catch the preserved-package invariant; this case is a code-regression failure despite completion of the delivery protocol, not merely a missing-submit problem."},
                {"slot_index": 9032, "facts": ["Two distinct fixed patches, two handoffs/integrations, five public-test calls and two request_changes reviews precede the token cutoff.", "Review records57/89 request a call-phase guard and then a missing Failed import; those reasons are model assertions, not independent test verdicts.", "The final designated001 candidate passes official evaluation but has no legal submission; team97 calls/4,987,637tokens."], "inference": "Version-specific review can induce additional repair and validation cycles while the delivery endpoint remains unfinished. The observed sequence does not prove both requested changes were necessary for the official criterion."},
                {"slot_index": 9147, "facts": ["SymPy15345 is a new code success relative to S1 and has legal/official delivery.", "One fixed patch/handoff/review/submission and3 public-test calls are recorded; team65 calls/2,762,372tokens versus S1's2,033,162tokens."], "inference": "This is a concrete successful review workflow, but one different attempt does not isolate a causal review benefit. REVIEW's other added success Requests2931 is also affected by the revised public fixture."},
            ],
            "SPRINT": [
                {"slot_index": 9128, "facts": ["001 performs no file modification; final candidate.patch is0bytes and its tree equals baseline.", "002 modifies its private tree throughv8 and obtains two public2/2 passes; both attempts to start Sprint fail, then fixed publication at88 is rejected because the Sprint is not active.", "No handoff/integration/submission occurs; 99calls/4,974,872tokens are consumed."], "inference": "The official failure is on the unchanged designated final tree. The trace shows an unintegrated private implementation, not an absence of coding effort; its hidden-test correctness has not been evaluated."},
                {"slot_index": 9008, "facts": ["Sphinx7889 final001 code passes official evaluation, but no legal delivery exists.", "001v5 public test at81 is7/7 verified; fixed publication at83 is rejected because no Sprint is active.002's publication at64 had the same refusal.", "18 replace_file attempts and8 public-test calls are recorded; 103calls/4,996,282tokens reach the team limit."], "inference": "This is a concrete process barrier after code creation, with additional private revisions. Correct permission enforcement and protocol usability must be distinguished from an implementation crash."},
                {"slot_index": 9043, "facts": ["The patch places the raw-bytes override after _encode_params(data). Official test_binary_put fails inside _encode_params/to_native_string before that override can run.", "The required target failure is a UnicodeDecodeError with non-ASCII bytes, independent of other unscored httpbin errors in the same log.", "102calls/4,995,972tokens and8 public-test attempts do not close this execution-path defect."], "inference": "More coordination and test attempts did not compensate for placing the repair after the failing operation; not every failure is an organization-contract problem."},
            ],
        },
        "boundaries": [
            "The16/11 denominators are the user's valid-score/noncash selected subset, not full50; token cutoffs remain.",
            "REVIEW has11/16 code passes versus matched S110/16, so it is not described as uniformly worse. Added Requests2931 andSymPy15345 are offset by lost pytest6197.",
            "Public run_tests successful responses mean a request executed, not that its tests passed. Only explicit framework verdicts are used in cases.",
            "Official FAIL_TO_PASS/PASS_TO_PASS membership determines the failure classification; additional raw-log failures are not silently added as regressions.",
            "Private peer test success does not establish hidden correctness, and unmerged work is not automatically wasted because messages may transmit useful information.",
            "Token attribution to a tool contains full prompt history, not a marginal causal overhead estimate. Cash-selection, harness and recovery confounds remain.",
        ],
        "resource_operations": {"new_API_calls": 0, "new_model_calls": 0,
            "Docker_operations": 0, "new_tests_or_grading": 0, "archive_reads": 0,
            "bounded_controller_summaries_read": len(traces), "maximum_controller_bytes": max(t["source"]["bytes"] for t in traces.values())},
    }
    for group in ("REVIEW", "SPRINT"):
        rr = [row for row in selected if row["group"] == group]
        agg = summary["groups"][group]["behavior"]
        inputs = outputs = 0
        for row in rr:
            for member in row["members"].values():
                for usage in member["per_usage_id"].values():
                    inputs += usage["prompt_tokens"]
                    outputs += usage["completion_tokens"]
        calls = sum(row["actual_calls"] for row in rr)
        s1_calls = sum(s1[row["instance_id"]]["usage"]["requests"] for row in rr)
        s1_input = sum(s1[row["instance_id"]]["usage"]["known_token_totals"]["input_tokens"] for row in rr)
        result["groups"][group] = {
            "n": len(rr), "code_passed": sum(row["code_classification"] == "passed" for row in rr),
            "delivery_passed": sum(row["delivery_classification"] == "passed" for row in rr),
            "S1_same_tasks_passed": sum(row["S1_PROJECT_resolved"] for row in rr),
            "failure_types": dict(Counter(row["failure_category"] for row in failures if row["group"] == group)),
            "actual_tokens": inputs + outputs, "input_tokens": inputs, "output_tokens": outputs,
            "input_fraction": inputs / (inputs + outputs), "actual_calls": calls,
            "S1_same_tasks_calls": s1_calls, "call_ratio": calls / s1_calls,
            "mean_input_per_call": inputs / calls, "S1_mean_input_per_call": s1_input / s1_calls,
            "condenser_tokens": agg["condenser_tokens"],
            "condenser_fraction": agg["condenser_tokens"] / agg["actual_tokens"],
            "member_roles_and_tokens": summary["groups"][group]["member_role_costs"],
            "operations": agg["tools"], "categories": agg["categories"],
            "coordination_fraction_of_actions": agg["collaboration_action_fraction"],
            "facts": (["Reviewer002 consumes49.76%of team tokens; code lookup, repeated public validation and version-specific review are real work, not free extra votes.",
                       "Two final code passes remain without delivery; successful review tool calls can mean request_changes rather than acceptance."]
                      if group == "REVIEW" else
                      ["All11 selected tasks reach the5M boundary. OnlyFlask5014 starts a Sprint and achieves legal delivery.",
                       "43governance operations include19rejections;13fixed-publication attempts include12rejections;107org_status calls consume real opportunities.",
                       "PO003/SM004 consume27.69%of tokens; developers001/002 consume72.31%. This is role usage, not a pure overhead estimate."]),
            "interpretation": "More API rounds, rather than longer per-call inputs or long outputs, explain the arithmetic increase in total tokens; this decomposition does not assign all extra rounds to coordination.",
        }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (("summary.json", result), ("failed-cases.json", failures), ("case-events.json", traces)):
        path = OUTPUT / name
        if path.exists():
            raise FileExistsError("Preserve previous cause evidence")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": read(OUTPUT / "summary.json")[1],
                      "failure_types": {g: v["failure_types"] for g, v in result["groups"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
