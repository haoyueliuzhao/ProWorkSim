"""Conservative read-only links from a new member's work to a final delivery.

This is a finite organization-development ledger, not a training Mapper or a
causal/authorship score. Only declared public production AST units are compared.
No code, tests, private acceptance files or reference implementations are run or
opened. Raw message content requires manual semantic review before information
help can be claimed. Existing final R is reported separately from code retention.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path

VERSION = "organization-work-use-v0.39"
PROJECT = "SOFTWARE27"
TASK_EVENTS = {"task_created", "claim", "task_revised", "task_returned", "transfer_offered",
               "transfer_accepted", "transfer_declined", "dependency_declared", "dependency_removed"}
PUBLIC_GROUPS = ("upstream_regressions", "public_normal")


def read(path):
    return json.loads(path.read_text())


def pointer(path, value):
    return {"path": str(path), "json_pointer": value}


def actual_event(event):
    return event.get("origin") != "diagnostic_setup" and event.get("model_generated") is not False


def ref_key(reference):
    if not isinstance(reference, dict):
        return None
    return reference.get("object_id"), reference.get("version_id")


def brief_event(event, state_path):
    keys = ("sequence", "kind", "actor_id", "action_id", "patch_id", "task_id", "source_reference",
            "previous_reference", "input_reference", "conflicts", "delivery_id", "test_sequence", "path")
    return {**{k: event[k] for k in keys if k in event},
            "source": pointer(state_path, f"/software_events/{event['sequence'] - 1}")}


class Versions:
    def __init__(self, folder, state, state_path):
        self.state, self.cache = state, {}
        self.controls = [state_path.parent, folder / "episode/end/control"]

    def get(self, reference):
        key = ref_key(reference)
        if key in self.cache:
            return self.cache[key]
        if key is None or any(not isinstance(s, str) or Path(s).name != s or s in {".", ".."} for s in key):
            return {}, None, "invalid_version_reference"
        artifact = self.state.get("artifacts", {}).get(key[0], {})
        filename = artifact.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".json"):
            return {}, None, "unknown_public_artifact_filename"
        for control in self.controls:
            path = control / "versions" / key[0] / key[1] / filename
            if not path.is_file() or not path.resolve().is_relative_to((control / "versions").resolve()):
                continue
            try:
                bundle = read(path)
            except (OSError, ValueError):
                return {}, str(path), "unreadable_public_version"
            result = bundle.get("files", {}), str(path), None
            self.cache[key] = result
            return result
        return {}, None, "missing_public_version"


def public_unit(text, symbol):
    """Return a structural fingerprint, or explicit unsupported/unknown state."""
    if not isinstance(text, str):
        return {"status": "missing_file"}
    try:
        module = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return {"status": "unparseable_module"}
    nodes = [n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and n.name == symbol]
    if not nodes:
        return {"status": "absent", "fingerprint": None}
    if len(nodes) != 1 or symbol.startswith("_"):
        return {"status": "unknown_ambiguous_or_nonpublic_symbol"}
    node = nodes[0]
    if node.decorator_list or isinstance(node, ast.ClassDef) and (node.bases or node.keywords):
        return {"status": "unknown_decorated_or_complex_class"}
    # Rebinding a declared entry point makes a plain definition comparison unsafe.
    for statement in module.body:
        if statement is node or isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == symbol for n in ast.walk(statement)):
            return {"status": "unknown_module_rebinding"}
    normalized = copy.deepcopy(node)
    for item in ast.walk(normalized):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.body:
            first = item.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                item.body = item.body[1:]
    encoded = ast.dump(normalized, include_attributes=False).encode()
    return {"status": "supported", "kind": type(node).__name__, "start_line": node.lineno,
            "end_line": node.end_lineno, "fingerprint": hashlib.sha256(encoded).hexdigest()}


class Inputs:
    """Stored selected input must bind a charged, successful original generation."""
    def __init__(self, folder, evidence, budget):
        self.folder, self.calls, self.action_calls, self.cache = folder, {}, {}, {}
        self.issues = []
        originals = {r["call_id"]: r for r in evidence.get("original_attempts", [])}
        by_hash = defaultdict(list)
        for path in sorted((folder / "raw-transport").glob("request-*/projection.json")):
            projection = read(path)
            by_hash[projection.get("selected_request_sha256")].append((path, projection))
        for call_id, record in budget.get("records", {}).items():
            original = originals.get(call_id, {})
            if (record.get("attempt_started") is not True or not record.get("charge")
                    or original.get("status") != "success" or not original.get("original_output_present")):
                continue
            prep = record.get("reservation", {}).get("preparation", {})
            matches = by_hash.get(prep.get("selected_request_sha256"), [])
            if (len(matches) != 1 or matches[0][1].get("input_ids_sha256") != original.get("input_ids_sha256")
                    or prep.get("input_ids_sha256") != original.get("input_ids_sha256")):
                self.issues.append({"call_id": call_id, "reason": "missing_or_ambiguous_actual_input_binding"})
                continue
            path, projection = matches[0]
            selected = path.with_name("selected-request.json")
            if not selected.is_file():
                self.issues.append({"call_id": call_id, "reason": "missing_selected_request"})
                continue
            self.calls[call_id] = {"call_id": call_id, "member": record["member"],
                "experience_sequence": original["experience_sequence"], "path": str(selected),
                "selected_request_sha256": projection["selected_request_sha256"],
                "input_ids_sha256": original["input_ids_sha256"]}
        experience = folder / "experience.jsonl"
        if experience.is_file():
            with experience.open() as stream:
                for line in stream:
                    event = json.loads(line)
                    if event["kind"] not in {"tool_call", "harness_tool_call"}:
                        continue
                    payload = event["payload"]
                    call = self.calls.get(payload.get("model_call_id"))
                    response = payload.get("response", {})
                    if call and response.get("ok") is True and response.get("action_id"):
                        self.action_calls[response["action_id"]] = call
        else:
            self.issues.append({"reason": "missing_model_world_action_links"})

    def by_member(self, member):
        return sorted((c for c in self.calls.values() if c["member"] == member), key=lambda c: c["experience_sequence"])

    def messages(self, call):
        if call["path"] not in self.cache:
            self.cache[call["path"]] = read(Path(call["path"])).get("messages", [])
        return self.cache[call["path"]]

    def bound(self, event):
        call = self.action_calls.get(event.get("action_id"))
        return call if actual_event(event) and call and call["member"] == event.get("actor_id") else None

    def visible_message(self, event):
        """Exact addressed event/body or its explicit truncated preview, never an ID alone."""
        sender = self.bound(event)
        for call in self.by_member(event.get("recipient")):
            if not sender or call["experience_sequence"] <= sender["experience_sequence"]:
                continue
            for index, message in enumerate(self.messages(call)):
                try:
                    content = json.loads(message.get("content", ""))
                except (TypeError, ValueError):
                    continue
                if not isinstance(content, dict):
                    continue
                observation = content.get("observation", {})
                candidates = observation.get("messages", []) if isinstance(observation, dict) else []
                if message.get("role") == "tool" and content.get("ok") is True and isinstance(content.get("result"), dict):
                    candidates = [*candidates, content["result"]]
                for item in candidates:
                    if (item.get("sequence") != event["sequence"] or item.get("actor_id") != event["actor_id"]
                            or item.get("recipient") != event.get("recipient")):
                        continue
                    full = item.get("body") == event.get("body") and isinstance(event.get("body"), str)
                    preview = (item.get("body_truncated") is True and isinstance(item.get("body"), str)
                               and bool(item["body"]) and event.get("body", "").startswith(item["body"]))
                    if full or preview:
                        return {**call, "message_index": index, "full_body": full,
                                "evidence": "Actual charged selected input, matching sender/recipient/event and body"}
        return None


def briefing_evidence(birth, inputs):
    child, text = birth["member_id"], birth.get("briefing", "")
    calls = inputs.by_member(child)
    public_input, seen = None, None
    for call in calls:
        for index, message in enumerate(inputs.messages(call)):
            try:
                content = json.loads(message.get("content", ""))
            except (TypeError, ValueError):
                continue
            obs = content.get("observation", {}) if isinstance(content, dict) else {}
            if obs.get("actor_id") != child:
                continue
            if public_input is None and obs.get("contract") and "team_model_budget" in obs:
                public_input = {**call, "message_index": index,
                    "workspace_reference": obs.get("workspace_reference"),
                    "matches_birth_workspace": obs.get("workspace_reference") == birth.get("workspace_reference")}
            if text and obs.get("own_initial_briefing") == text and seen is None:
                seen = {**call, "message_index": index}
    external_empty = birth.get("origin") == "external_controller" and not text
    return {"status": "not_applicable_external_no_briefing" if external_empty else
            "presented_in_actual_child_input" if seen else "unknown_no_actual_child_input" if not calls else
            "unknown_briefing_not_found_in_bound_child_inputs",
            "briefing_input": seen, "public_root_and_budget_input": public_input,
            "attribution": "Member briefing is parent's output once and child's input; an external empty briefing is not invented member output"}


def final_evidence(result, events, state_path):
    deliveries = [e for e in events if e["kind"] == "submit" and actual_event(e)]
    final = deliveries[-1] if deliveries else None
    if final is None:
        return {"status": "unclosed_no_fixed_delivery", "delivery": None, "recorded_R": result.get("R")}
    tests = [e for e in events if e["kind"] == "test" and actual_event(e)
             and e["actor_id"] == final["actor_id"] and e.get("source_reference") == final.get("source_reference")
             and e["sequence"] == final.get("test_sequence") and e["sequence"] < final["sequence"]]
    test = tests[0] if len(tests) == 1 else None
    executed = bool(test and all(test.get("groups", {}).get(n, {}).get("executed") is True for n in PUBLIC_GROUPS))
    return {"status": "recorded_fixed_delivery" if executed else "unknown_missing_current_version_public_test",
        "delivery": brief_event(final, state_path), "current_version_public_test": brief_event(test, state_path) if test else None,
        "public_groups_executed": executed,
        "public_groups_passed": bool(test and all(test.get("groups", {}).get(n, {}).get("passed") is True for n in PUBLIC_GROUPS)),
        "recorded_R": result.get("R"), "recorded_complete_delivery": result.get("complete_delivery"),
        "quality_source": "Existing slot-result.json terminal fields only; no private/reference acceptance file opened",
        "scope": "Final fixed tree only, not every earlier submission and not a later mutable workspace"}


def code_links(child, birth, events, symbols, versions, inputs, final, state_path):
    initial, initial_path, initial_error = versions.get(birth.get("initial_source_reference"))
    changes, unknowns, acquisitions, links = [], [], [], []
    patches = [e for e in events if e["kind"] == "patch_fixed" and e["actor_id"] == child
               and e["sequence"] > birth["sequence"] and actual_event(e)]
    own_edits = [e for e in events if e["kind"] == "edit" and e["actor_id"] == child
                 and e["sequence"] > birth["sequence"] and actual_event(e)]
    for patch in patches:
        files, path, error = versions.get(patch.get("source_reference"))
        if initial_error or error or not inputs.bound(patch):
            unknowns.append({"patch_id": patch.get("patch_id"), "reason": initial_error or error or "unbound_model_patch_publication"})
            continue
        candidates = []
        for production_path, names in symbols.items():
            for name in names:
                before, after = public_unit(initial.get(production_path), name), public_unit(files.get(production_path), name)
                if before["status"] not in {"supported", "absent"} or after["status"] != "supported":
                    unknowns.append({"patch_id": patch["patch_id"], "path": production_path, "symbol": name,
                        "reason": "unsupported_or_unavailable_public_unit", "initial": before["status"], "published": after["status"]})
                    continue
                if before.get("fingerprint") == after["fingerprint"]:
                    continue
                edits = []
                for edit in own_edits:
                    if edit["path"] != production_path or edit["sequence"] >= patch["sequence"] or not inputs.bound(edit):
                        continue
                    old, _, old_error = versions.get(edit.get("previous_reference"))
                    new, _, new_error = versions.get(edit.get("source_reference"))
                    a, b = public_unit(old.get(production_path), name), public_unit(new.get(production_path), name)
                    if (not old_error and not new_error and a["status"] in {"supported", "absent"}
                            and b["status"] == "supported" and a.get("fingerprint") != b["fingerprint"]
                            and b["fingerprint"] == after["fingerprint"]):
                        edits.append(edit)
                if not edits:
                    unknowns.append({"patch_id": patch["patch_id"], "path": production_path, "symbol": name,
                                     "reason": "changed_since_birth_but_no_bound_child_edit_of_this_unit"})
                    continue
                candidate = {"patch_id": patch["patch_id"], "path": production_path, "symbol": name,
                    "initial_reference": birth.get("initial_source_reference"), "initial_version_path": initial_path,
                    "published_reference": patch["source_reference"], "published_version_path": path,
                    "initial_fingerprint": before.get("fingerprint"), "published_unit": after,
                    "child_edit": brief_event(edits[-1], state_path), "publication": brief_event(patch, state_path)}
                candidates.append(candidate)
                changes.append(candidate)
        for event in events:
            if event["actor_id"] == child or event["sequence"] <= patch["sequence"] or not inputs.bound(event):
                continue
            if event["kind"] == "read" and event.get("patch_id") == patch["patch_id"] and event.get("source_reference") == patch["source_reference"]:
                acquisitions.append({"kind": "recorded_fixed_patch_read", "event": brief_event(event, state_path),
                    "scope": "Successful legal read; not by itself proof of code adoption or semantic use"})
            if event["kind"] != "integrate" or event.get("patch_id") != patch["patch_id"]:
                continue
            acquisitions.append({"kind": "recorded_explicit_integration", "event": brief_event(event, state_path)})
            for candidate in candidates:
                link = {"unit": candidate, "integration": brief_event(event, state_path),
                        "status": "unknown", "reason": None}
                delivery = final.get("delivery")
                if event.get("input_reference") != patch["source_reference"]:
                    link["reason"] = "integration_does_not_bind_published_version"
                elif not delivery:
                    link["reason"] = "unclosed_no_final_delivery"
                elif delivery["actor_id"] != event["actor_id"]:
                    link["reason"] = "multihop_or_other_final_submitter_not_attributed"
                elif event["sequence"] >= delivery["sequence"]:
                    link["reason"] = "integration_after_final_submission"
                else:
                    pre, pre_path, pre_error = versions.get(event.get("previous_reference"))
                    end, end_path, end_error = versions.get(delivery.get("source_reference"))
                    before = public_unit(pre.get(candidate["path"]), candidate["symbol"])
                    retained = public_unit(end.get(candidate["path"]), candidate["symbol"])
                    link.update(receiver_pre_version_path=pre_path, final_version_path=end_path,
                                receiver_before=before, final_unit=retained)
                    if pre_error or end_error or before["status"] not in {"supported", "absent"} or retained["status"] != "supported":
                        link["reason"] = pre_error or end_error or "unsupported_pre_or_final_AST"
                    elif before.get("fingerprint") == candidate["published_unit"]["fingerprint"]:
                        link.update(status="not_evidenced", reason="same_unit_already_present_before_integration")
                    elif retained["fingerprint"] != candidate["published_unit"]["fingerprint"]:
                        link.update(status="not_evidenced", reason="exact_child_unit_not_retained_rewrite_value_unknown")
                    elif (final["status"] != "recorded_fixed_delivery" or not inputs.bound(delivery)
                            or not inputs.bound(final.get("current_version_public_test") or {})):
                        link["reason"] = "final_current_version_test_or_model_binding_unavailable"
                    else:
                        link.update(status="evidenced_code_adoption", reason="child_changed_unit_explicitly_imported_and_retained",
                                    final_quality=final)
                links.append(link)
    delivery = final.get("delivery")
    direct = {"status": "not_observed", "units": []}
    if delivery and delivery["actor_id"] == child:
        end, _, error = versions.get(delivery.get("source_reference"))
        retained = [c for c in changes if not error and c["publication"]["sequence"] < delivery["sequence"]
                    and public_unit(end.get(c["path"]), c["symbol"]).get("fingerprint") == c["published_unit"]["fingerprint"]]
        direct = {"status": "evidenced_new_member_direct_delivery" if retained and final["status"] == "recorded_fixed_delivery"
                  and inputs.bound(delivery) and inputs.bound(final.get("current_version_public_test") or {}) else "unknown",
                  "units": retained, "final_quality": final,
                  "scope": "New member's own final delivery; distinct from a partner adopting its work"}
    return {"changed_public_units": changes, "unknown_or_unsupported": unknowns,
        "partner_acquisitions": acquisitions, "code_adoption_links": links, "direct_final_delivery": direct,
        "scope": "Exact declared public AST units, excluding docstrings/locations. No alias/dynamic/semantic equivalence, unique authorship, causal necessity or credit for integration IDs alone."}


def information_links(child, birth, events, inputs, final, state_path):
    candidates = []
    for message in events:
        if message["kind"] != "work_message" or message["actor_id"] != child or message["sequence"] <= birth["sequence"] or not inputs.bound(message):
            continue
        tests = [e for e in events if e["kind"] == "test" and e["actor_id"] == child
                 and birth["sequence"] < e["sequence"] < message["sequence"] and inputs.bound(e)]
        visible = inputs.visible_message(message)
        following = [e for e in events if visible and e["actor_id"] == message.get("recipient")
            and e["sequence"] > message["sequence"] and e["kind"] in {"edit", "test", "patch_fixed", "submit"}
            and inputs.bound(e) and inputs.bound(e)["experience_sequence"] >= visible["experience_sequence"]]
        linked_final = bool(final.get("delivery") and final["delivery"]["actor_id"] == message.get("recipient")
                            and final["delivery"]["sequence"] > message["sequence"])
        status = "needs_manual_review" if visible and following and linked_final else "unknown_unclosed_relation"
        candidates.append({"status": status, "preceding_child_test": brief_event(tests[-1], state_path) if tests else None,
            "message": {**brief_event(message, state_path), "recipient": message.get("recipient"), "body": message.get("body")},
            "receiver_actual_input": visible, "receiver_followup": [brief_event(e, state_path) for e in following],
            "final_delivery_by_recipient": linked_final, "final_quality": final if linked_final else None,
            "missing_evidence": [name for name, exists in (("receiver_actual_selected_input", visible),
                ("receiver_followup", following), ("recipient_final_delivery", linked_final)) if not exists],
            "semantic_consumption": "needs_manual_review",
            "scope": "Chronological candidate only. Test-to-message content and counterexample-to-edit semantic use are not automatically established; a message is never scored as effective help."})
    return candidates


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    result_path = folder / "slot-result.json"
    if not result_path.is_file():
        return {"version": VERSION, "status": "unknown_missing_slot_result", "births": [], "totals": {}, "episode": str(folder)}
    result = read(result_path)
    base = {"version": VERSION, "episode": str(folder), "slot_id": result.get("slot_id"),
        "purpose": result.get("purpose"), "condition": result.get("condition"),
        "closed_result_source": pointer(result_path, "/"), "recorded_R": result.get("R"),
        "external_intervention": result.get("external_intervention", result.get("boundary", {}).get("external_intervention")),
        "read_only": True, "new_model_calls": 0, "new_test_or_acceptance_executions": 0,
        "training_support": False, "scope": "Finite observed work relations; no causal credit, contribution reward or new training classes"}
    if result.get("status") != "closed":
        return {**base, "status": "unknown_episode_not_closed", "births": [], "totals": {}}
    state_path = folder / "prepared/world/control/state.json"
    if not state_path.is_file():
        state_path = folder / "episode/end/control/state.json"
    if not state_path.is_file():
        return {**base, "status": "unknown_missing_terminal_world", "births": [], "totals": {}}
    state = read(state_path)
    software = state["projects"][PROJECT]["software"]
    initial = set(result.get("member_lifecycle", {}).get("initial_members", software["case"].get("active_roles", [])))
    events = state["software_events"]
    births = [e for e in events if e["kind"] == "member_spawned" and e.get("member_id") not in initial
              and e.get("origin") != "diagnostic_setup"]
    final = final_evidence(result, events, state_path)
    totals = {"new_members": len(births), "model_requested_births": 0, "external_births": 0,
        "members_with_bound_actual_output": 0, "members_with_evidenced_peer_code_adoption": 0,
        "members_with_direct_final_delivery": 0, "information_candidates_needing_manual_review": 0,
        "information_candidates_unclosed": 0}
    if not births:
        return {**base, "status": "no_new_births", "births": [], "totals": totals, "final_delivery": final}
    evidence_path = folder / "organization-evidence.json"
    evidence = read(evidence_path) if evidence_path.is_file() else {}
    budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
    inputs, versions = Inputs(folder, evidence, budget), Versions(folder, state, state_path)
    symbols = software["case"].get("source_contract", {}).get("contract_symbols", {})
    symbols = {p: names for p, names in symbols.items() if p.endswith(".py") and not Path(p).name.startswith("test")
               and isinstance(names, list) and all(isinstance(n, str) for n in names)}
    rows = []
    for birth in births:
        child = birth["member_id"]
        origin = {"member_request": "model", "external_controller": "external_controller"}.get(birth.get("origin"), "unknown")
        totals["model_requested_births"] += origin == "model"
        totals["external_births"] += origin == "external_controller"
        own = [e for e in events if e["actor_id"] == child and e["sequence"] > birth["sequence"] and inputs.bound(e)]
        code = code_links(child, birth, events, symbols, versions, inputs, final, state_path)
        info = information_links(child, birth, events, inputs, final, state_path)
        calls = inputs.by_member(child)
        rows.append({"member_id": child, "origin": origin, "original_origin": birth.get("origin"),
            "birth": {**brief_event(birth, state_path), **{k: birth.get(k) for k in (
                "born_by", "briefing", "initial_source_reference", "initial_patch_id", "workspace_reference", "replaces")}},
            "briefing": briefing_evidence(birth, inputs), "bound_actual_output_calls": len(calls),
            "recorded_usage": evidence.get("usage_by_member", {}).get(child),
            "actual_work": {"event_counts": dict(Counter(e["kind"] for e in own)),
                "production_edits": [brief_event(e, state_path) for e in own if e["kind"] == "edit" and e.get("path") in symbols],
                "public_tests": [brief_event(e, state_path) for e in own if e["kind"] == "test"],
                "task_effects": [brief_event(e, state_path) for e in own if e["kind"] in TASK_EVENTS]},
            "code_work": code, "information_help_candidates": info,
            "measurement_gaps": ([] if symbols else ["missing_declared_public_contract_symbols"]) +
                ([] if calls else ["no_bound_actual_child_output"]),
            "scope": "No observed chain does not establish no contribution; unsupported AST, indirect transfers and text semantics stay unknown."})
        totals["members_with_bound_actual_output"] += bool(calls)
        totals["members_with_evidenced_peer_code_adoption"] += any(link["status"] == "evidenced_code_adoption" for link in code["code_adoption_links"])
        totals["members_with_direct_final_delivery"] += code["direct_final_delivery"]["status"] == "evidenced_new_member_direct_delivery"
        totals["information_candidates_needing_manual_review"] += sum(c["status"] == "needs_manual_review" for c in info)
        totals["information_candidates_unclosed"] += sum(c["status"] == "unknown_unclosed_relation" for c in info)
    return {**base, "status": "measured", "births": rows, "totals": totals, "final_delivery": final,
            "actual_input_binding_issues": inputs.issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = measure_episode(args.episode)
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
