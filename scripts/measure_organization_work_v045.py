"""Five separately evidenced stages of frozen v045 member-work reuse.

This reader never executes a model, tokenizer, business test, or acceptance.
Current work, legal publication, actual acquisition, verifiable use, and final
fixed-delivery linkage are separate facts. A strict program path is a changed
member unit, an authorized exact patch, acquisition by another member, a changed
imported unit, and an actual test of a version retaining it. Test failure and no
delivery do not erase that use. Text semantics require a separately source-bound
review; mere reading, similarity, multiple sessions, and later work earn no use.

The first *eligible* sharing opportunity means a recorded producer opportunity
after creation with a live reachable partner. It is a mechanical opportunity,
not an assertion of usefulness or complementarity. Resources are from original
preparation and the same opportunity's before snapshot, never terminal balance.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v039 as base
from scripts import measure_organization_work_v040 as legacy
from scripts import measure_organization_work_v044 as lifecycle

VERSION = "organization-work-use-v0.45"
OPPORTUNITY_VERSION = "organization_work_opportunity_v045"
STAGES = ("produced", "published", "acquired", "used", "fixed_delivery")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def source(path, pointer="/"):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data), "json_pointer": pointer}


def stage(value, status, **evidence):
    return {"value": value, "status": status, **evidence}


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def content(message):
    return legacy.content(message)


def structural_file(text):
    """An executable file fingerprint; comments/docstrings are not new work."""
    if not isinstance(text, str):
        return {"status": "absent", "fingerprint": None}
    try:
        node = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return {"status": "unsupported_syntax", "fingerprint": None}
    for item in ast.walk(node):
        if isinstance(item, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.body:
            first = item.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                item.body = item.body[1:]
    return {"status": "supported", "fingerprint": digest(ast.dump(node, include_attributes=False).encode())}


def unit(files, path, symbol):
    return structural_file(files.get(path)) if symbol is None else base.public_unit(files.get(path), symbol)


class Evidence:
    """One pass over original experience; immutable input bytes cached once."""

    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.gaps, self.calls, self.action_calls, self.action_receipts = [], {}, {}, {}
        self.message_cache, self.native, self.opportunities = {}, {}, []
        self.result_path = self.folder / "slot-result.json"
        self.result = base.read(self.result_path)
        require(self.result.get("status") == "closed", "episode_not_closed")
        self.state_path = self.folder / "episode/end/control/state.json"
        if not self.state_path.is_file():
            self.state_path = self.folder / "prepared/world/control/state.json"
        self.state = base.read(self.state_path)
        self.software = self.state["projects"][base.PROJECT]["software"]
        self.events = self.state["software_events"]
        require([event.get("sequence") for event in self.events] == list(range(1, len(self.events) + 1)),
                "world_event_sequence_not_unique_complete")
        self.registry = self.software.get("registry", {})
        self.evidence_path = self.folder / "organization-evidence.json"
        self.evidence = base.read(self.evidence_path)
        self.budget_path = self.folder / "team-budget.json"
        self.budget = base.read(self.budget_path)["model"]
        require(self.budget == self.result["team_budget"]["model"] == self.evidence["team_budget"]["model"],
                "saved_model_budget_copies_disagree")
        self.experience_path = self.folder / "experience.jsonl"
        with self.experience_path.open() as stream:
            self.experience = [json.loads(line) for line in stream if line.strip()]
        self.experience_source, self.world_source = source(self.experience_path), source(self.state_path)
        sequences = [row.get("sequence") for row in self.experience]
        require(all(type(seq) is int for seq in sequences) and sequences == sorted(set(sequences)),
                "experience_sequence_not_unique_monotonic")
        self.by_kind = defaultdict(list)
        for row in self.experience:
            self.by_kind[row.get("kind")].append(row)
        self.versions = base.Versions(self.folder, self.state, self.state_path)
        self._inputs()
        self._opportunities()
        self._actions()

    def gap(self, reason, **facts):
        self.gaps.append({"reason": reason, **facts})

    def point(self, event):
        return {**base.brief_event(event, self.state_path),
                "source": {**self.world_source, "json_pointer": f"/software_events/{event['sequence'] - 1}"}}

    def experience_point(self, event):
        return {"sequence": event["sequence"], "kind": event["kind"],
                "member": event.get("worker_id"), "source": self.experience_source,
                "lookup": {"sequence": event["sequence"]}}

    def _inputs(self):
        attempts = self.evidence.get("original_attempts", [])
        originals = {row["call_id"]: row for row in attempts}
        require(len(originals) == len(attempts), "duplicate_original_attempt")
        records = self.budget["records"]
        for directory in sorted((self.folder / "raw-transport").glob("request-*")):
            call_id = None
            try:
                turn = base.read(directory / "runner-turn.json")
                call_id, member = turn["association"]["call_id"], turn["member_id"]
                require(call_id not in self.calls, "duplicate_actual_call_id")
                record, original = records[call_id], originals[call_id]
                require(record["member"] == member == original["worker_id"] == turn["association"]["worker_id"],
                        "actual_call_member_mismatch")
                require(record.get("attempt_started") is True and record.get("status") == "settled"
                        and original.get("status") == "success" and original.get("original_output_present") is True,
                        "actual_call_not_settled_original_output")
                selected_path = directory / "selected-request.json"
                selected, preparation, projection, response = (base.read(directory / name) for name in
                    ("selected-request.json", "budget-preparation.json", "projection.json", "response.json"))
                body, charge = response["body"], record["charge"]
                trace, usage = body["token_trace"], body["usage"]
                require(response.get("http_status") == 200 and digest(json_bytes(body)) == original["response_body_sha256"]
                        == charge["response_body_sha256"] and body["id"] == original["response_id"] == charge["response_id"],
                        "original_native_output_identity_mismatch")
                require(preparation == record["reservation"]["preparation"]
                        and preparation["preparation_sha256"] == digest(json_bytes({k: v for k, v in preparation.items()
                                                                                 if k != "preparation_sha256"})),
                        "unbound_original_preparation")
                require(digest(selected_path.read_bytes()) == preparation["selected_request_sha256"]
                        == projection["selected_request_sha256"], "selected_input_bytes_changed")
                require(digest(json_bytes(trace["input_ids"])) == preparation["input_ids_sha256"]
                        == projection["input_ids_sha256"] == original["input_ids_sha256"]
                        and digest(json_bytes(trace["output_ids"])) == original["output_ids_sha256"],
                        "original_input_or_output_token_trace_mismatch")
                require(body["actor_identity"] == preparation["actor_identity"] == self.result["actor_identity"]
                        and body["online_window_id"] == preparation["window_id"] == "organization-v045:" + self.result["slot_id"],
                        "actual_actor_or_window_mismatch")
                require(usage == original["usage"] == charge["reported_usage"]
                        and usage["prompt_tokens"] == len(trace["input_ids"]) == preparation["prompt_tokens"]
                        and usage["completion_tokens"] == len(trace["output_ids"])
                        and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"] == charge["charged_tokens"],
                        "actual_usage_or_charge_mismatch")
                require(preparation["reserved_output_tokens"] == selected["max_tokens"] == 2048
                        and preparation["context_limit"] == 16384 and preparation["fits"] is True
                        and preparation["prompt_tokens"] + 2048 <= 16384, "actual_request_context_contract_mismatch")
                starts = [e for e in self.by_kind["model_call"] if isinstance(e.get("payload"), dict)
                          and e["payload"].get("call_id") == call_id and e["payload"].get("stage") == "started"]
                start = one(starts, "missing_or_ambiguous_original_call_start")
                require(start["worker_id"] == member and start["sequence"] < original["experience_sequence"],
                        "actual_call_start_order_or_member_mismatch")
                call = {"call_id": call_id, "member": member, "path": str(selected_path),
                    "experience_sequence": original["experience_sequence"], "start_sequence": start["sequence"],
                    "opportunity_id": start["payload"].get("opportunity_id"),
                    "selected_request_sha256": preparation["selected_request_sha256"],
                    "input_ids_sha256": preparation["input_ids_sha256"], "preparation": preparation,
                    "source": source(selected_path), "response_source": source(directory / "response.json")}
                self.calls[call_id], self.message_cache[call_id], self.native[call_id] = call, selected["messages"], body
            except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
                self.gap(str(error), call_id=call_id, raw_request=str(directory))
        expected = {call for call, record in records.items() if record.get("attempt_started") is True}
        if expected != set(self.calls) or expected != set(originals):
            self.gap("not_all_original_attempts_bound", expected=sorted(expected), bound=sorted(self.calls),
                     original_attempts=sorted(originals))

    def _opportunities(self):
        grouped = defaultdict(dict)
        for event in self.by_kind[OPPORTUNITY_VERSION]:
            payload = event.get("payload", {})
            key, phase = payload.get("opportunity_id"), payload.get("phase")
            if not key or phase not in {"before", "after"} or phase in grouped[key]:
                self.gap("malformed_or_duplicate_opportunity_receipt", experience_sequence=event["sequence"])
                continue
            grouped[key][phase] = event
        for key, pair in grouped.items():
            try:
                before, after = pair["before"], pair["after"]
                bp, ap = before["payload"], after["payload"]
                member = bp["member_id"]
                require(before["sequence"] < after["sequence"] and member == ap["member_id"]
                        and bp["opportunity_ordinal"] == ap["opportunity_ordinal"], "opportunity_scope_mismatch")
                calls = [e for e in self.by_kind["model_call"] if isinstance(e.get("payload"), dict)
                         and e["payload"].get("stage") == "started" and e["payload"].get("opportunity_id") == key]
                start = one(calls, "opportunity_not_exactly_one_call_start")
                require(start["worker_id"] == member and before["sequence"] < start["sequence"] < after["sequence"],
                        "opportunity_does_not_contain_same_member_call")
                call_id = start["payload"]["call_id"]
                record = self.budget["records"][call_id]
                reservation = record.get("reservation", record.get("rejected_reservation", {}))
                prep = reservation["preparation"]
                require(start["payload"]["reservation"] == reservation
                        and ap["team_budget"]["records"][call_id] == record, "opportunity_budget_or_preparation_mismatch")
                require(prep["preparation_sha256"] == digest(json_bytes({k: v for k, v in prep.items()
                                                                       if k != "preparation_sha256"}))
                        and prep["window_id"] == "organization-v045:" + self.result["slot_id"]
                        and prep["actor_identity"] == self.result["actor_identity"], "opportunity_preparation_identity_mismatch")
                require(type(bp["team_budget"]["available_tokens"]) is int, "missing_original_opportunity_pool")
                self.opportunities.append({"opportunity_id": key, "ordinal": bp["opportunity_ordinal"],
                    "member": member, "call_id": call_id, "before_sequence": before["sequence"],
                    "after_sequence": after["sequence"], "call_start_sequence": start["sequence"],
                    "world_event_sequence_before": bp["world_event_sequence"], "availability": bp["availability"],
                    "team_budget_before": bp["team_budget"], "preparation": prep,
                    "actual_generation_started": record.get("attempt_started") is True,
                    "terminal_status": ap.get("outcome_status"),
                    "source": self.experience_point(before), "after_source": self.experience_point(after)})
            except (KeyError, IndexError, TypeError, ValueError) as error:
                self.gap(str(error), opportunity_id=key)
        self.opportunities.sort(key=lambda row: row["before_sequence"])
        if {row["call_id"] for row in self.opportunities} != set(self.budget["records"]):
            self.gap("incomplete_original_opportunity_resource_receipts")

    def _actions(self):
        for tool in self.by_kind["tool_call"]:
            payload = tool.get("payload", {})
            response, call_id = payload.get("response", {}), payload.get("model_call_id")
            if response.get("ok") is not True:
                continue
            try:
                call = self.calls[call_id]
                body = self.native[call_id]
                require(body.get("protocol_parse_error") is None, "world_action_from_rejected_native_output")
                choice = one(body.get("choices", []), "ambiguous_native_choice")
                native = one(choice.get("message", {}).get("tool_calls", []), "not_one_original_native_tool")
                require(native["function"]["name"] == payload["action"]
                        and json.loads(native["function"]["arguments"]) == payload["arguments"]
                        and native["id"] == payload["model_tool_call_id"], "native_world_action_mismatch")
                link = one([e for e in self.by_kind["model_action_link"]
                    if e.get("payload", {}).get("model_call_id") == call_id
                    and e["payload"].get("world_action_id") == response.get("action_id")], "unbound_world_action_link")
                feedback = one([e for e in self.by_kind["model_tool_result"]
                    if e.get("payload", {}).get("call_id") == call_id], "unbound_original_world_feedback")
                lp, fp = link["payload"], feedback["payload"]
                require(call["member"] == tool["worker_id"] == link["worker_id"] == feedback["worker_id"]
                        and payload["decision_id"] == lp["decision_id"] == call_id
                        and payload["model_tool_call_id"] == lp["model_tool_call_id"] == fp["model_tool_call_id"],
                        "world_action_member_or_decision_mismatch")
                require(response == lp["world_response"] == fp["world_response"]
                        and response.get("command_committed") is True
                        and response.get("command_id") == lp["world_command_id"]
                        and bool(response.get("action_id")) and bool(response.get("command_id")), "world_receipt_not_committed")
                require(call["experience_sequence"] < tool["sequence"] < link["sequence"] < feedback["sequence"],
                        "world_action_experience_order_mismatch")
                action_id = response["action_id"]
                require(action_id not in self.action_calls, "duplicate_committed_world_action")
                self.action_calls[action_id] = call
                self.action_receipts[action_id] = {"call_id": call_id, "member": call["member"],
                    "action": payload["action"], "arguments": payload["arguments"], "response": response,
                    "tool_sequence": tool["sequence"], "feedback_sequence": feedback["sequence"],
                    "source": self.experience_point(tool), "native_response": call["response_source"]}
            except (KeyError, IndexError, TypeError, ValueError) as error:
                self.gap(str(error), call_id=call_id, experience_sequence=tool["sequence"])
        for event in self.events:
            if event.get("actor_id") not in self.registry or not base.actual_event(event) or not event.get("action_id"):
                continue
            if self.bound(event):
                continue
            if event.get("kind") == "member_retired":
                # The existing strict staff_done binding covers its separate runtime retirement action.
                try:
                    path = self.folder / "runtime-opportunities.jsonl"
                    opportunities = [json.loads(line) for line in path.read_text().splitlines()]
                    lifecycle.bind_retirement(event, state=self.state, result=self.result,
                        evidence=self.evidence, budget=self.budget, inputs=self, experience=self.experience,
                        opportunities=opportunities, folder=self.folder)
                    continue
                except (OSError, KeyError, IndexError, TypeError, ValueError):
                    pass
            self.gap("member_world_event_without_original_native_binding", event=self.point(event))

    def by_member(self, member):
        return sorted((c for c in self.calls.values() if c["member"] == member), key=lambda c: c["experience_sequence"])

    def messages(self, call):
        return self.message_cache[call["call_id"]]

    def bound(self, event):
        if not event.get("operation_id"):
            originals = [row for row in self.events if all(row.get(key) == event.get(key)
                for key in ("sequence", "kind", "actor_id", "action_id"))]
            if len(originals) != 1:
                return None
            event = originals[0]
        call = self.action_calls.get(event.get("action_id"))
        if not base.actual_event(event) or not call or call["member"] != event.get("actor_id"):
            return None
        receipt = self.action_receipts[event["action_id"]]
        if event.get("operation_id") != receipt["response"]["command_id"]:
            return None
        return call

    def resource(self, call_or_opportunity):
        call_id = call_or_opportunity["call_id"]
        found = [row for row in self.opportunities if row["call_id"] == call_id]
        if len(found) != 1:
            return {"status": "measurement_pending", "call_id": call_id, "reason": "missing_unique_opportunity_receipt"}
        row = found[0]
        prep, pool = row["preparation"], row["team_budget_before"]
        try:
            prompt, reserved, limit = (prep[key] for key in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
            require(all(type(v) is int for v in (prompt, reserved, limit)) and reserved == 2048 and limit == 16384,
                    "incomplete_original_preparation_counts")
            later = [r for r in self.opportunities if r["member"] == row["member"]
                     and r["before_sequence"] > row["after_sequence"]]
            return {"status": "recorded", "call_id": call_id, "member": row["member"],
                "opportunity_id": row["opportunity_id"], "opportunity_ordinal": row["ordinal"],
                "actual_generation_started": row["actual_generation_started"],
                "prompt_tokens": prompt, "reserved_output_tokens": reserved, "context_limit": limit,
                "hard_headroom_tokens": limit - prompt - reserved,
                "team_available_tokens_before_opportunity": pool["available_tokens"],
                "remaining_decisions_before_opportunity": pool.get("remaining_decisions"),
                "remaining_attempts_before_opportunity": pool.get("remaining_attempts"),
                "later_member_opportunities": len(later),
                "later_member_actual_generations": sum(r["actual_generation_started"] for r in later),
                "later_member_call_ids": [r["call_id"] for r in later], "source": row["source"],
                "scope": "Original before-opportunity pool and sealed selected-request preparation; no final-balance substitution or new encoding."}
        except (KeyError, TypeError, ValueError) as error:
            return {"status": "measurement_pending", "call_id": call_id, "reason": str(error)}

    def acquired_input(self, member, predicate, *, after_sequence, before_sequence=None):
        for call in self.by_member(member):
            if call["experience_sequence"] <= after_sequence or before_sequence is not None and call["experience_sequence"] > before_sequence:
                continue
            for index, message in enumerate(self.messages(call)):
                value = content(message)
                if predicate(message, value):
                    return {**call, "message_index": index,
                        "source": {**call["source"], "json_pointer": f"/messages/{index}"}, "resource": self.resource(call)}
        return None

    def first_share_opportunity(self, producer, produced_event, *, earliest_actual_knowledge=None):
        origin = self.bound(produced_event)
        if origin is None:
            return {"status": "measurement_pending", "reason": "unbound_production_event"}
        threshold = self.action_receipts[produced_event["action_id"]]["tool_sequence"]
        for row in self.opportunities:
            if row["member"] != producer or row["before_sequence"] <= threshold:
                continue
            if (earliest_actual_knowledge is not None and row["call_id"] != earliest_actual_knowledge["call_id"]
                    and row["before_sequence"] < earliest_actual_knowledge["experience_sequence"]):
                continue
            partners = [member for member, state in row["availability"].items()
                        if member != producer and state.get("can_receive_work") is True]
            if partners and row["team_budget_before"].get("remaining_decisions", 0) > 0:
                return {"status": "recorded_eligible_opportunity", "eligible_partners": partners,
                    "resource": self.resource(row), "semantic_usefulness": "not_inferred",
                    "scope": "Producer could attempt a legal share of existing work; rejected generation and private knowledge are kept separate."}
        return {"status": "no_recorded_eligible_share_opportunity", "resource": None,
                "semantic_usefulness": "not_inferred"}


def declared_units(case):
    symbols = case.get("source_contract", {}).get("contract_symbols", {})
    public = case.get("source_contract", {}).get("public_production_files", list(symbols))
    editable = set(case.get("editable_paths", []))
    selected = [(path, symbol) for path in public if path in editable
                for symbol in symbols.get(path, [])]
    if "test_member.py" in editable:
        selected.append(("test_member.py", None))
    return selected


def current_program_work(data):
    outcomes, non_work = [], []
    declarations = declared_units(data.software.get("case", {}))
    if not declarations:
        data.gap("missing_declared_editable_production_units")
    for event in data.events:
        if event.get("kind") != "edit" or not data.bound(event):
            continue
        path = event.get("path")
        names = [symbol for declared_path, symbol in declarations if declared_path == path]
        before, before_path, before_error = data.versions.get(event.get("previous_reference"))
        after, after_path, after_error = data.versions.get(event.get("source_reference"))
        initial_reference = data.registry[event["actor_id"]].get("initial_source_reference")
        initial, initial_path, initial_error = data.versions.get(initial_reference)
        for symbol in names:
            original, produced = unit(before, path, symbol), unit(after, path, symbol)
            initial_unit = unit(initial, path, symbol)
            reason = before_error or after_error or initial_error
            if not reason and (original["status"] not in {"supported", "absent"}
                               or initial_unit["status"] not in {"supported", "absent"} or produced["status"] != "supported"):
                reason = "unsupported_current_unit_syntax"
            if not reason and (digest(before.get(path, "").encode()) != event.get("before_sha256")
                               or digest(after[path].encode()) != event.get("after_sha256")):
                reason = "edit_file_bytes_not_bound_to_version"
            changed = None if reason else (original.get("fingerprint") != produced.get("fingerprint")
                                          and initial_unit.get("fingerprint") != produced.get("fingerprint"))
            item = {"work_id": f"program:{event['sequence']}:{path}:{symbol or '<file>'}",
                "work_kind": "member_test_program" if path == "test_member.py" else "production_program",
                "source_member": event["actor_id"], "path": path, "symbol": symbol,
                "production": data.point(event), "source_reference": event["source_reference"],
                "previous_reference": event["previous_reference"], "before_version_path": before_path,
                "initial_reference": initial_reference, "initial_version_path": initial_path,
                "initial_unit": initial_unit,
                "produced_version_path": after_path, "previous_unit": original, "produced_unit": produced,
                "stage": stage(changed, "measurement_pending" if reason else
                    "current_structural_member_work" if changed else "no_structural_change", reason=reason),
                "first_eligible_share_opportunity": data.first_share_opportunity(event["actor_id"], event),
                "origin": "original_member_edit", "initial_code_is_member_work": False}
            (outcomes if changed is not False else non_work).append(item)
    return outcomes, non_work


def legal_patch(data, patch, recipient):
    if not data.bound(patch):
        return stage(None, "measurement_pending", reason="unbound_original_patch_publication")
    reference = patch.get("source_reference")
    files, path, error = data.versions.get(reference)
    if error:
        return stage(None, "measurement_pending", reason=error)
    if digest(json_bytes(files)) != patch.get("files_sha256"):
        return stage(None, "measurement_pending", reason="fixed_patch_files_digest_mismatch")
    grants = [row for row in data.state.get("shares", [])
              if row.get("project_id") == base.PROJECT and base.ref_key(row) == base.ref_key(reference)
              and row.get("shared_by") == patch["actor_id"] and recipient in row.get("actor_ids", [])
              and row.get("at") == patch.get("logical_time")]
    if not grants:
        return stage(None, "measurement_pending", reason="no_exact_version_recipient_authorization")
    return stage(True, "legally_published_fixed_version", publication=data.point(patch),
                 authorized_recipient=recipient, source_reference=reference,
                 version_path=path, exact_version_grants=grants, metadata_is_content_acquisition=False)


def retained_descendant(data, member, start, end, work):
    """Follow original version edges; a later equal AST alone is insufficient."""
    current, visited = base.ref_key(end), set()
    target = base.ref_key(start)
    if current is None or target is None:
        return None, "invalid_retention_reference"
    while current != target:
        if current in visited:
            return None, "cyclic_version_lineage"
        visited.add(current)
        edges = [event for event in data.events if event.get("actor_id") == member
                 and event.get("kind") in {"edit", "integrate"} and data.bound(event)
                 and base.ref_key(event.get("source_reference")) == current]
        if len(edges) != 1:
            return None, "missing_or_ambiguous_recipient_version_lineage"
        edge = edges[0]
        files, _, error = data.versions.get(edge["source_reference"])
        check = unit(files, work["path"], work["symbol"])
        if error or check["status"] != "supported":
            return None, error or "unsupported_retained_unit"
        if check["fingerprint"] != work["produced_unit"]["fingerprint"]:
            return False, "exact_shared_unit_changed_on_version_path"
        current = base.ref_key(edge.get("previous_reference"))
        if current is None:
            return None, "missing_recipient_previous_reference"
    return True, None


def program_transfers(data, patch, recipient):
    transfers = []
    for event in data.events:
        if not data.bound(event) or event["sequence"] <= patch["sequence"]:
            continue
        if event.get("kind") == "integrate" and event.get("actor_id") == recipient and event.get("patch_id") == patch["patch_id"]:
            transfers.append({"event": event, "route": "explicit_patch_import", "input_reference": event.get("input_reference"),
                "previous_reference": event.get("previous_reference"), "source_reference": event.get("source_reference")})
        elif (event.get("kind") == "member_spawned" and event.get("member_id") == recipient
              and event.get("initial_patch_id") == patch["patch_id"]):
            transfers.append({"event": event, "route": "authorized_snapshot_at_member_birth",
                "input_reference": event.get("initial_source_reference"), "previous_reference": None,
                "source_reference": event.get("workspace_reference")})
    return transfers


def actual_patch_acquisition(data, work, patch, recipient):
    points = []
    for transfer in program_transfers(data, patch, recipient):
        event = transfer["event"]
        if transfer["input_reference"] != patch["source_reference"]:
            points.append(stage(None, "measurement_pending", reason="import_does_not_bind_exact_published_version",
                                event=data.point(event)))
            continue
        files, _, error = data.versions.get(transfer["source_reference"])
        if error or work["path"] not in files:
            points.append(stage(None, "measurement_pending", reason=error or "acquired_workspace_missing_work_path"))
            continue
        recipient_first = next((row for row in data.opportunities if row["member"] == recipient
                                and row["before_sequence"] > data.action_receipts[event["action_id"]]["tool_sequence"]), None)
        points.append(stage(True, "exact_version_imported_to_recipient_workspace", route=transfer["route"],
            event=data.point(event), acquired_workspace_reference=transfer["source_reference"], recipient_actual_input=None,
            ordering_sequence=data.action_receipts[event["action_id"]]["tool_sequence"], resource=data.resource(data.bound(event)),
            acquisition_resource_actor=data.bound(event)["member"],
            recipient_first_later_opportunity=data.resource(recipient_first) if recipient_first else None,
            import_alone_is_use=False))
    for event in data.events:
        call = data.bound(event)
        if not call or event["actor_id"] != recipient or event["sequence"] <= patch["sequence"]:
            continue
        if event["kind"] != "read" or event.get("patch_id") != patch["patch_id"] or event.get("source_reference") != patch["source_reference"]:
            continue
        receipt = data.action_receipts[event["action_id"]]
        received = receipt["response"].get("result", {})
        if received.get("path") != work["path"]:
            continue
        files, _, error = data.versions.get(patch["source_reference"])
        full = files.get(work["path"], "").splitlines()
        bounds = work["produced_unit"]
        start, end = bounds.get("start_line", 1), bounds.get("end_line", len(full))
        expected = "\n".join(full[start - 1:end])
        if error or not expected or expected not in received.get("text", ""):
            continue
        actual = data.acquired_input(recipient, lambda message, value: message.get("role") == "tool"
                                     and value == receipt["response"], after_sequence=receipt["feedback_sequence"])
        if actual:
            points.append(stage(True, "exact_work_content_in_actual_recipient_input", event=data.point(event),
                recipient_actual_input=actual, ordering_sequence=actual["experience_sequence"],
                resource=actual["resource"], reading_alone_is_use=False))
    proven = [point for point in points if point["value"] is True]
    if proven:
        return min(proven, key=lambda row: row["ordering_sequence"])
    return points[0] if points else stage(False, "no_recorded_actual_acquisition", resource=None,
        scope="Public metadata, a permitted read not later presented, and reachable content do not establish acquisition.")


def tested_import(data, work, patch, recipient):
    pending = []
    for transfer in program_transfers(data, patch, recipient):
        imported = transfer["event"]
        before, _, before_error = (data.versions.get(transfer["previous_reference"])
                                  if transfer["previous_reference"] else ({}, None, None))
        after, _, after_error = data.versions.get(transfer["source_reference"])
        a = unit(before, work["path"], work["symbol"]) if transfer["previous_reference"] else {"status": "absent", "fingerprint": None}
        b = unit(after, work["path"], work["symbol"])
        if before_error or after_error or a["status"] not in {"supported", "absent"} or b["status"] != "supported":
            pending.append("unavailable_imported_unit")
            continue
        if a.get("fingerprint") == work["produced_unit"]["fingerprint"]:
            continue  # Already independently present is not evidence of new adoption.
        if transfer["input_reference"] != patch["source_reference"] or b["fingerprint"] != work["produced_unit"]["fingerprint"]:
            pending.append("import_conflict_or_derived_unit_needs_semantic_review")
            continue
        for test in data.events:
            if (test.get("kind") != "test" or test.get("actor_id") != recipient or not data.bound(test)
                    or test["sequence"] <= imported["sequence"]):
                continue
            executed = (test.get("groups", {}).get("member_tests", {}).get("executed") is True
                        if work["work_kind"] == "member_test_program" else legacy.public_test_executed(test))
            if not executed:
                continue
            retained, reason = retained_descendant(data, recipient, transfer["source_reference"], test.get("source_reference"), work)
            if retained is not True:
                pending.append(reason or "unknown_retained_test_version")
                continue
            return stage(True, "changed_imported_member_unit_actually_tested", integration=data.point(imported),
                acquisition_route=transfer["route"],
                test=data.point(test), test_groups=copy.deepcopy(test.get("groups", {})),
                resource=data.resource(data.bound(test)), tested_reference=test["source_reference"],
                exact_lineage_start=transfer["source_reference"],
                scope="Actual verification of adopted work, even when tests fail. No unique authorship, causal gain, or semantic improvement claim.")
    if pending:
        return stage(None, "measurement_pending", reasons=sorted(set(pending)), resource=None)
    return stage(False, "no_verified_use_after_acquisition", resource=None)


def fixed_delivery_link(data, work, recipient, used):
    if used["value"] is not True:
        return stage(False if used["value"] is False else None, "no_evidenced_use_to_link")
    final = base.final_evidence(data.result, data.events, data.state_path)
    delivery = final.get("delivery")
    if delivery is None:
        return stage(False, "used_but_no_final_fixed_delivery", recorded_R=data.result.get("R"))
    if delivery["actor_id"] != recipient:
        return stage(None, "measurement_pending", reason="other_final_author_requires_multihop_evidence", delivery=delivery)
    if not data.bound(delivery) or final.get("status") != "recorded_fixed_delivery":
        return stage(None, "measurement_pending", reason="unbound_final_fixed_delivery_or_current_test")
    if delivery["sequence"] < used["test"]["sequence"]:
        return stage(False, "use_occurred_after_final_fixed_delivery")
    retained, reason = retained_descendant(data, recipient, used["exact_lineage_start"], delivery["source_reference"], work)
    return stage(retained, "use_linked_to_final_fixed_delivery" if retained is True else
                 "exact_unit_not_retained_in_final_delivery" if retained is False else "measurement_pending",
                 reason=reason, delivery=delivery, recorded_R=data.result.get("R"),
                 final_success_is_separate_from_use=True)


def program_relations(data, works):
    rows = []
    for work in works:
        producer = work["source_member"]
        publications = []
        for patch in data.events:
            if (patch.get("kind") != "patch_fixed" or patch.get("actor_id") != producer
                    or patch["sequence"] <= work["production"]["sequence"]):
                continue
            files, _, error = data.versions.get(patch.get("source_reference"))
            retained = unit(files, work["path"], work["symbol"])
            if not error and retained["status"] == "supported" and retained["fingerprint"] == work["produced_unit"].get("fingerprint"):
                publications.append(patch)
        recipients = [member for member in data.registry if member != producer]
        if not recipients:
            rows.append({"work_id": work["work_id"], "source_member": producer, "recipient": None,
                "work_kind": "program", "stages": {"produced": work["stage"], **{
                    name: stage(False, "not_applicable_no_partner") for name in STAGES[1:]}},
                "first_eligible_share_opportunity": {"status": "not_applicable_no_partner"}})
            continue
        for recipient in recipients:
            selected = publications or [None]
            for patch in selected:
                published = (legal_patch(data, patch, recipient) if patch is not None else
                             stage(False, "current_work_not_published"))
                acquired = (actual_patch_acquisition(data, work, patch, recipient) if published["value"] is True else
                            stage(False if published["value"] is False else None, "not_acquired_without_bound_publication", resource=None))
                used = (tested_import(data, work, patch, recipient) if acquired["value"] is True else
                        stage(False if acquired["value"] is False else None, "no_acquired_work_to_use", resource=None))
                # A later independent edit is never promoted by structural similarity.
                if acquired["value"] is True and used["value"] is False:
                    following = [data.point(e) for e in data.events if e.get("actor_id") == recipient
                        and e.get("kind") == "edit" and data.bound(e)
                        and data.bound(e)["experience_sequence"] >= acquired.get("ordering_sequence", 0)]
                    if following and acquired["status"] == "exact_work_content_in_actual_recipient_input":
                        used = stage(None, "measurement_pending", reason="read_then_revision_requires_semantic_use_evidence",
                                     subsequent_revisions=following, resource=None)
                rows.append({"work_id": work["work_id"], "work_kind": "program", "source_member": producer,
                    "recipient": recipient, "path": work["path"], "symbol": work["symbol"],
                    "patch_id": patch.get("patch_id") if patch else None,
                    "stages": {"produced": work["stage"], "published": published, "acquired": acquired,
                               "used": used, "fixed_delivery": fixed_delivery_link(data, work, recipient, used)},
                    "first_eligible_share_opportunity": work["first_eligible_share_opportunity"]})
    return rows


def message_input(data, message):
    sender = data.bound(message)
    if sender is None:
        return None
    recipient = message.get("recipient", message.get("member_id"))
    body = message.get("body", message.get("briefing", ""))

    def exact_received(native_message, value):
        observation = value.get("observation", {})
        if not isinstance(observation, dict):
            return False
        if message["kind"] == "member_spawned":
            return (native_message.get("role") == "user" and observation.get("actor_id") == recipient
                    and bool(body) and observation.get("own_initial_briefing") == body)
        candidates = observation.get("messages", []) if observation.get("actor_id") == recipient else []
        if native_message.get("role") == "tool" and value.get("ok") is True and isinstance(value.get("result"), dict):
            candidates = [*candidates, value["result"]]
        return any(isinstance(row, dict) and row.get("sequence") == message["sequence"]
                   and row.get("actor_id") == message["actor_id"] and row.get("recipient") == recipient
                   and row.get("body") == body and isinstance(body, str) and bool(body) for row in candidates)

    return data.acquired_input(recipient, exact_received,
        after_sequence=data.action_receipts[message["action_id"]]["tool_sequence"])


def report_page_inputs(data, report, member, *, before_sequence=None):
    matches = []
    for call in data.by_member(member):
        if before_sequence is not None and call["experience_sequence"] > before_sequence:
            continue
        for index, message in enumerate(data.messages(call)):
            value = content(message)
            result = value.get("result", {})
            if message.get("role") != "tool" or value.get("ok") is not True or not isinstance(result, dict):
                continue
            if result.get("report_id") != report["report_id"] or result.get("body_sha256") != report["body_sha256"]:
                continue
            page = result.get("page", {})
            original = next((p for p in report["pages"] if p.get("index") == page.get("index")), None)
            if original != page:
                continue
            matches.append({"page_index": page["index"], "page_text": page["text"],
                "actual_input": {**call, "message_index": index,
                    "source": {**call["source"], "json_pointer": f"/messages/{index}"},
                    "resource": data.resource(call)}})
    return matches


def current_information_work(data):
    outcomes, initial_reexecutions = [], []
    for report_id, report in data.software.get("test_reports", {}).items():
        identity = report.get("event_identity", {})
        tests = [event for event in data.events if event.get("kind") == "test"
                 and event.get("sequence") == identity.get("test_event_sequence")]
        if len(tests) != 1 or not data.bound(tests[0]):
            data.gap("private_report_not_bound_to_original_member_test", report_id=report_id)
            continue
        test = tests[0]
        visible = report.get("visible_result", {})
        try:
            require(report_id == report["report_id"] and report["actor_id"] == test["actor_id"]
                    and identity["operation_id"] == test["operation_id"], "test_report_identity_mismatch")
            require(report["body"] == json_bytes(visible).decode()
                    and report["body_sha256"] == digest(report["body"].encode()), "test_report_original_body_mismatch")
            files, _, error = data.versions.get(test.get("source_reference"))
            require(not error and visible.get("source_reference") == test.get("source_reference")
                    and visible.get("files_sha256") == test.get("files_sha256") == digest(json_bytes(files)),
                    "test_report_work_version_mismatch")
            initial, _, initial_error = data.versions.get(data.registry[test["actor_id"]].get("initial_source_reference"))
            require(not initial_error, "missing_report_author_initial_version")
        except (KeyError, TypeError, ValueError) as error:
            data.gap(str(error), report_id=report_id)
            continue
        repeated_initial = files == initial
        seen = report_page_inputs(data, report, test["actor_id"])
        first_seen = min((row["actual_input"] for row in seen), key=lambda row: row["experience_sequence"], default=None)
        item = {"work_id": "information:" + report_id, "work_kind": "current_version_test_result",
            "source_member": test["actor_id"], "production": data.point(test), "report_id": report_id,
            "source_reference": test["source_reference"], "files_sha256": test["files_sha256"],
            "body_sha256": report["body_sha256"], "body_characters": len(report["body"]),
            "report_source": {**data.world_source, "json_pointer":
                "/projects/SOFTWARE27/software/test_reports/" + report_id.replace("~", "~0").replace("/", "~1")},
            "stage": stage(True, "recorded_member_test_execution_result"),
            "initial_material_reexecution": repeated_initial,
            "initial_facts_are_new_member_discoveries": False,
            "producer_actual_page_inputs": [{k: v for k, v in row.items() if k != "page_text"} for row in seen],
            "first_eligible_share_opportunity": data.first_share_opportunity(test["actor_id"], test,
                earliest_actual_knowledge=first_seen) if first_seen else {
                    "status": "no_actual_producer_knowledge_of_saved_report", "resource": None},
            "scope": "A report on the author's initial files is an initial-material reexecution. A new version's actual result is current investigation work, not necessarily a novel fact or a useful contribution."}
        (initial_reexecutions if repeated_initial else outcomes).append(item)
    return outcomes, initial_reexecutions


def information_relations(data, works, initial_reexecutions):
    """Mechanically establish provenance and acquisition; never infer semantics."""
    rows, forwardings, unknown_messages = [], [], []
    messages = [event for event in data.events if data.bound(event) and (
        event.get("kind") == "work_message" or event.get("kind") == "member_spawned" and event.get("briefing"))]
    claimed = set()
    for work in [*works, *initial_reexecutions]:
        report = data.software["test_reports"][work["report_id"]]
        producer = work["source_member"]
        shares = []
        for message in messages:
            if message["actor_id"] != producer or message["sequence"] <= work["production"]["sequence"]:
                continue
            body = message.get("body", message.get("briefing", ""))
            pages = report_page_inputs(data, report, producer,
                                      before_sequence=data.bound(message)["experience_sequence"])
            exact = [page for page in pages if page["page_text"] and page["page_text"] in body]
            if not exact:
                continue
            claimed.add(message["sequence"])
            recipient = message.get("recipient", message.get("member_id"))
            actual = message_input(data, message)
            following = [event for event in data.events if actual and event.get("actor_id") == recipient
                and event.get("kind") in {"edit", "test", "integrate", "patch_fixed", "submit"} and data.bound(event)
                and data.bound(event)["experience_sequence"] >= actual["experience_sequence"]]
            shared = {"message": data.point(message), "body": body,
                "exact_original_page_indices": sorted({page["page_index"] for page in exact}),
                "sender_page_input_evidence": [{k: v for k, v in page.items() if k != "page_text"} for page in exact]}
            if work["initial_material_reexecution"]:
                forwardings.append({"source_member": producer, "recipient": recipient,
                    "origin": "initial_material_reexecution", "current_member_work_reuse": False,
                    "publication": shared, "actual_recipient_input": actual,
                    "status": "exact_initial_material_forwarding" if actual else "initial_material_sent_not_actually_acquired"})
                shares.append(message["sequence"])
                continue
            # No outcome/R restriction: a positive semantic review could include failed business work.
            used = (stage(None, "measurement_pending", reason="information_adoption_requires_source_semantic_review",
                          following_member_work=[data.point(event) for event in following],
                          candidate_action_resources=[data.resource(data.bound(event)) for event in following],
                          resource=None) if actual and following else
                    stage(False, "no_recorded_work_using_the_acquired_information", resource=None))
            rows.append({"work_id": work["work_id"], "work_kind": "information", "source_member": producer,
                "recipient": recipient, "report_id": work["report_id"],
                "stages": {"produced": work["stage"], "published": stage(True, "exact_current_report_text_legally_addressed", **shared),
                    "acquired": stage(bool(actual), "exact_message_in_actual_recipient_input" if actual else
                                      "addressed_message_without_actual_recipient_input", actual_input=actual,
                                      resource=actual["resource"] if actual else None),
                    "used": used, "fixed_delivery": stage(None if used["value"] is None else False,
                        "information_use_not_yet_evidenced", recorded_R=data.result.get("R"))},
                "first_eligible_share_opportunity": work["first_eligible_share_opportunity"],
                "criterion": "Exact provenance and actual reading establish acquisition only. Later actions, citation, or a matching final R do not establish information use."})
            shares.append(message["sequence"])
        if not shares and not work["initial_material_reexecution"]:
            partners = [member for member in data.registry if member != producer]
            rows.append({"work_id": work["work_id"], "work_kind": "information", "source_member": producer,
                "recipient": None, "report_id": work["report_id"],
                "stages": {"produced": work["stage"], **{key: stage(False,
                    "current_report_not_shared" if partners else "not_applicable_no_partner") for key in STAGES[1:]}},
                "first_eligible_share_opportunity": work["first_eligible_share_opportunity"]})
    initial = data.software.get("initial_diagnostics", {})
    for message in messages:
        if message["sequence"] in claimed:
            continue
        body = message.get("body", message.get("briefing", ""))
        referenced = [key for key in initial if key in body]
        exact_initial = [key for key, value in initial.items()
                         if json_bytes(value).decode().strip() in body or json.dumps(value, ensure_ascii=False) in body]
        recipient = message.get("recipient", message.get("member_id"))
        actual = message_input(data, message)
        if referenced or exact_initial:
            forwardings.append({"source_member": message["actor_id"], "recipient": recipient,
                "origin": "environment_initial_diagnostic", "current_member_work_reuse": False,
                "message": data.point(message), "body": body, "initial_ids_mentioned": referenced,
                "exact_initial_reports_in_message": exact_initial, "actual_recipient_input": actual,
                "status": "exact_initial_material_forwarding" if exact_initial and actual else
                          "initial_material_reference_requires_review"})
        if not exact_initial:
            unknown_messages.append({"source_member": message["actor_id"], "recipient": recipient,
                "message": data.point(message), "body": body, "actual_recipient_input": actual,
                "status": "measurement_pending", "reason": "free_text_current_work_origin_and_use_not_mechanically_proved",
                "initial_material_ids_mentioned": referenced,
                "scope": "Specific investigation, advice, summaries, or initial-material relays require source inspection; none is automatically credited."})
    return rows, forwardings, unknown_messages


def aggregate(rows, stage_name):
    values = [row["stages"][stage_name]["value"] for row in rows]
    return True if True in values else None if None in values else False


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    header = {"version": VERSION, "episode": str(folder), "read_only": True,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_world_actions": 0,
        "new_test_or_acceptance_executions": 0, "training_support": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "has_evidenced_cross_member_chain": None, "has_evidenced_cross_member_use": None,
        "has_use_linked_to_final_fixed_delivery": None, "program_work_chains": [],
        "information_work_chains": [], "measurement_gaps": [], "totals": {}}
    try:
        data = Evidence(folder)
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        return {**header, "status": "measurement_pending", "measurement_gaps": [{"reason": str(error)}]}
    result, case = data.result, data.software.get("case", {})
    initial_members = result.get("member_lifecycle", {}).get("initial_members", [])
    condition = result.get("condition", case.get("condition"))
    if not data.registry or not initial_members:
        data.gap("missing_original_member_registry_or_initial_members")
    if condition == "S1" and (len(data.registry) != 1 or len(initial_members) != 1):
        data.gap("s1_contains_hidden_partner_or_birth")
    program, non_work = current_program_work(data)
    program_rows = program_relations(data, program)
    information, reexecutions = current_information_work(data)
    info_rows, initial_forwarding, info_pending = information_relations(data, information, reexecutions)
    rows = program_rows + info_rows
    for row in rows:
        if row["stages"]["produced"]["value"] is not True:
            for key in ("used", "fixed_delivery"):
                if row["stages"][key]["value"] is True:
                    row["stages"][key] = stage(None, "measurement_pending", reason="current_work_production_not_proved")
    program_chains = [row for row in program_rows if row["stages"]["used"]["value"] is True]
    info_chains = [row for row in info_rows if row["stages"]["used"]["value"] is True]
    unresolved = [row for row in rows if any(row["stages"][key]["value"] is None for key in STAGES[:4])]
    use = aggregate(rows, "used")
    if use is False and (data.gaps or unresolved or info_pending):
        use = None
    fixed = aggregate(rows, "fixed_delivery")
    if fixed is False and (data.gaps or use is None):
        fixed = None
    no_partner = len(data.registry) == 1 and condition == "S1"
    if no_partner and not data.gaps:
        use = fixed = False
    member_work = {}
    for member, registry in data.registry.items():
        own = [event for event in data.events if event.get("actor_id") == member and data.bound(event)]
        member_work[member] = {"origin": registry.get("origin", "initial_configuration"),
            "actual_output_calls": len(data.by_member(member)), "actual_event_counts": dict(Counter(e["kind"] for e in own)),
            "current_program_work": sum(work["source_member"] == member and work["stage"]["value"] is True for work in program),
            "current_information_work": sum(work["source_member"] == member for work in information),
            "initial_material_reexecutions": sum(work["source_member"] == member for work in reexecutions)}
    return {**header, "status": "measurement_pending" if data.gaps else "measured", "slot_id": result.get("slot_id"),
        "purpose": result.get("purpose"), "condition": condition, "recorded_R": result.get("R"),
        "recorded_submitted": result.get("submitted"), "has_evidenced_cross_member_chain": use,
        "has_evidenced_cross_member_use": use, "has_use_linked_to_final_fixed_delivery": fixed,
        "cross_member_applicability": "not_applicable_no_partner" if no_partner else "applicable",
        "member_work": member_work, "current_program_work": program, "nonstructural_or_initial_program_edits": non_work,
        "current_information_work": information, "initial_material_reexecutions": reexecutions,
        "initial_material_forwarding": initial_forwarding, "five_stage_relations": rows,
        "program_work_chains": program_chains, "information_work_chains": info_chains,
        "pending_program_relations": [row for row in unresolved if row["work_kind"] == "program"],
        "pending_semantic_relations": info_pending + [row for row in unresolved if row["work_kind"] == "information"],
        "measurement_gaps": data.gaps, "final_delivery": base.final_evidence(result, data.events, data.state_path),
        "totals": {"observed_members": len(data.registry), "initial_members": len(initial_members),
            "current_program_artifacts": sum(work["stage"]["value"] is True for work in program),
            "current_information_artifacts": len(information), "evidenced_program_work_chains": len(program_chains),
            "evidenced_information_work_chains": len(info_chains),
            "chains_closed_to_final_fixed_delivery": sum(row["stages"]["fixed_delivery"]["value"] is True for row in rows),
            "initial_material_forwardings": len(initial_forwarding), "initial_material_reexecutions": len(reexecutions),
            "pending_program_relations": sum(row["work_kind"] == "program" for row in unresolved),
            "information_candidates_needing_manual_review": len(info_pending) + sum(row["work_kind"] == "information" for row in unresolved),
            "model_requested_births": sum(event.get("kind") == "member_spawned" and data.bound(event) is not None for event in data.events)},
        "first_stage_opportunities": [{"work_id": row["work_id"], "recipient": row.get("recipient"),
            "first_eligible_sharing": row["first_eligible_share_opportunity"],
            "first_actual_acquisition": row["stages"]["acquired"].get("resource"),
            "first_verified_use": row["stages"]["used"].get("resource")} for row in rows],
        "sources": {"result": source(data.result_path), "world": data.world_source,
            "experience": data.experience_source, "organization_evidence": source(data.evidence_path),
            "team_budget": source(data.budget_path)},
        "criterion": "Five stages are separate. True use requires original current-work provenance and actual verifiable partner consumption; false requires complete evidence, null preserves missing/semantic evidence. Reading, accessibility, similar code and multiple members are not use. R and delivery success never select eligible use evidence.",
        "information_scope": "Current report creation, authorized exact text transmission and actual input acquisition are mechanical. Free-text advice or acquisition followed by work remains pending until an independent source inspection establishes a specific use; no semantic verdict is fabricated."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json_bytes(measure_episode(args.episode))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered)
    else:
        print(rendered.decode(), end="")


if __name__ == "__main__":
    main()

