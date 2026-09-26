"""Read-only work evidence diagnostics; never re-run SQL, reward or a model.

Closed episodes are checked against their immutable snapshots/receipts. Original
reward components remain terminal observations, never backdated early labels.
Open/missing episodes and missing reward evidence remain explicitly unknown.
"""

import argparse
import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from proworksim.presentations import response_matches_receipt
from proworksim.storage import digest, json_bytes

VERSION = "learning-work-diagnostics-v0.14"
READS = {"read_alias", "read_version", "read_object"}


def feedback_in_request(events, earlier, later):
    """Exact saved public tool message must occur in a later actual request."""
    if earlier.get("worker_id") != later.get("worker_id"):
        return False
    prior_call = earlier["payload"].get("model_call_id")
    later_call = later["payload"].get("model_call_id")
    if not prior_call or not later_call:
        return False
    messages = [event["payload"].get("message") for event in events
                if event["kind"] == "model_tool_result" and event.get("worker_id") == earlier.get("worker_id")
                and event["sequence"] < later["sequence"] and event["payload"].get("call_id") == prior_call]
    attempts = [event["payload"] for event in events
                if event["kind"] == "model_attempt" and event.get("worker_id") == later.get("worker_id")
                and event["payload"].get("stage") == "finished" and event["payload"].get("status") == "success"
                and event["payload"].get("call_id") == later_call]
    return len(attempts) == 1 and any(message is not None and message in attempts[0].get("request", {}).get("messages", []) for message in messages)


def ref(value):
    if not isinstance(value, dict):
        return None
    oid = value.get("object_id", value.get("artifact_id"))
    vid = value.get("version_id")
    return {"object_id": oid, "version_id": vid} if oid and vid else None


def norm_work(value, project="TEAM"):
    return value if not value or "::" in value else project + "::" + value


def event_result(event):
    value = event["payload"].get("response", {}).get("result")
    return value if isinstance(value, dict) else {}


def pointer(event):
    return {"sequence": event["sequence"], "member": event.get("worker_id"),
            "action": event["payload"]["action"],
            "command_id": event["payload"].get("response", {}).get("command_id"),
            "model_call_id": event["payload"].get("model_call_id")}


def applicable_read(read, period):
    data = read.get("data", {})
    if read["alias"] == "basis":
        table = data.get("tables", {}).get("basis_meta", {})
        rows, columns = table.get("rows", []), table.get("columns", [])
        if len(rows) != 1:
            return False
        metadata = dict(zip([column["name"] for column in columns], rows[0]))
    elif read["alias"] == "audit_basis":
        metadata = data
    else:
        return None
    return metadata.get("edition") == "approved" and metadata.get("period") == period


def diagnose_events(events, start, end, reward, *, document=None):
    """Extract factual relationships after caller verifies the historical files.

    This pure function is also used by explicit offline fixtures. It has no
    environment, evaluator, SQL engine, training function or file write access.
    """
    calls = [event for event in events if event["kind"] == "tool_call" and event["payload"].get("response", {}).get("command_id") not in start.get("operation_commits", {})]
    workspace = end["workspaces"]["TEAM"]
    aliases = {oid: alias for alias, oid in workspace.items()}
    current = {oid: artifact["current_version"] for oid, artifact in start["artifacts"].items()}
    wid = (reward or {}).get("spec", {}).get("work_id", "TEAM::build")
    item = end["work_items"][wid]
    period = start["work_items"][wid]["requirements"].get("reporting_period")
    components = {row["term_id"]: row for row in (reward or {}).get("components", [])}
    reads, writes, builds, submissions, judgments, failures = [], [], [], [], [], []
    inspect_events = []
    initial_submissions = start["work_items"][wid].get("submissions", [])
    fixed = copy.deepcopy(initial_submissions[-1]["artifact_versions"]) if initial_submissions else {}
    all_submissions = {row["submission_id"]: row for row in item.get("submissions", [])}

    def terminal_match(term, event, **identity):
        component = components.get(term)
        if component is None:
            return None
        evidence = component.get("evidence") or {}
        return component.get("achieved") is True and (
            evidence.get("action_sequence") == event["sequence"]
            or bool(identity) and all(evidence.get(k) == value for k, value in identity.items())
        )

    def consumed(read, event):
        return feedback_in_request(events, read["event"], event)

    for event in calls:
        payload = event["payload"]
        action, args = payload["action"], payload.get("arguments", {})
        response, result = payload.get("response", {}), event_result(event)
        ok = response.get("ok") is True
        if not ok or (action in {"sql_build", "sql_query"} and result.get("execution_status") not in {None, "success"}):
            failures.append(event)
        if action == "preflight_submission" and ok and result.get("issues"):
            failures.append(event)
        if not ok:
            continue
        if action in READS:
            reference = ref(result.get("reference"))
            alias = aliases.get((reference or {}).get("object_id"))
            row = {**pointer(event), "reference": reference, "alias": alias, "data": result.get("data", {}), "event": event}
            row["applicable_public_period"] = applicable_read(row, period)
            if event.get("worker_id") == "reviewer" and reference and reference["object_id"] in fixed:
                row["world_fixed_version_at_read"] = fixed[reference["object_id"]]
                row["matches_world_fixed_version_at_read"] = reference["version_id"] == fixed[reference["object_id"]]
            reads.append(row)
        if action == "write_object":
            reference = ref(result)
            if reference is None:
                continue
            oid, vid = reference["object_id"], reference["version_id"]
            prior = current.get(oid)
            versions = end["artifacts"][oid]["versions"]
            prior_sha = versions.get(prior, {}).get("sha256")
            new_sha = versions[vid]["sha256"]
            row = {**pointer(event), "reference": reference, "alias": aliases.get(oid),
                   "prior_version_id": prior, "prior_sha256": prior_sha, "written_sha256": new_sha,
                   "content_changed": prior_sha != new_sha,
                   "basis_reads_preceding": [r["sequence"] for r in reads if r["member"] == event.get("worker_id") and r["alias"] == "basis"],
                   "basis_reads_in_actual_writing_request": [r["sequence"] for r in reads if r["member"] == event.get("worker_id") and r["alias"] == "basis" and consumed(r, event)]}
            row["sql_program_changed"] = None
            if row["alias"] == "code" and document is not None and prior is not None:
                old_code, new_code = document({"object_id": oid, "version_id": prior}), document(reference)
                def sql_program(code):
                    return [{"name": model.get("name"), "sql": model.get("sql")} for model in code.get("models", []) if isinstance(model, dict)]
                row["sql_program_changed"] = sql_program(old_code) != sql_program(new_code)
                row["sql_change_scope"] = "Exact model names/SQL text differ; semantic correctness comes only from saved terminal outcomes."
            writes.append(row)
            current[oid] = vid
        if action == "sql_build":
            reference = ref(result.get("reference"))
            version = end["artifacts"].get((reference or {}).get("object_id"), {}).get("versions", {}).get((reference or {}).get("version_id"), {})
            provenance = version.get("execution_provenance", {})
            code_reference = ref(provenance.get("code_reference"))
            expected_code = {"object_id": workspace["code"], "version_id": current[workspace["code"]]}
            sources = provenance.get("source_references", {})
            authored = [row for row in writes if row["alias"] == "code" and row["content_changed"] and row["reference"] == code_reference]
            row = {**pointer(event), "reference": reference, "work_id": provenance.get("work_id"),
                   "execution_status": result.get("execution_status"), "provenance": copy.deepcopy(provenance),
                   "code_reference": code_reference, "current_code_reference_at_call": expected_code,
                   "executed_current_code": provenance.get("kind") == "sql_build" and code_reference == expected_code,
                   "executed_current_episode_code_edit": bool(authored),
                   "executed_current_episode_sql_change": any(edit["sql_program_changed"] is True for edit in authored),
                   "code_edit_sequences": [edit["sequence"] for edit in authored],
                   "source_references": copy.deepcopy(sources),
                   "required_input_aliases_absent": sorted(set(item["requirements"].get("input_policies", {})) - set(sources)),
                   "basis_read_in_actual_build_request": any(read["alias"] == "basis" and read["member"] == event.get("worker_id") and read["reference"] == ref(sources.get("basis")) and consumed(read, event) for read in reads),
                   "original_terminal_correct_build_component_matches": terminal_match("correct_actual_build", event)}
            builds.append(row)
            if reference:
                current[reference["object_id"]] = reference["version_id"]
        if action in {"submit", "inspect_submission"}:
            fixed = copy.deepcopy(result.get("artifact_versions", fixed))
            if action == "inspect_submission":
                inspect_events.append(event)
            else:
                sid = result.get("submission_id")
                row = {**pointer(event), "submission_id": sid, "artifact_versions": copy.deepcopy(fixed),
                       "original_terminal_correct_submission_component_matches": terminal_match("correct_fixed_submission", event, submission_id=sid),
                       "actual_build_sequences_for_fixed_result_and_code": [build["sequence"] for build in builds if build["reference"] == {"object_id": workspace["result"], "version_id": fixed.get(workspace["result"])} and build["code_reference"] == {"object_id": workspace["code"], "version_id": fixed.get(workspace["code"])}]}
                submissions.append(row)
        if action in {"approve", "raise_issue"}:
            sid = args.get("submission_id")
            sub = all_submissions.get(sid)
            if sub is None:
                continue
            required_refs = [{"object_id": oid, "version_id": vid} for oid, vid in sub["artifact_versions"].items()]
            data_bindings = [binding for binding in sub.get("adoption_snapshot", {}).values() if binding.get("alias") == "data"]
            required_refs.extend(ref(binding) for binding in data_bindings)
            required_refs = [reference for reference in required_refs if reference]
            observed = [read for read in reads if read["member"] == event.get("worker_id") and consumed(read, event)]
            missing = [reference for reference in required_refs if not any(read["reference"] == reference for read in observed)]
            inspections = [earlier for earlier in inspect_events if earlier.get("worker_id") == event.get("worker_id") and event_result(earlier).get("submission_id") == sid and feedback_in_request(events, earlier, event)]
            audits = [read for read in observed if read["alias"] == "audit_basis" and read["applicable_public_period"] is True]
            judgments.append({**pointer(event), "submission_id": sid,
                              "artifact_versions": copy.deepcopy(sub["artifact_versions"]),
                              "required_fixed_references": required_refs, "missing_consumed_fixed_references": missing,
                              "actual_consumed_read_sequences": [read["sequence"] for read in observed],
                              "actual_consumed_inspect_sequences": [earlier["sequence"] for earlier in inspections],
                              "actual_consumed_applicable_audit_sequences": [read["sequence"] for read in audits],
                              "evidence_complete_before_action": bool(inspections and audits and not missing and data_bindings),
                              "original_terminal_supported_review_component_matches": terminal_match("correct_review_decision", event)})

    repairs = []
    for failure in failures:
        payload, result = failure["payload"], event_result(failure)
        error = payload.get("response", {}).get("error", {})
        work = norm_work(payload.get("arguments", {}).get("work_id"))
        candidates = [event for event in calls if event["sequence"] > failure["sequence"] and event.get("worker_id") == failure.get("worker_id") and feedback_in_request(events, failure, event)]
        row = {**pointer(failure), "error": copy.deepcopy(error or result.get("error") or result.get("issues")),
               "later_action_sequences_with_actual_feedback": [event["sequence"] for event in candidates],
               "repairs": [], "status": "no_verified_specific_obligation_repair"}
        match = re.search(r"SQL input requires this work's exact adoption: ([A-Za-z0-9_]+)", error.get("message", ""))
        missing = [match.group(1)] if match else []
        missing.extend(issue["source_alias"] for issue in result.get("issues", []) if issue.get("code") == "missing_work_adoption" and issue.get("source_alias"))
        for alias in sorted(set(missing)):
            adopted = [event for event in candidates if event["payload"]["action"] == "adopt" and event["payload"].get("response", {}).get("ok") and event_result(event).get("alias") == alias and event_result(event).get("work_id") == work]
            for adoption in adopted:
                reference = ref(event_result(adoption))
                resumed = next((build for build in builds if build["sequence"] > adoption["sequence"] and build["member"] == failure.get("worker_id") and build["work_id"] == work and build["execution_status"] == "success" and ref(build["source_references"].get(alias)) == reference and any(event["sequence"] == build["sequence"] for event in candidates)), None)
                if resumed:
                    row["repairs"].append({"kind": "adoption_obligation_then_actual_execution", "alias": alias, "reference": reference,
                                           "adoption_sequence": adoption["sequence"], "execution_sequence": resumed["sequence"],
                                           "scope": "Specific structural prerequisite restored. This does not imply all inputs or business correctness."})
                    break
        if result.get("execution_status") not in {None, "success"}:
            edited = [write for write in writes if write["sequence"] > failure["sequence"] and write["alias"] == "code" and write["content_changed"] and any(event["sequence"] == write["sequence"] for event in candidates)]
            for edit in edited:
                resumed = next((build for build in builds if build["sequence"] > edit["sequence"] and build["work_id"] == work and build["execution_status"] == "success" and build["code_reference"] == edit["reference"] and any(event["sequence"] == build["sequence"] for event in candidates)), None)
                if resumed:
                    row["repairs"].append({"kind": "changed_code_then_actual_execution", "code_reference": edit["reference"], "code_edit_sequence": edit["sequence"], "execution_sequence": resumed["sequence"], "scope": "Execution recovery only, not independently correct business work."})
                    break
        if row["repairs"]:
            row["status"] = "verified_specific_obligation_repair"
        row["same_operation_later_accepted_sequences"] = [event["sequence"] for event in candidates if event["payload"]["action"] == payload["action"] and event["payload"].get("response", {}).get("ok")]
        repairs.append(row)
    distinct_repairs = {
        (repair["kind"], repair.get("alias"), repair.get("adoption_sequence", repair.get("code_edit_sequence")), repair["execution_sequence"])
        for row in repairs for repair in row["repairs"]
    }
    public_reads = [{k: v for k, v in read.items() if k not in {"data", "event"}} for read in reads]
    return {"reads": public_reads, "writes": writes, "builds": builds, "submissions": submissions,
            "review_judgments": judgments, "feedback_obligation_repairs": repairs,
            "original_terminal_components": copy.deepcopy((reward or {}).get("components")),
            "summary": {"implementer_actually_read_basis": any(row["member"] == "implementer" and row["alias"] == "basis" for row in reads),
                        "implementer_read_applicable_basis": any(row["member"] == "implementer" and row["alias"] == "basis" and row["applicable_public_period"] is True for row in reads),
                        "reviewer_read_fixed_code": any(row["member"] == "reviewer" and row["alias"] == "code" and row.get("matches_world_fixed_version_at_read") is True for row in reads),
                        "reviewer_read_fixed_result": any(row["member"] == "reviewer" and row["alias"] == "result" and row.get("matches_world_fixed_version_at_read") is True for row in reads),
                        "reviewer_read_applicable_audit": any(row["member"] == "reviewer" and row["alias"] == "audit_basis" and row["applicable_public_period"] is True for row in reads),
                        "evidence_complete_before_actual_judgment": any(row["evidence_complete_before_action"] for row in judgments),
                        "changed_code": any(row["alias"] == "code" and row["content_changed"] for row in writes),
                        "changed_sql_program": any(row["sql_program_changed"] is True for row in writes) if document is not None else None,
                        "manual_result_write": any(row["alias"] == "result" for row in writes),
                        "executed_current_episode_code_edit": any(row["execution_status"] == "success" and row["executed_current_episode_code_edit"] for row in builds),
                        "executed_current_episode_sql_change": any(row["execution_status"] == "success" and row["executed_current_episode_sql_change"] for row in builds),
                        "correct_build_original_term": components.get("correct_actual_build", {}).get("achieved"),
                        "correct_fixed_submission_original_term": components.get("correct_fixed_submission", {}).get("achieved"),
                        "supported_review_original_term": components.get("correct_review_decision", {}).get("achieved"),
                        "specific_feedback_obligation_repairs": len(distinct_repairs),
                        "failed_actions_later_matching_specific_repair": sum(bool(row["repairs"]) for row in repairs)}}


def diagnose_episode(path):
    root = Path(path).resolve()
    if root.name == "manifest.json":
        root = root.parent
    if (root / "episode").is_dir():
        root = root / "episode"
    row = {"episode_path": str(root), "status": "unknown", "reason": None}
    try:
        raw = (root / "manifest.json").read_bytes()
        manifest = json.loads(raw)
        row.update(episode_id=manifest.get("episode_id"), manifest_sha256=digest(raw))
        if manifest.get("status") != "closed":
            row["reason"] = "episode_not_closed"
            return row

        def checked(path, sha):
            data = path.read_bytes()
            if digest(data) != sha:
                raise ValueError("Immutable evidence hash differs: " + str(path))
            return json.loads(data)

        experience = manifest["experience"]
        history = checked(root / experience["path"], experience["sha256"])
        events = history["events"][experience["start"]:experience["end"]]
        states = {phase: checked(root / manifest[phase]["path"] / manifest[phase]["state"]["path"], manifest[phase]["state"]["sha256"]) for phase in ("start", "end")}
        for event in events:
            if event["kind"] != "tool_call":
                continue
            payload = event["payload"]
            response = payload.get("response", {})
            commit = states["end"]["operation_commits"].get(response.get("command_id"))
            if not commit or commit.get("bound_actor") != event.get("worker_id") or not response_matches_receipt(commit, response, action=payload["action"], arguments=payload.get("arguments")):
                raise ValueError("Actual tool event does not bind its real world receipt")
        reward = None
        rollout_path = root.parent / "team-rollout.json"
        reward_path = root.parent / "reward.json"
        if rollout_path.exists():
            rollout = json.loads(rollout_path.read_bytes())
            if rollout.get("manifest_sha256") != row["manifest_sha256"] or rollout.get("events") != events:
                raise ValueError("Saved TeamRollout does not identify this exact episode")
            reward = rollout.get("reward_eligibility")
        elif reward_path.exists():
            reward = json.loads(reward_path.read_bytes())
        if reward is not None and (reward.get("manifest_sha256") != row["manifest_sha256"] or reward.get("episode_id") != manifest["episode_id"]):
            raise ValueError("Saved reward does not identify this exact episode")
        if reward is not None and not reward.get("eligible"):
            reward = None
        version_files = {(entry["object_id"], entry["version_id"]): entry for entry in manifest["end"]["files"]}
        cache = {}
        def document(reference):
            key = (reference["object_id"], reference["version_id"])
            if key not in cache:
                entry = version_files[key]
                cache[key] = checked(root / manifest["end"]["path"] / entry["path"], entry["sha256"])
            return cache[key]
        case = manifest.get("scenario", {}).get("variation", {}).get("online_case", {})
        row.update(status="closed_verified", reason=None, case_id=case.get("case_id"), task=case.get("task"),
                   policy_identities=copy.deepcopy(manifest.get("policies")),
                   original_reward_status="available" if reward is not None else "unknown",
                   original_reward=copy.deepcopy(reward), event_interval=copy.deepcopy(experience),
                   work=diagnose_events(events, states["start"], states["end"], reward, document=document))
    except (OSError, ValueError, KeyError, TypeError) as error:
        row.update(status="unknown", reason=type(error).__name__ + ": " + str(error))
    return row


def build_report(episodes):
    rows = [diagnose_episode(path) for path in episodes]
    groups = defaultdict(Counter)
    for row in rows:
        group = groups[row.get("task") or "unknown"]
        group["scheduled_or_requested_episodes"] += 1
        group[row["status"]] += 1
        if row["status"] == "closed_verified":
            for key, value in row["work"]["summary"].items():
                if type(value) is bool:
                    group[key + ":true"] += value
                    group[key + ":observed"] += 1
                elif type(value) is int:
                    group[key] += value
    return {"version": VERSION, "analysis_script_sha256": digest(Path(__file__).read_bytes()), "episodes": rows, "task_counts": dict(groups),
            "scope": "Read-only factual diagnosis from closed original events, immutable states and world receipts. No SQL/model/reward/validity re-evaluation. Original terminal quality is reported separately from earlier factual actions; structural feedback recovery is not business success.",
            "unknown_rule": "Open/missing/corrupt episodes remain unknown; absent or ineligible original reward creates unknown terminal outcomes, not zero reward."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", action="append", default=[], type=Path)
    parser.add_argument("--run", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    episodes = list(args.episode)
    for run in args.run:
        protocol = json.loads((run / "online/protocol.json").read_bytes())
        for wi, window in enumerate(protocol["windows"]):
            episodes.extend(run / f"online/window-{wi}/collection/slot-{si}/episode" for si in range(len(window["slots"])))
    if not episodes:
        parser.error("Supply at least one episode or run")
    result = build_report(episodes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as file:
        file.write(json_bytes(result))
    print(json.dumps({"episodes": len(episodes), "statuses": dict(Counter(row["status"] for row in result["episodes"]))}))


if __name__ == "__main__":
    main()
