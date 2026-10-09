"""Finite read-only all-member work-use evidence for the v040 handoff panel.

Automatic evidence is limited to changed public code, actual publication and
recipient input, explicit import that changes the recipient unit, then a real
public test of a version retaining it. Final fixed-delivery closure is separate.
Diagnostic/message semantics remain manual-review candidates, never automatic
cooperation credit. No model, business test, private acceptance or reference
implementation is executed or opened by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path

from scripts import measure_organization_work_v039 as previous

VERSION = "organization-work-use-v0.40"
PUBLIC_GROUPS = previous.PUBLIC_GROUPS


def content(message):
    try:
        value = json.loads(message.get("content", ""))
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def reports(value):
    if isinstance(value, dict):
        return list(value.values())
    return value if isinstance(value, list) else []


def diagnostic_facts(report):
    tests = report.get("tests")
    keys = ("test_id", "request", "observed", "expected", "passed")
    if not isinstance(tests, list) or not tests:
        return None
    for test in tests:
        if not isinstance(test, dict) or not {"test_id", "passed"} <= set(test):
            return None
        if test["passed"] is False and not {"request", "observed", "expected"} <= set(test):
            return None
        if not isinstance(test["passed"], bool):
            return None
    return {"executed": report.get("executed"), "passed": report.get("passed"),
            "tests": [{key: test[key] for key in keys if key in test} for test in tests]}


def same_facts(a, b):
    left, right = diagnostic_facts(a), diagnostic_facts(b)
    return left == right if left is not None and right is not None else None


def same_source(a, b):
    key = "initial_source_reference" if "initial_source_reference" in a else "source_reference"
    other = "initial_source_reference" if "initial_source_reference" in b else "source_reference"
    return a.get(key) is not None and a.get(key) == b.get(other)


def input_point(call, index):
    return {**call, "message_index": index,
            "source": previous.pointer(Path(call["path"]), f"/messages/{index}")}


def source_point(report):
    return {k: report[k] for k in ("diagnostic_id", "group_id", "origin", "source_reference",
        "initial_source_reference", "files_sha256", "source_binding", "executed", "passed") if k in report}


def diagnostic_visibility(inputs, events, initial):
    """Read original selected reports; execution and later visibility are distinct."""
    visible = defaultdict(list)
    test_by_action = {e.get("action_id"): e for e in events if e["kind"] == "test" and inputs.bound(e)}
    for call in sorted(inputs.calls.values(), key=lambda c: c["experience_sequence"]):
        for index, message in enumerate(inputs.messages(call)):
            value = content(message)
            observation = value.get("observation", {})
            if message.get("role") == "user" and isinstance(observation, dict) and observation.get("actor_id") == call["member"]:
                for report in reports(observation.get("initial_diagnostics")):
                    ident = report.get("diagnostic_id")
                    original = initial.get(ident)
                    if original is None:
                        continue
                    exact = (report.get("origin") == "environment_initial_diagnostic"
                        and report.get("files_sha256") == original.get("files_sha256")
                        and same_source(report, original) and same_facts(report, original) is True)
                    visible[call["member"]].append({"diagnostic_id": ident, "route": "environment_initial_report",
                        "exact_initial_fact": exact, "actual_input": input_point(call, index),
                        "report_source": source_point(report), "member_discovery": False})
            if message.get("role") != "tool" or value.get("ok") is not True:
                continue
            event = test_by_action.get(value.get("action_id"))
            if not event or event["actor_id"] != call["member"] or inputs.bound(event)["experience_sequence"] >= call["experience_sequence"]:
                continue
            rendered = value.get("result", {})
            actual = {r.get("diagnostic_id"): r for r in reports(event.get("public_diagnostics"))}
            for report in reports(rendered.get("public_diagnostics")):
                ident = report.get("diagnostic_id")
                original, actual_report = initial.get(ident), actual.get(ident)
                if original is None or actual_report is None:
                    continue
                real_report = (report.get("files_sha256") == actual_report.get("files_sha256")
                    and same_source(report, actual_report) and same_facts(report, actual_report) is True)
                initial_fact = (real_report and report.get("files_sha256") == original.get("files_sha256")
                                and same_facts(report, original) is True)
                visible[call["member"]].append({"diagnostic_id": ident, "route": "own_public_test_result",
                    "exact_original_test_report": real_report, "exact_initial_fact": initial_fact,
                    "same_initial_files": report.get("files_sha256") == original.get("files_sha256"),
                    "same_initial_test_facts": same_facts(report, original), "actual_input": input_point(call, index),
                    "test_sequence": event["sequence"], "report_source": source_point(report),
                    "member_discovery": "New execution is member work; the initial diagnostic remains an environment fact"})
    return dict(visible)


def patch_input(inputs, patch, recipient, before_sequence, events_by_action):
    publication = inputs.bound(patch)
    if not publication:
        return None
    for call in inputs.by_member(recipient):
        if not publication["experience_sequence"] < call["experience_sequence"] <= before_sequence:
            continue
        for index, message in enumerate(inputs.messages(call)):
            value = content(message)
            obs = value.get("observation", {})
            candidates = []
            if message.get("role") == "user" and isinstance(obs, dict) and obs.get("actor_id") == recipient:
                candidates = reports(obs.get("patches"))
            if message.get("role") == "tool" and value.get("ok") is True and isinstance(value.get("result"), dict):
                result = value["result"]
                action = events_by_action.get(value.get("action_id"), {})
                if (action.get("actor_id") == recipient and inputs.bound(action)
                        and action.get("patch_id") == patch["patch_id"]):
                    candidates.append({**result, "patch_id": action["patch_id"]})
            if any(item.get("patch_id") == patch["patch_id"] and item.get("source_reference") == patch["source_reference"]
                   for item in candidates):
                return {**input_point(call, index), "patch_id": patch["patch_id"],
                    "source_reference": patch["source_reference"],
                    "scope": "Exact public version in actual recipient input, not an ID-only mention; this alone is not use"}
    return None


def public_test_executed(test):
    return all(test.get("groups", {}).get(name, {}).get("executed") is True for name in PUBLIC_GROUPS)


def final_link(chain, final, versions, inputs):
    delivery = final.get("delivery")
    if not delivery:
        return {"status": "unclosed_no_final_fixed_delivery", "closed": False}
    if delivery["actor_id"] != chain["recipient"] or delivery["sequence"] < chain["test_result"]["sequence"]:
        return {"status": "unknown_other_final_author_or_earlier_delivery", "closed": None,
                "delivery": delivery}
    if (final.get("status") != "recorded_fixed_delivery" or not inputs.bound(delivery)
            or not inputs.bound(final.get("current_version_public_test") or {})):
        return {"status": "unknown_final_current_test_or_actual_output_binding", "closed": None, "delivery": delivery}
    files, path, error = versions.get(delivery.get("source_reference"))
    unit = previous.public_unit(files.get(chain["unit"]["path"]), chain["unit"]["symbol"])
    if error or unit["status"] != "supported":
        return {"status": "unknown_final_AST", "closed": None, "reason": error or unit["status"]}
    retained = unit["fingerprint"] == chain["unit"]["published_unit"]["fingerprint"]
    return {"status": "closed_to_final_fixed_delivery" if retained else "not_retained_in_final_fixed_delivery",
        "closed": retained, "delivery": delivery, "final_version_path": path,
        "recorded_R": final.get("recorded_R"), "public_groups_passed": final.get("public_groups_passed"),
        "scope": "Closure/quality separate from the existence of an earlier cross-member use chain"}


def program_chains(changes, events, inputs, versions, final, state_path):
    chains, unresolved = [], []
    by_action = {e.get("action_id"): e for e in events}
    by_patch = {e["patch_id"]: e for e in events if e["kind"] == "patch_fixed"}
    for unit in changes:
        patch = by_patch[unit["patch_id"]]
        for imported in events:
            if (imported["kind"] != "integrate" or imported.get("patch_id") != patch["patch_id"]
                    or imported["actor_id"] == patch["actor_id"] or imported["sequence"] <= patch["sequence"]
                    or not inputs.bound(imported)):
                continue
            recipient = imported["actor_id"]
            point = patch_input(inputs, patch, recipient, inputs.bound(imported)["experience_sequence"], by_action)
            candidate = {"source_member": patch["actor_id"], "recipient": recipient, "unit": unit,
                "publication": previous.brief_event(patch, state_path), "recipient_actual_input": point,
                "integration": previous.brief_event(imported, state_path)}
            if point is None or imported.get("input_reference") != patch["source_reference"]:
                unresolved.append({**candidate, "status": "unknown", "reason": "exact_publication_input_or_import_binding_missing"})
                continue
            before_files, before_path, before_error = versions.get(imported.get("previous_reference"))
            before = previous.public_unit(before_files.get(unit["path"]), unit["symbol"])
            if before_error or before["status"] not in {"supported", "absent"}:
                unresolved.append({**candidate, "status": "unknown", "reason": before_error or "unsupported_recipient_pre_AST"})
                continue
            if before.get("fingerprint") == unit["published_unit"]["fingerprint"]:
                # A complete negative for this strict structural path, not a claim of no possible information value.
                continue
            integrated_files, integrated_path, integrated_error = versions.get(imported.get("source_reference"))
            integrated = previous.public_unit(integrated_files.get(unit["path"]), unit["symbol"])
            if integrated_error or integrated["status"] != "supported":
                unresolved.append({**candidate, "status": "unknown", "reason": integrated_error or "unsupported_integrated_AST"})
                continue
            if integrated["fingerprint"] != unit["published_unit"]["fingerprint"]:
                unresolved.append({**candidate, "status": "unknown", "reason": "exact_published_unit_not_in_integrated_version"})
                continue
            tests = [e for e in events if e["kind"] == "test" and e["actor_id"] == recipient
                and e["sequence"] > imported["sequence"] and inputs.bound(e) and public_test_executed(e)]
            matched = False
            for test in tests:
                files, path, error = versions.get(test.get("source_reference"))
                tested = previous.public_unit(files.get(unit["path"]), unit["symbol"])
                if error or tested["status"] != "supported":
                    unresolved.append({**candidate, "status": "unknown", "reason": error or "unsupported_tested_AST",
                                       "test_sequence": test["sequence"]})
                    continue
                if tested["fingerprint"] != unit["published_unit"]["fingerprint"]:
                    continue
                chain = {**candidate, "status": "evidenced_program_work_use", "receiver_before": before,
                    "receiver_before_version_path": before_path, "integrated_version_path": integrated_path,
                    "integrated_unit": integrated, "tested_version_path": path, "tested_unit": tested,
                    "test_result": {**previous.brief_event(test, state_path),
                        "groups": {name: {k: group.get(k) for k in ("executed", "passed", "status")}
                                   for name, group in test.get("groups", {}).items()},
                        "public_groups_passed": all(test["groups"][name].get("passed") is True for name in PUBLIC_GROUPS)},
                    "scope": "Changed member unit, exact actual recipient input, changed workspace by explicit import and actual test result. Not semantic improvement, unique authorship or causal necessity."}
                chain["final_fixed_relation"] = final_link(chain, final, versions, inputs)
                chains.append(chain)
                matched = True
                break
            if not matched:
                unresolved.append({**candidate, "status": "unknown", "reason": "no_later_bound_public_test_of_retained_unit"})
    return chains, unresolved


def message_candidates(events, inputs, initial, visibility, assignments, final, state_path):
    candidates = []
    for message in events:
        sender_call = inputs.bound(message)
        if message["kind"] != "work_message" or not sender_call:
            continue
        sender, recipient = message["actor_id"], message.get("recipient")
        actual_input = inputs.visible_message(message)
        body = message.get("body", "")
        referenced = [ident for ident, report in initial.items() if ident in body or any(
            isinstance(t.get("test_id"), str) and t["test_id"] in body for t in report.get("tests", []))]
        relations = []
        for ident in referenced:
            known_sender = [v for v in visibility.get(sender, []) if v["diagnostic_id"] == ident
                            and v["actual_input"]["experience_sequence"] <= sender_call["experience_sequence"]]
            incoming_seq = actual_input["experience_sequence"] if actual_input else None
            recipient_seen = [v for v in visibility.get(recipient, []) if v["diagnostic_id"] == ident
                              and incoming_seq is not None and v["actual_input"]["experience_sequence"] <= incoming_seq]
            exact_prior = [v for v in recipient_seen if v["exact_initial_fact"] and v["actual_input"]["experience_sequence"] < incoming_seq]
            exact_same = [v for v in recipient_seen if v["exact_initial_fact"] and v["actual_input"]["experience_sequence"] == incoming_seq]
            relations.append({"diagnostic_id": ident, "initial_origin": "environment_initial_diagnostic",
                "initial_source": source_point(initial[ident]), "initial_diagnostic_is_member_discovery": False,
                "sender_report_visible_before_share": bool(known_sender), "sender_source_evidence": known_sender[:1],
                "recipient_initially_assigned": ident in assignments.get(recipient, []),
                "recipient_had_same_initial_fact_before_message_input": bool(exact_prior) if actual_input else None,
                "recipient_independently_received_same_initial_fact_in_same_input": bool(exact_same) if actual_input else None,
                "recipient_prior_or_same_input_evidence": exact_prior[:1] + exact_same[:1],
                "recipient_had_other_version_public_report": any(not v["exact_initial_fact"] for v in recipient_seen),
                "novel_information_benefit": "not_inferred"})
        followup = [e for e in events if actual_input and e["actor_id"] == recipient and e["sequence"] > message["sequence"]
            and e["kind"] in {"edit", "test", "patch_fixed", "submit"} and inputs.bound(e)
            and inputs.bound(e)["experience_sequence"] >= actual_input["experience_sequence"]]
        candidates.append({"status": "needs_manual_review", "source_member": sender, "recipient": recipient,
            "message": {**previous.brief_event(message, state_path), "body": body},
            "recipient_actual_input": actual_input, "referenced_initial_diagnostics": relations,
            "specific_diagnostic_machine_binding": bool(referenced),
            "following_member_work": [previous.brief_event(e, state_path) for e in followup],
            "observed_followup_tests": [{**previous.brief_event(e, state_path),
                "public_diagnostics": [source_point(d) for d in reports(e.get("public_diagnostics"))]}
                for e in followup if e["kind"] == "test"],
            "final_fixed_relation": {"recipient_is_final_submitter": bool(final.get("delivery") and final["delivery"]["actor_id"] == recipient),
                                     "semantic_relation": "unknown_until_manual_review"},
            "scope": "Full text must establish a specific fact and relevant consumption. ID, delivery, temporal follow-up and repeated known information do not establish use or complementarity benefit."})
    return candidates


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    result_path = folder / "slot-result.json"
    base = {"version": VERSION, "episode": str(folder), "read_only": True, "new_model_calls": 0,
        "new_test_or_acceptance_executions": 0, "training_support": False,
        "has_evidenced_cross_member_chain": None}
    if not result_path.is_file():
        return {**base, "status": "unknown_missing_slot_result", "totals": {}}
    result = previous.read(result_path)
    base.update(slot_id=result.get("slot_id"), purpose=result.get("purpose"), condition=result.get("condition"),
                recorded_R=result.get("R"), result_source=previous.pointer(result_path, "/"))
    if result.get("status") != "closed":
        return {**base, "status": "unknown_episode_not_closed", "totals": {}}
    state_path = folder / "prepared/world/control/state.json"
    if not state_path.is_file():
        state_path = folder / "episode/end/control/state.json"
    evidence_path = folder / "organization-evidence.json"
    if not state_path.is_file() or not evidence_path.is_file():
        return {**base, "status": "unknown_missing_evidence", "totals": {}}
    state, evidence = previous.read(state_path), previous.read(evidence_path)
    software = state["projects"][previous.PROJECT]["software"]
    events = state["software_events"]
    registry = software.get("registry", result.get("member_lifecycle", {}).get("registry", {}))
    budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
    inputs, versions = previous.Inputs(folder, evidence, budget), previous.Versions(folder, state, state_path)
    initial = software.get("initial_diagnostics", {})
    assignments = software.get("initial_diagnostic_assignments", {})
    symbols = software["case"].get("source_contract", {}).get("contract_symbols", {})
    symbols = {p: names for p, names in symbols.items() if p.endswith(".py") and not Path(p).name.startswith("test")}
    final = previous.final_evidence(result, events, state_path)
    visibility = diagnostic_visibility(inputs, events, initial)
    work, changes, unsupported = {}, [], []
    births = [e for e in events if e["kind"] == "member_spawned" and e.get("origin") != "diagnostic_setup"]
    for member, record in registry.items():
        birth = next((e for e in births if e.get("member_id") == member), None)
        onset = {"sequence": birth["sequence"] if birth else 0, "member_id": member,
                 "initial_source_reference": record.get("initial_source_reference")}
        material = previous.code_links(member, onset, events, symbols, versions, inputs, {"delivery": None}, state_path)
        own = [e for e in events if e["actor_id"] == member and inputs.bound(e)]
        visible = visibility.get(member, [])
        executed = [{"test_sequence": e["sequence"], "source": previous.brief_event(e, state_path),
            "diagnostics": [source_point(d) for d in reports(e.get("public_diagnostics"))]}
            for e in own if e["kind"] == "test"]
        work[member] = {"origin": record.get("origin", "initial_configuration" if birth is None else "unknown"),
            "initial_source_reference": onset["initial_source_reference"],
            "initial_code_is_environment_or_received_snapshot": True,
            "actual_output_calls": len(inputs.by_member(member)), "actual_event_counts": dict(Counter(e["kind"] for e in own)),
            "changed_public_units": material["changed_public_units"], "unsupported": material["unknown_or_unsupported"],
            "initial_diagnostic_assignment": assignments.get(member, []),
            "diagnostic_actual_input_evidence": visible, "own_public_diagnostic_executions": executed,
            "additional_initial_group_reexecution_visible": sorted({v["diagnostic_id"] for v in visible if v["route"] == "own_public_test_result"
                and v["diagnostic_id"] not in assignments.get(member, []) and v["exact_original_test_report"]}),
            "same_initial_fact_self_reacquired": sorted({v["diagnostic_id"] for v in visible if v["route"] == "own_public_test_result"
                and v["exact_initial_fact"] and v["diagnostic_id"] not in assignments.get(member, [])}),
            "scope": "Initial environment code/diagnostics are not member discoveries; actual edits, executions and sharing are member behavior."}
        changes += material["changed_public_units"]
        unsupported += [{"member_id": member, **issue} for issue in material["unknown_or_unsupported"]]
    chains, pending_program = program_chains(changes, events, inputs, versions, final, state_path)
    info = message_candidates(events, inputs, initial, visibility, assignments, final, state_path)
    expected_calls = sum(v.get("attempt_started") is True and bool(v.get("charge")) for v in budget.get("records", {}).values())
    gaps = copy.deepcopy(inputs.issues)
    if len(inputs.calls) != expected_calls:
        gaps.append({"reason": "not_all_charged_actual_calls_have_complete_input_output_binding",
                     "expected": expected_calls, "bound": len(inputs.calls)})
    unbound = [e for e in events if e.get("actor_id") in registry and e.get("action_id")
               and previous.actual_event(e) and not inputs.bound(e)]
    if unbound:
        gaps.append({"reason": "member_events_without_actual_output_binding",
                     "events": [previous.brief_event(e, state_path) for e in unbound]})
    if not registry or not symbols:
        gaps.append({"reason": "missing_member_registry_or_declared_public_symbols"})
    if not initial or not assignments:
        gaps.append({"reason": "missing_initial_diagnostic_provenance_or_assignment"})
    bad_initial = [v for values in visibility.values() for v in values if v["route"] == "environment_initial_report" and not v["exact_initial_fact"]]
    if bad_initial:
        gaps.append({"reason": "initial_diagnostic_payload_not_exactly_bound", "count": len(bad_initial)})
    decision = True if chains else None if info or pending_program or unsupported or gaps else False
    return {**base, "status": "measured", "has_evidenced_cross_member_chain": decision,
        "environment_preparation": {"initial_code_is_model_work": False, "initial_diagnostics_are_member_discoveries": False,
            "diagnostics": {key: source_point(value) for key, value in initial.items()}, "assignments": assignments,
            "source": previous.pointer(state_path, "/projects/SOFTWARE27/software/initial_diagnostics")},
        "member_work": work, "diagnostic_information": {"actual_report_visibility": visibility,
            "message_share_candidates": [{"source_member": c["source_member"], "recipient": c["recipient"],
                "message": c["message"], "referenced_initial_diagnostics": c["referenced_initial_diagnostics"]} for c in info]},
        "program_work_chains": chains, "pending_program_relations": pending_program,
        "information_work_candidates": info, "unsupported_relations": unsupported, "measurement_gaps": gaps,
        "final_delivery": final, "birth_events": [previous.brief_event(e, state_path) for e in births],
        "totals": {"observed_members": len(registry), "initial_members": len(result.get("member_lifecycle", {}).get("initial_members", [])),
            "model_requested_births": sum(e.get("origin") == "member_request" for e in births),
            "external_births": sum(e.get("origin") == "external_controller" for e in births),
            "evidenced_program_work_chains": len(chains),
            "chains_closed_to_final_fixed_delivery": sum(c["final_fixed_relation"]["closed"] is True for c in chains),
            "information_candidates_needing_manual_review": len(info), "pending_program_relations": len(pending_program),
            "unsupported_relations": len(unsupported), "initial_diagnostic_share_candidates": sum(c["specific_diagnostic_machine_binding"] for c in info),
            "member_extra_diagnostic_groups_self_reacquired": sum(len(w["same_initial_fact_self_reacquired"]) for w in work.values())},
        "criterion": "True: at least one frozen mechanical program chain. False: complete records with no pending semantic/unsupported relation. Null: missing or ambiguous evidence. Test success and final closure are separate; no causal, training-support or quota inference."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(measure_episode(args.episode), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
