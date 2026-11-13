"""Read-only natural collaboration audit of the twelve sealed v203.2.1 runs.

No model, Docker, grading, replay, or old-file writes. Window selection is the
mechanical rule below and never consumes official scores. Request presentation
is read from original SQLite MODEL_REQUEST wire.messages, not inferred from
send success. Full-conversation storage is referenced, not duplicated.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import time

import analyze_passive_mechanisms_v203_2_1 as prior


ROOT = prior.ROOT
OUT = ROOT / "artifacts/software-benchmark-v203-2-2/natural-audit-r1"
SCHEMA = "v203.2.2-natural-collaboration-r1"
WINDOW_RULE = {
    "version": "v203.2.2-all-natural-trigger-receipts-r1",
    "selection_inputs": "original executor receipts and opportunities only; no grading or final outcome input",
    "triggers": ["successful_send_message", "successful_handoff_patch", "integration_reporting_conflict",
                 "successful_org_review_patch", "executed_failed_public_test", "first_team_budget_gate_per_episode"],
    "cutoff": "inclusive triggering receipt sequence; budget uses first team_budget_exhausted opportunity sequence",
    "merge": "same episode and same cutoff sequence only",
    "communication_target": "recipient; sending is global evidence, not proof of receiver presentation",
    "review_target": "original patch author; recorded review is global evidence until presented",
    "context": "latest original request of target actor at or before cutoff, plus own tool receipts since that request",
    "future_exclusion": "no subsequent request, model output, action, test, score, terminal state or prior audit label",
    "prior_context_rule": "last five target-actor receipts plus last own test/version mutation and named published candidate",
    "unknown_policy": "missing original presentation or semantic use stays unknown; no inferred organizational label",
    "expected_trigger_count_before_same_cutoff_merge": 108,
}
OBS_KEYS = ("actor_id", "logical_time", "workspace_reference", "patches", "all_fixed_patches",
            "included_patch_ids", "messages", "handoffs", "older_message_sequences", "older_handoff_sequences",
            "current_version_test_coverage", "shared_resource_limits", "team_test_budget", "team_model_budget",
            "fixed_organization", "organization_protocol", "member_availability", "delivery_status", "tasks")
MUTATIONS = {"write_file", "replace_file", "create_file", "delete_file", "rename_file", "integrate_patch"}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for value in values:
            stream.write(dump(value) + "\n")


def source(row, path):
    return {"journal": str(path), "sequence": row["sequence"], "event_key": row["key"],
            "capture_time": row.get("source", {}).get("capture_time"),
            "record_sha256": row["record_sha256"], "chain_sha256": row["chain_sha256"]}


def result(event):
    value = event.get("payload", {}).get("response", {}).get("result")
    return value if isinstance(value, dict) else {}


def ok(event):
    return event.get("payload", {}).get("response", {}).get("ok") is True


def actor(event):
    return event.get("payload", {}).get("actor") or event.get("payload", {}).get("worker_id")


def tool(event):
    return event.get("payload", {}).get("tool")


def brief(event):
    if event is None:
        return None
    p, r = event["payload"], result(event)
    if tool(event) in {"run_tests", "read_test_result"} and isinstance(r.get("test_evidence"), dict):
        r = dict(r)
        evidence = dict(r["test_evidence"])
        sessions = []
        for session in evidence.get("sessions", []):
            session = dict(session)
            reports = session.pop("test_reports", [])
            failed = [item for item in reports if item.get("outcome") in {"failed", "error"}]
            session["first_failed_reports"] = failed[:12]
            session["omitted_test_report_count"] = len(reports) - min(12, len(failed))
            session["all_original_reports_source"] = event["source_reference"]
            sessions.append(session)
        evidence["sessions"] = sessions
        r["test_evidence"] = evidence
    return {"source": event["source_reference"], "actor": actor(event), "tool": tool(event),
            "arguments": p.get("arguments"), "ok": p.get("response", {}).get("ok"),
            "result": r, "error": p.get("response", {}).get("error"),
            "decision_id": p.get("association", {}).get("decision_id")}


def version(event):
    r = result(event)
    return {key: r.get(key) for key in ("source_reference", "files_sha256", "entry_metadata_sha256")}


def same_content(a, b):
    keys = ("files_sha256", "entry_metadata_sha256")
    if not all(a.get(k) and b.get(k) for k in keys):
        return None
    return all(a[k] == b[k] for k in keys)


def test_identity(event, receipts):
    """Recover omitted test metadata only from an exact earlier workspace ID/hash."""
    identity = version(event)
    if not identity["entry_metadata_sha256"]:
        support = next((e for e in reversed(receipts) if e["sequence"] < event["sequence"]
            and result(e).get("source_reference") == identity["source_reference"]
            and result(e).get("files_sha256") == identity["files_sha256"]
            and result(e).get("entry_metadata_sha256")), None)
        if support:
            identity["entry_metadata_sha256"] = result(support)["entry_metadata_sha256"]
            identity["entry_metadata_source"] = support["source_reference"]
    return identity


def request_context(row, accepted):
    p = row["payload"]
    messages = p.get("wire", {}).get("messages", [])
    observations = []
    for index, message in enumerate(messages):
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        try:
            value = json.loads(message["content"])
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("observation"), dict):
            observations.append((index, value))
    index, latest = observations[-1] if observations else (None, {})
    observation = latest.get("observation", {})
    binding = accepted.get(p.get("request_id"), {})
    presentation_entries = []
    for message_index, value in observations:
        for key in ("messages", "handoffs"):
            for item_index, item in enumerate(value["observation"].get(key, [])):
                presentation_entries.append({"message_index": message_index, "current_observation": message_index == index,
                    "json_path": f"messages[{message_index}].content.observation.{key}[{item_index}]",
                    "kind": key, "entry": item})
    return {"source": row["source_reference"], "actor": p.get("member_id"),
            "request_id": p.get("request_id"), "decision_id": binding.get("decision_id"),
            "request_sha256_from_verified_physical_join": binding.get("request_sha256"),
            "physical_id": binding.get("physical_id"), "prompt_upper_bound": p.get("prompt_upper_bound"),
            "latest_observation_message_index": index, "wire_message_count": len(messages),
            "role_task": latest.get("role_task"),
            "observation": {k: observation[k] for k in OBS_KEYS if k in observation},
            "presentation_entries": presentation_entries,
            "complete_original_wire_present": bool(messages),
            "current_observation_parsed": bool(observations)}


def communication_presentation(event, requests, receipts):
    p, r = event["payload"], result(event)
    handoff = tool(event) == "handoff_patch"
    sequence = r.get("handoff_sequence" if handoff else "message_sequence")
    recipient = r.get("recipient")
    body = p["arguments"].get("message" if handoff else "body", "")
    presentations = []
    for request in requests:
        if request["actor"] != recipient or request["source"]["sequence"] <= event["sequence"]:
            continue
        entries = [entry for entry in request["presentation_entries"]
                   if entry["entry"].get("sequence") == sequence
                   and entry["kind"] == ("handoffs" if handoff else "messages")]
        if not entries:
            continue
        entry = next((e for e in entries if e["current_observation"]), entries[-1])
        visible = entry["entry"].get("message" if handoff else "body", "")
        if not visible:
            visible = entry["entry"].get("preview", "")
        presentations.append({"request_source": request["source"], "decision_id": request["decision_id"],
            "request_sha256": request["request_sha256_from_verified_physical_join"],
            **entry, "original_body_characters": len(body), "presented_body_characters": len(visible),
            "full_body_presented_in_this_entry": visible == body,
            "original_body_starts_with_presented_text": body.startswith(visible) if visible else None})
    explicit_reads = [brief(e) for e in receipts if actor(e) == recipient and tool(e) == "read_work_event"
                      and result(e).get("sequence") == sequence and e["sequence"] > event["sequence"]]
    first = presentations[0] if presentations else None
    after = [brief(e) for e in receipts if actor(e) == recipient
             and first and e["sequence"] > first["request_source"]["sequence"]][:3]
    return {"recipient": recipient, "work_event_sequence": sequence,
            "sent_body": body, "sent_body_sha256": sha(body),
            "actual_presentation_status": "observed_original_request" if first else "unknown_no_recipient_request_entry_found",
            "first_actual_presentation": first,
            "requests_containing_event_count": len(presentations),
            "any_full_body_observation_entry": any(p["full_body_presented_in_this_entry"] for p in presentations),
            "explicit_body_reads": explicit_reads, "next_three_recipient_tool_receipts": after,
            "semantic_use": "unknown; visibility and temporal succession do not establish comprehension or causal use"}


def first_patch_presentation(patch_id, recipient, requests, publication_sequence):
    for request in requests:
        if request["actor"] != recipient or request["source"]["sequence"] <= publication_sequence:
            continue
        for index, patch in enumerate(request["observation"].get("patches", [])):
            if patch.get("patch_id") == patch_id:
                return {"request_source": request["source"], "decision_id": request["decision_id"],
                        "json_path": f"messages[{request['latest_observation_message_index']}].content.observation.patches[{index}]",
                        "presented_patch_metadata": patch}
    return None


def make_chains(case, receipts, requests, gates):
    chains = []
    publications = {result(e)["patch_id"]: e for e in receipts if tool(e) == "fix_patch" and ok(e) and result(e).get("patch_id")}
    integrations = [e for e in receipts if tool(e) == "integrate_patch"]
    tests = [e for e in receipts if tool(e) == "run_tests" and result(e).get("executed") is True]
    reviews = [e for e in receipts if tool(e) == "org_review_patch" and ok(e)]
    deliveries = [e for e in receipts if tool(e) == "submit_integration" and ok(e)]
    for event in receipts:
        if tool(event) not in {"send_message", "handoff_patch"} or not ok(event):
            continue
        presentation = communication_presentation(event, requests, receipts)
        chain = {"chain_type": "A_handoff_information_adoption" if tool(event) == "handoff_patch" else "message_presentation_boundary",
                 "task_id": case, "anchor": brief(event), "communication": presentation}
        if tool(event) == "handoff_patch":
            patch_id = result(event)["patch_id"]
            publication = publications.get(patch_id)
            matched = [e for e in integrations if e["payload"]["arguments"].get("patch_id") == patch_id
                       and actor(e) == presentation["recipient"]]
            reads = [e for e in receipts if tool(e) == "read_file" and actor(e) == presentation["recipient"]
                     and e["payload"]["arguments"].get("patch_id") == patch_id]
            chain.update(patch_id=patch_id, publication=brief(publication),
                first_recipient_patch_metadata_presentation=first_patch_presentation(patch_id, presentation["recipient"], requests,
                                                                                     publication["sequence"] if publication else 0),
                explicit_published_file_reads=[brief(e) for e in reads], integrations=[])
            for integrated in matched:
                subsequent = [t for t in tests if actor(t) == actor(integrated) and t["sequence"] > integrated["sequence"]]
                next_integration = next((e["sequence"] for e in integrations if actor(e) == actor(integrated)
                                        and e["sequence"] > integrated["sequence"]), float("inf"))
                subsequent = [t for t in subsequent if t["sequence"] < next_integration]
                chain["integrations"].append({"receipt": brief(integrated),
                    "relative_to_handoff": "before" if integrated["sequence"] < event["sequence"] else "after",
                    "outcome": "committed_with_conflicts" if result(integrated).get("conflict_count") else "committed_clean" if ok(integrated) else "rejected",
                    "same_content_as_published_at_integration": same_content(result(integrated), result(publication)) if publication else None,
                    "subsequent_test_version_evidence": [{"test": brief(t), "test_identity": test_identity(t, receipts),
                        "same_content_as_integration": same_content(test_identity(t, receipts), result(integrated)),
                        "same_content_as_published": same_content(test_identity(t, receipts), result(publication)) if publication else None}
                        for t in subsequent],
                    "review_receipts": [brief(r) for r in reviews if r["payload"]["arguments"].get("patch_id") == patch_id]})
            chain["adoption_observed"] = bool(matched)
            chain["handoff_caused_adoption"] = "unknown; an adoption before handoff explicitly contradicts that ordering"
        chains.append(chain)
    for integrated in integrations:
        if not result(integrated).get("conflict_count"):
            continue
        patch_id = integrated["payload"]["arguments"]["patch_id"]
        publication = publications[patch_id]
        paths = result(integrated)["conflicts"]
        later = [e for e in receipts if actor(e) == actor(integrated) and e["sequence"] > integrated["sequence"]]
        next_integrate = next((e["sequence"] for e in later if tool(e) == "integrate_patch"), float("inf"))
        later = [e for e in later if e["sequence"] < next_integrate]
        reads, edits, fragments = [], [], []
        read_pages = []
        for e in later:
            args, r = e["payload"].get("arguments", {}), result(e)
            if args.get("path") not in paths:
                continue
            if tool(e) in {"read_file", "search_file"}:
                reads.append(brief(e))
            if tool(e) == "read_file" and isinstance(r.get("text"), str) and isinstance(r.get("start_character"), int):
                read_pages.append((args.get("path"), r.get("source_reference"), r["start_character"], r["text"], e["source_reference"]))
            if tool(e) in MUTATIONS and ok(e):
                edits.append(brief(e))
            text = r.get("text", "") if tool(e) == "read_file" else args.get("old", "") if tool(e) == "replace_file" else ""
            for block in re.findall(r"<<<<<<< working-copy\n.*?>>>>>>> incoming-patch", text, re.S):
                if not any(item["text"] == block for item in fragments):
                    fragments.append({"source": e["source_reference"], "path": args.get("path"), "text": block})
        # A conflict may span two overlapping original read_file pages. Merge
        # only equal immutable source versions with byte-for-character overlap.
        merged_pages = []
        for path, ref, start, text, src in sorted(read_pages, key=lambda x: (x[0], dump(x[1]), x[2])):
            previous = merged_pages[-1] if merged_pages else None
            if previous and (previous["path"], previous["version"]) == (path, ref) and start <= previous["start"] + len(previous["text"]):
                offset = start - previous["start"]
                overlap = min(len(previous["text"]) - offset, len(text))
                assert previous["text"][offset:offset + overlap] == text[:overlap]
                previous["text"] += text[overlap:]
                previous["sources"].append(src)
            else:
                merged_pages.append({"path": path, "version": ref, "start": start, "text": text, "sources": [src]})
        for page in merged_pages:
            for block in re.findall(r"<<<<<<< working-copy\n.*?>>>>>>> incoming-patch", page["text"], re.S):
                if not any(item["text"] == block for item in fragments):
                    fragments.append({"sources": page["sources"], "path": page["path"], "text": block,
                                      "recovery": "joined overlapping original read pages of identical immutable version"})
        resolution = next((e for e in later if tool(e) in MUTATIONS and ok(e)
                           and same_content(result(e), result(publication)) is True), None)
        post_tests = [e for e in later if tool(e) == "run_tests" and result(e).get("executed") is True]
        chains.append({"chain_type": "B_conflict_handling_recovery", "task_id": case,
            "anchor": brief(integrated), "patch_id": patch_id, "publication": brief(publication),
            "conflict_mechanism": "committed three-way content merge with working-copy/frozen-base/incoming-patch markers; not a rejected request",
            "conflict_paths": paths, "exact_conflict_blocks": fragments,
            "prior_local_mutations_on_conflict_paths": [brief(e) for e in receipts if e["sequence"] < integrated["sequence"]
                and actor(e) == actor(integrated) and tool(e) in MUTATIONS and ok(e)
                and (e["payload"].get("arguments", {}).get("path") in paths
                     or any(path in result(e).get("paths", []) for path in paths))][-5:],
            "exact_cause_status": "original conflicting texts recovered" if fragments else "unknown_original_conflict_text_not_read",
            "followup_reads": reads, "followup_edits": edits,
            "replacement_consumed_prefixes_before_conflict_marker": [{"source": e["source"],
                "path": e["arguments"].get("path"),
                "original_prefix": e["arguments"]["old"].split("<<<<<<< working-copy", 1)[0],
                "replacement_text": e["arguments"].get("new"),
                "meaning": "literal replacement also consumed this pre-marker prefix; not inferred from later test outcome"}
                for e in edits if "<<<<<<< working-copy" in e["arguments"].get("old", "")
                and e["arguments"]["old"].split("<<<<<<< working-copy", 1)[0].strip()
                and not e["arguments"].get("new", "").startswith(e["arguments"]["old"].split("<<<<<<< working-copy", 1)[0])],
            "first_restored_published_content": brief(resolution),
            "subsequent_tests": [{"test": brief(e), "test_identity": test_identity(e, receipts),
                                  "same_content_as_published": same_content(test_identity(e, receipts), result(publication))}
                                 for e in post_tests],
            "subsequent_reviews": [brief(e) for e in later if tool(e) == "org_review_patch"],
            "organizational_cause": "not_assessed"})
    for review in reviews:
        r = result(review)
        patch_id = r.get("patch_id")
        publication = publications.get(patch_id)
        ev = r.get("test_evidence") or {}
        matching_tests = [e for e in tests if actor(e) == actor(review) and e["sequence"] < review["sequence"]
                          and result(e).get("source_reference") == ev.get("source_reference")
                          and result(e).get("files_sha256") == ev.get("files_sha256")]
        later_deliveries = [e for e in deliveries if e["sequence"] > review["sequence"]]
        author = r.get("author")
        later_versions = [e for e in receipts if actor(e) == author and e["sequence"] > review["sequence"]
                          and tool(e) in MUTATIONS and ok(e)]
        chains.append({"chain_type": "C_review_rework_delivery", "task_id": case, "anchor": brief(review),
            "patch_id": patch_id, "publication": brief(publication),
            "review_identity": r.get("identity"), "adopted_source_reference": r.get("adopted_source_reference"),
            "review_reason_is_actor_claim": True, "reason": r.get("reason"), "decision": r.get("decision"),
            "rework_responsible": r.get("rework_responsible"),
            "reviewed_content_matches_publication": same_content(r.get("identity", {}), result(publication)) if publication else None,
            "test_content_matches_publication": same_content(ev, result(publication)) if publication else None,
            "same_actor_same_version_original_test_receipts": [brief(e) for e in matching_tests],
            "latest_reviewer_test_before_review": next(({"test": brief(e), "test_identity": test_identity(e, receipts),
                "same_content_as_reviewed_patch": same_content(test_identity(e, receipts), r.get("identity", {}))}
                for e in reversed(tests) if actor(e) == actor(review) and e["sequence"] < review["sequence"]), None),
            "subsequent_author_mutations": [brief(e) for e in later_versions],
            "subsequent_deliveries": [{"delivery": brief(e), "same_content_as_reviewed": same_content(result(e), r.get("identity", {}))}
                                      for e in later_deliveries],
            "official_score": "not_read"})
    for gate in gates[:1]:
        before = [r for r in requests if r["source"]["sequence"] < gate["sequence"] and r["decision_id"] and r["current_observation_parsed"]]
        last_by_actor = {r["actor"]: r for r in before}
        chains.append({"chain_type": "D_budget_decision_stop", "task_id": case,
            "anchor": {"source": gate["source_reference"], "payload": gate["payload"]},
            "last_presented_budgets": [{"actor": r["actor"], "request_source": r["source"],
                "budget": r["observation"].get("team_model_budget"), "workspace_reference": r["observation"].get("workspace_reference")}
                for r in last_by_actor.values()],
            "last_five_receipts_before_gate": [brief(e) for e in receipts if e["sequence"] < gate["sequence"]][-5:],
            "receipts_after_gate": [brief(e) for e in receipts if e["sequence"] > gate["sequence"]],
            "interpretation": "reservation/admission boundary, not proof budget alone caused task outcome", "official_score": "not_read"})
    for index, chain in enumerate(chains, 1):
        chain.update(schema=SCHEMA, chain_id=f"{case}:chain:{index:03}")
    return chains


def triggers(event):
    if event["kind"] != "RECEIPT":
        return []
    if tool(event) == "run_tests" and result(event).get("executed") is True and result(event).get("passed") is False:
        return ["executed_failed_public_test"]
    if not ok(event):
        return []
    if tool(event) in {"send_message", "handoff_patch", "org_review_patch"}:
        return ["successful_" + tool(event)]
    if tool(event) == "integrate_patch" and result(event).get("conflict_count"):
        return ["integration_reporting_conflict"]
    return []


def make_windows(case, events, receipts, requests, gates, initial):
    windows = []
    anchors = [(e, triggers(e)) for e in receipts if triggers(e)]
    anchors += [(e, ["first_team_budget_gate_per_episode"]) for e in gates[:1]]
    for event, kinds in sorted(anchors, key=lambda x: x[0]["sequence"]):
        cutoff = event["sequence"]
        r = result(event)
        target = r.get("recipient") if tool(event) in {"send_message", "handoff_patch"} else r.get("author") if tool(event) == "org_review_patch" else actor(event)
        context = next((q for q in reversed(requests) if q["actor"] == target and q["source"]["sequence"] <= cutoff
                        and q["decision_id"] and q["current_observation_parsed"]), None)
        window_id = f"{case}:s{cutoff:04}"
        stem = window_id.replace(":", "--")
        before = [e for e in receipts if actor(e) == target and e["sequence"] <= cutoff]
        selected = before[-5:]
        for category in ({"run_tests"}, MUTATIONS):
            last = next((e for e in reversed(before) if tool(e) in category), None)
            if last and last not in selected:
                selected.append(last)
        # Publication metadata is included only if actually in this actor's request.
        local = None if context is None else {k: context[k] for k in
            ("source", "actor", "request_id", "decision_id", "request_sha256_from_verified_physical_join",
             "latest_observation_message_index", "role_task", "observation", "complete_original_wire_present")}
        prefix_refs = [{"kind": e["kind"], "source": e["source_reference"]} for e in events if e["sequence"] <= cutoff]
        prefix_path = OUT / "blind-review-packets/prefix-indexes" / (stem + ".jsonl")
        write_jsonl(prefix_path, prefix_refs)
        packet = {"schema": SCHEMA, "window_id": window_id, "task_id": case,
            "trigger_kinds": kinds, "target_actor": target, "cutoff": event["source_reference"],
            "exposure_boundary": "inclusive anchor only; no post-cutoff action/outcome or prior audit assessment supplied",
            "global_trigger_fact": brief(event) if event["kind"] == "RECEIPT" else {"source": event["source_reference"], "payload": event["payload"]},
            "trigger_visibility_to_target": "own tool receipt" if actor(event) == target else "global event; do not assume recipient has seen it at this cutoff",
            "latest_actual_target_request": local,
            "target_actor_recent_receipts": [brief(e) for e in sorted(selected, key=lambda e: e["sequence"])],
            "target_receipts_after_latest_request": [brief(e) for e in before if context and e["sequence"] > context["source"]["sequence"]],
            "initial_role_contract": initial["payload"].get("organization"),
            "initial_public_issue": initial["payload"].get("public_initial_message") if not context else None,
            "prefix_source_index": {"path": str(prefix_path.relative_to(OUT)), "rows": len(prefix_refs),
                                    "maximum_sequence": cutoff, "sha256": sha(prefix_path.read_bytes())},
            "reviewer_instruction": "Judge only evidence available by cutoff. Separate global occurrence from actor presentation. Do not infer not-read from missing explicit read. Public-test outcomes are contemporaneous evidence, never official scores. No labels have been supplied."}
        packet_path = OUT / "blind-review-packets" / (stem + ".json")
        write_json(packet_path, packet)
        # Check all original-source references in the packet, not only selected rows.
        def assert_boundary(value):
            if isinstance(value, dict):
                if "journal" in value and "record_sha256" in value:
                    assert value["sequence"] <= cutoff
                for item in value.values():
                    assert_boundary(item)
            elif isinstance(value, list):
                for item in value:
                    assert_boundary(item)
        assert_boundary(packet)
        windows.append({"schema": SCHEMA, "window_id": window_id, "task_id": case,
            "trigger_kinds": kinds, "target_actor": target, "cutoff": event["source_reference"],
            "selection_rule": WINDOW_RULE["version"], "context_request_source": context["source"] if context else None,
            "packet_path": str(packet_path.relative_to(OUT)), "packet_sha256": sha(packet_path.read_bytes()),
            "prefix_index_path": str(prefix_path.relative_to(OUT)), "annotation": None})
    return windows


def analyze_one(path, decoder):
    measurement = json.loads(path.read_bytes())
    episode = measurement["episode_id"]
    case = episode.split(":")[1]
    journal = Path(measurement["sidecar_journal"]["path"])
    selected, proof = prior.selected_observations(journal, measurement["sidecar_journal"], decoder)
    selected_by_seq = {r["sequence"]: r for r in selected}
    accepted = {r["request_id"]: r for r in measurement["accepted_requests"]}
    events, requests, gates = [], [], []
    with sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for raw in db.execute("SELECT * FROM observations ORDER BY sequence"):
            row = selected_by_seq.get(raw["sequence"])
            if row is None:
                row = decoder(raw)
            row["source_reference"] = source(row, journal)
            row["task_id"], row["episode_id"] = case, episode
            p = row["payload"]
            if row["kind"] == "MODEL_REQUEST":
                request = request_context(row, accepted)
                requests.append(request)
                row["payload"] = {k: request[k] for k in request if k not in {"presentation_entries", "role_task"}}
            elif row["kind"] == "MODEL_RESPONSE":
                row["payload"] = {"actor": p.get("actor"), "request_id": p.get("request_id"),
                                  "usage": p.get("body", {}).get("usage"),
                                  "original_response_retrieval": row["source_reference"]}
            elif row["kind"] == "OPPORTUNITY":
                if p.get("status") == "team_budget_exhausted":
                    gates.append(row)
                else:
                    row["payload"] = {k: p[k] for k in ("status", "worker_id", "action_performed", "reason", "decision") if k in p}
            events.append(row)
    receipts = [e for e in events if e["kind"] == "RECEIPT"]
    initial = next(e for e in events if e["kind"] == "INITIAL")
    chains = make_chains(case, receipts, requests, gates)
    windows = make_windows(case, events, receipts, requests, gates, initial)
    summary = {"task_id": case, "episode_id": episode, "journal_proof": proof,
               "timeline_rows": len(events), "requests_recovered": len(requests),
               "requests_without_current_observation": sum(not r["current_observation_parsed"] for r in requests),
               "agent_decision_requests": sum(bool(r["decision_id"]) for r in requests),
               "agent_requests_without_current_observation": sum(bool(r["decision_id"]) and not r["current_observation_parsed"] for r in requests),
               "chains": dict(Counter(c["chain_type"] for c in chains)), "windows": len(windows),
               "trigger_counts": dict(Counter(k for w in windows for k in w["trigger_kinds"])),
               "integrations": {"total": sum(tool(e) == "integrate_patch" for e in receipts),
                   "clean_committed": sum(tool(e) == "integrate_patch" and ok(e) and not result(e).get("conflict_count") for e in receipts),
                   "committed_with_conflicts": sum(tool(e) == "integrate_patch" and ok(e) and bool(result(e).get("conflict_count")) for e in receipts)}}
    return events, chains, windows, summary


def main():
    started, cpu_start = time.monotonic(), time.process_time()
    if hasattr(os, "sched_getaffinity"):
        available = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, available[:2])
    os.nice(10)
    OUT.mkdir(parents=True, exist_ok=True)
    # Persist rule before the first source is opened; all triggers are unfiltered.
    write_json(OUT / "blind-review-packets/selection-rule.json", WINDOW_RULE)
    decoder = prior.load_analyzer().ObserverJournal._decode
    timelines, chains, windows, cases = [], [], [], []
    for path in prior.MEASUREMENTS:
        events, task_chains, task_windows, summary = analyze_one(path, decoder)
        timelines.extend(events)
        chains.extend(task_chains)
        windows.extend(task_windows)
        cases.append(summary)
        print(dump({"task": summary["task_id"], "events": len(events), "windows": len(task_windows)}), flush=True)
    counts = Counter(k for w in windows for k in w["trigger_kinds"])
    assert counts == Counter({"successful_send_message": 26, "successful_handoff_patch": 16,
                            "integration_reporting_conflict": 4, "successful_org_review_patch": 12,
                            "executed_failed_public_test": 43, "first_team_budget_gate_per_episode": 7}), counts
    assert len(windows) == len({w["window_id"] for w in windows}) == 108
    assert sum(c["integrations"]["clean_committed"] for c in cases) == 12
    assert sum(c["integrations"]["committed_with_conflicts"] for c in cases) == 4
    assert sum(c["agent_decision_requests"] for c in cases) == 863
    assert sum(c["agent_requests_without_current_observation"] for c in cases) == 0
    # One immutable source identifier and full chronological coverage per task.
    for case in cases:
        own = [e for e in timelines if e["task_id"] == case["task_id"]]
        assert [e["sequence"] for e in own] == list(range(1, len(own) + 1))
    write_jsonl(OUT / "task_event_timeline.jsonl", timelines)
    write_jsonl(OUT / "collaboration_chains.jsonl", chains)
    write_jsonl(OUT / "decision_windows.jsonl", windows)
    communications = [c for c in chains if "communication" in c]
    conflicts = [c for c in chains if c["chain_type"].startswith("B_")]
    handoffs = [c for c in chains if c["chain_type"].startswith("A_")]
    summary = {"schema": SCHEMA, "selection_rule": WINDOW_RULE, "tasks": cases,
        "totals": {"tasks": len(cases), "timeline_rows": len(timelines), "collaboration_chains": len(chains),
            "original_model_requests": sum(c["requests_recovered"] for c in cases),
            "agent_decision_requests_with_original_observation": 863,
            "non_agent_summary_requests_without_observation": sum(c["requests_without_current_observation"] for c in cases),
            "decision_windows": len(windows), "trigger_counts": dict(counts),
            "communication_events": len(communications),
            "communication_presentations_observed": sum(c["communication"]["first_actual_presentation"] is not None for c in communications),
            "full_body_in_observation_entries": sum(c["communication"]["any_full_body_observation_entry"] for c in communications),
            "explicit_communication_body_read_receipts": sum(len(c["communication"]["explicit_body_reads"]) for c in communications),
            "handoffs_with_integration_before_notice": sum(any(i["relative_to_handoff"] == "before" for i in c["integrations"]) for c in handoffs),
            "handoffs_with_observed_integration": sum(c["adoption_observed"] for c in handoffs),
            "conflict_text_recovered": sum(bool(c["exact_conflict_blocks"]) for c in conflicts),
            "conflicts_restored_to_published_content": sum(c["first_restored_published_content"] is not None for c in conflicts),
            "integrations_clean_committed": 12, "integrations_committed_with_conflicts": 4},
        "limitations": ["All 12 tasks are previously exposed development material, not independent confirmation.",
            "Original request preview presence proves supplied text, not attention, comprehension or causal use.",
            "Observation preview completeness is checked against sender text; content can remain incomplete without an explicit full read.",
            "Public-test results in contemporaneous receipts are not official acceptance scores.",
            "No organizational mismatch labels, final scores, new requests, grading or intervention are produced.",
            "Full original conversations remain referenced in sealed SQLite; compact timeline and blind packets do not duplicate their complete history.",
            "Post-conflict tests can be on modified versions; hashes and source references distinguish exact candidate validation."],
        "checks": {"original_journals_read_only": True, "closed_chain_count_and_head_reused": True,
                   "selected_record_hashes_checked_once": True, "all_packet_source_sequences_at_or_before_cutoff": True,
                   "all_trigger_denominators_asserted": True, "official_grading_sources_opened": False,
                   "model_calls": 0, "docker_calls": 0, "replayed_actions": 0},
        "resources": {"cpu_affinity_limit": 2, "workers": 1, "nice_increment": 10,
            "wall_seconds": round(time.monotonic() - started, 3), "cpu_seconds": round(time.process_time() - cpu_start, 3),
            "peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}}
    write_json(OUT / "chain-summary.json", summary)
    print(dump(summary["totals"]))


if __name__ == "__main__":
    main()
