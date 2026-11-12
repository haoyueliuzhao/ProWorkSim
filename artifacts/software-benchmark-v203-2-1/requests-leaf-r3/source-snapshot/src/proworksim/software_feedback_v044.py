"""v044 ordinary format feedback lifecycle; archive and actual prompt are distinct.

Only the runner registers feedback. JSON field names alone confer no provenance.
A selected request plus an actual token trace and settled usage establish
presentation. Supersession and syntactic recovery never establish business success.
"""
from __future__ import annotations

import copy
from functools import cache
import json

from .storage import digest, json_bytes

VERSION = "ordinary-format-feedback-v0.44"
ACTIVE = "pending_or_presented"
HISTORICAL = frozenset({"superseded", "historicalized_after_legal_native_schema"})
DIAGNOSTIC_FIELDS = ("stage", "reason", "constraint", "field_path", "schema_path",
                     "expected_type", "observed_type", "position", "missing_fields")


def event_identity(kind, payload):
    """Stable identity of the unchanged runner payload, independent of recorder sequence."""
    return "runner-event:" + digest(json_bytes({"kind": kind, "payload": payload}))


def feedback_message(feedback):
    return {"role": "user", "content": json.dumps({"public_format_feedback": feedback},
            ensure_ascii=False, allow_nan=False)}


def compact_feedback(feedback):
    """Preserve actual correction facts, including separate native/adapter failures."""
    diagnostics = feedback["parse_diagnostics"]
    result = {key: copy.deepcopy(feedback[key]) for key in
              ("model_call_id", "status", "reason", "world_action_executed")}
    result["parse_diagnostics"] = {}
    for name in ("native_parser", "adapter_parser"):
        source = diagnostics[name]
        item = {"status": source["status"]}
        if source.get("tool_name") is not None:
            item["tool_name"] = copy.deepcopy(source["tool_name"])  # observed, never supplied or corrected
        if source.get("failure") is not None:
            item["failure"] = {key: copy.deepcopy(source["failure"][key])
                               for key in DIAGNOSTIC_FIELDS if key in source["failure"]}
        else:
            item["failure"] = None
        result["parse_diagnostics"][name] = item
    return result


def _body(response):
    if isinstance(response, dict) and "http_status" in response:
        if response["http_status"] != 200:
            raise ValueError("Only a successful actual response establishes presentation")
        return response["body"]
    return response


def _association(member_id, association):
    if (not isinstance(member_id, str) or not member_id
            or association.get("worker_id") != member_id
            or not isinstance(association.get("call_id"), str) or not association["call_id"]
            or type(association.get("decision_index")) is not int
            or association["decision_index"] <= 0):
        raise ValueError("Feedback lifecycle requires original runner/member/call/decision binding")


class OrdinaryFeedbackLedger:
    def __init__(self, *, evidence_kind="actual_generation_settled"):
        if evidence_kind not in {"actual_generation_settled", "cpu_programmed_fixture"}:
            raise ValueError("Unknown feedback lifecycle evidence kind")
        self.evidence_kind = evidence_kind
        self.records = {}
        self.generations = {}
        self.unsafe_calls = set()
        self.transitions = []

    def snapshot(self):
        return copy.deepcopy({"version": VERSION, "evidence_kind": self.evidence_kind, "records": list(self.records.values()),
            "generations": [{key: value for key, value in item.items() if key != "response"}
                            for item in self.generations.values()], "transitions": self.transitions,
            "unsafe_calls": sorted(self.unsafe_calls)})

    def register_rejection(self, member_id, association, feedback, response, *,
                           source_event_id=None, ordinary=True):
        _association(member_id, association)
        body = _body(response)
        call = association["call_id"]
        if (not isinstance(body, dict) or not body.get("id")
                or feedback.get("model_call_id") != call
                or feedback.get("original_response_id") != body["id"]
                or feedback.get("original_response_sha256") != digest(json_bytes(body))):
            raise ValueError("Runner feedback and original response identity/hash differ")
        identity = member_id + ":" + call
        if identity in self.records:
            raise ValueError("Runner feedback was registered twice")
        diagnostics = feedback.get("parse_diagnostics", {})
        trusted = (ordinary is True and bool(source_event_id) and call not in self.unsafe_calls
            and feedback.get("version") == "public-format-feedback-v0.33"
            and feedback.get("status") == "decision_rejected"
            and feedback.get("world_action_executed") is False
            and feedback.get("decision_consumed") is True
            and isinstance(feedback.get("reason"), str)
            and all(isinstance(diagnostics.get(name), dict) and "status" in diagnostics[name]
                    and (diagnostics[name].get("failure") is None
                         or isinstance(diagnostics[name]["failure"], dict))
                    for name in ("native_parser", "adapter_parser")))
        original = feedback_message(feedback)
        visible = feedback_message(compact_feedback(feedback)) if trusted else copy.deepcopy(original)
        record = {"feedback_id": identity, "runner_source": "model_format_feedback",
            "source_event_id": source_event_id, "member_id": member_id,
            "call_id": call, "decision_index": association["decision_index"],
            "association": copy.deepcopy(association), "original_response_id": body["id"],
            "original_response_sha256": digest(json_bytes(body)),
            "original_feedback_sha256": digest(json_bytes(feedback)),
            "original_message": original, "original_content_sha256": digest(original["content"].encode()),
            "visible_message": visible, "visible_content_sha256": digest(visible["content"].encode()),
            "ordinary": trusted, "state": ACTIVE if trusted else "retained_nonordinary_or_uncertain",
            "presentations": [], "transitions": []}
        if trusted:
            self._transition_presented(member_id, association, "superseded",
                {"new_feedback_id": identity, "source_event_id": source_event_id,
                 "business_problem_resolved": False, "syntax_repaired": False})
        self.records[identity] = record
        return copy.deepcopy(record)

    def record_presentation(self, member_id, association, selected_request, response, *,
                            accounting, team_accounting, selected_input_ids_sha256,
                            selected_request_ref=None, response_ref=None, source_event_id=None):
        _association(member_id, association)
        body = _body(response)
        trace = body.get("token_trace", {})
        usage = body.get("usage", {})
        input_ids, output_ids = trace.get("input_ids"), trace.get("output_ids")
        if (not body.get("id") or body.get("generation_started") is False
                or not isinstance(input_ids, list) or not input_ids
                or not isinstance(output_ids, list) or not output_ids
                or digest(json_bytes(input_ids)) != selected_input_ids_sha256
                or usage.get("prompt_tokens") != len(input_ids)
                or usage.get("total_tokens") != usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                or accounting.get("usage_status") != "reported"
                or accounting.get("reported_usage") != usage
                or team_accounting.get("usage_status") != "reported_actual_trace"
                or team_accounting.get("charged_tokens") != usage.get("total_tokens")
                or team_accounting.get("response_body_sha256") != digest(json_bytes(body))
                or team_accounting.get("response_id") != body["id"]):
            raise ValueError("Presentation needs actual selected native input, generated output and settled usage")
        call = association["call_id"]
        key = member_id + ":" + call
        if key in self.generations:
            raise ValueError("Actual generation was registered twice")
        receipt = {"member_id": member_id, "call_id": call,
            "decision_index": association["decision_index"], "source_event_id": source_event_id,
            "selected_request_sha256": digest(json_bytes(selected_request)),
            "selected_request_ref": copy.deepcopy(selected_request_ref),
            "response_ref": copy.deepcopy(response_ref), "response_id": body["id"],
            "response_body_sha256": digest(json_bytes(body)),
            "input_ids_sha256": selected_input_ids_sha256,
            "output_ids_sha256": digest(json_bytes(output_ids)),
            "accounting": copy.deepcopy(accounting), "team_accounting": copy.deepcopy(team_accounting),
            "generation_started": self.evidence_kind == "actual_generation_settled",
            "programmed_response_observed": self.evidence_kind == "cpu_programmed_fixture",
            "evidence_kind": self.evidence_kind}
        self.generations[key] = {**copy.deepcopy(receipt), "response": copy.deepcopy(body)}
        presented = []
        for record in self.records.values():
            if record["member_id"] != member_id or record["decision_index"] >= association["decision_index"]:
                continue
            matches = [i for i, message in enumerate(selected_request["messages"])
                       if message in (record["original_message"], record["visible_message"])]
            if len(matches) != 1:
                continue  # ambiguous identical text is not an origin witness
            item = {**copy.deepcopy(receipt), "message_index": matches[0],
                "presented_content_sha256": digest(selected_request["messages"][matches[0]]["content"].encode())}
            record["presentations"].append(item)
            presented.append({"feedback_id": record["feedback_id"], **item})
        return presented

    def _transition_presented(self, member_id, association, state, evidence):
        changed = []
        for record in self.records.values():
            # Require visibility in THIS deciding generation, not send_message,
            # CPU preparation or a feedback-looking arbitrary user message.
            witnesses = [p for p in record["presentations"] if p["call_id"] == association["call_id"]]
            if (record["ordinary"] and record["member_id"] == member_id and record["state"] == ACTIVE
                    and record["decision_index"] < association["decision_index"] and witnesses):
                transition = {"feedback_id": record["feedback_id"], "from": ACTIVE, "to": state,
                    "by_call_id": association["call_id"], "decision_index": association["decision_index"],
                    "presentation": copy.deepcopy(witnesses[-1]), **copy.deepcopy(evidence)}
                record["state"] = state
                record["transitions"].append(transition)
                self.transitions.append(transition)
                changed.append(copy.deepcopy(transition))
        return changed

    def record_legal_call(self, member_id, association, *, response, source_event_id=None,
                          proposed_action=None, model_tool_call_id=None):
        _association(member_id, association)
        body = _body(response)
        generated = self.generations.get(member_id + ":" + association["call_id"])
        message = body.get("choices", [{}])[0].get("message", {})
        calls = message.get("tool_calls") or []
        if (generated is None or generated["response_body_sha256"] != digest(json_bytes(body))
                or body.get("protocol_parse_error") or message.get("role") != "assistant"
                or len(calls) != 1 or calls[0].get("id") != model_tool_call_id
                or proposed_action is None
                or calls[0].get("function", {}).get("name") != proposed_action.get("action")
                or json.loads(calls[0]["function"]["arguments"]) != proposed_action.get("arguments")):
            raise ValueError("Legal recovery needs the actual runner native/public-schema proposed-action event")
        return self._transition_presented(member_id, association, "historicalized_after_legal_native_schema",
            {"source_event_id": source_event_id, "model_tool_call_id": model_tool_call_id,
             "native_and_public_schema_valid": True, "business_problem_resolved": False,
             "world_business_result": "not_used_for_syntax_lifecycle"})

    def observe_event(self, kind, payload, *, source_event_id=None, selected_request=None,
                      selected_input_ids_sha256=None, selected_request_ref=None, response_ref=None):
        """Replay the same trusted runner events used by the live worker hook.

        Completed attempt events require their independently bound saved selected
        request and native input hash. No CPU projection itself creates a receipt.
        """
        source_event_id = source_event_id or event_identity(kind, payload)
        if kind in {"process_violation", "execution_integrity_error", "permission_violation"}:
            if payload.get("call_id"):
                self.unsafe_calls.add(payload["call_id"])
            return []
        member = payload.get("worker_id")
        if kind == "model_attempt" and payload.get("stage") == "finished" and payload.get("status") == "success":
            return self.record_presentation(member, payload, selected_request, payload["response"],
                accounting=payload["accounting"], team_accounting=payload["team_accounting"],
                selected_input_ids_sha256=selected_input_ids_sha256,
                selected_request_ref=selected_request_ref, response_ref=response_ref, source_event_id=source_event_id)
        if kind == "model_format_feedback":
            generated = self.generations.get(str(member) + ":" + str(payload.get("call_id")))
            if generated is None:
                return []  # source/settlement unclear: unregistered text remains untouched
            return self.register_rejection(member, payload, payload["feedback"], generated["response"],
                source_event_id=source_event_id, ordinary=payload["call_id"] not in self.unsafe_calls)
        if kind == "model_call" and payload.get("stage") == "finished" and payload.get("status") == "proposed_action":
            generated = self.generations.get(str(member) + ":" + str(payload.get("call_id")))
            if generated is None:
                return []
            return self.record_legal_call(member, payload, response=generated["response"],
                source_event_id=source_event_id, proposed_action=payload["proposed_action"],
                model_tool_call_id=payload["model_tool_call_id"])
        return []


def project_format_feedback(request, *, ledger=None, member_id=None):
    state = ledger.snapshot() if isinstance(ledger, OrdinaryFeedbackLedger) else copy.deepcopy(ledger)
    records = state.get("records", []) if isinstance(state, dict) and state.get("version") == VERSION else []
    selected = copy.deepcopy(request)
    removed, changed, retained = [], [], []
    claimed = set()
    for record in records:
        if record["member_id"] != member_id:
            continue
        matches = [i for i, message in enumerate(request["messages"]) if message == record["original_message"]]
        if len(matches) != 1:
            if matches:
                retained.append({"indices": matches, "feedback_id": record["feedback_id"], "reason": "ambiguous_exact_origin"})
            continue
        index = matches[0]
        if index in claimed:
            raise ValueError("Two registered feedback origins claim the same message")
        claimed.add(index)
        evidence = {"index": index, "feedback_id": record["feedback_id"], "member_id": member_id,
            "source_call_id": record["call_id"], "source_event_id": record["source_event_id"],
            "original_response_id": record["original_response_id"],
            "original_response_sha256": record["original_response_sha256"],
            "original_content_sha256": record["original_content_sha256"],
            "visible_content_sha256": record["visible_content_sha256"], "state": record["state"],
            "presentations": copy.deepcopy(record["presentations"]), "transitions": copy.deepcopy(record["transitions"])}
        if not record["ordinary"]:
            retained.append({**evidence, "reason": "nonordinary_or_uncertain"})
        elif record["state"] in HISTORICAL:
            if not record["presentations"] or not record["transitions"]:
                raise ValueError("Historical feedback lacks actual presentation and transition evidence")
            removed.append(evidence)
        else:
            selected["messages"][index] = copy.deepcopy(record["visible_message"])
            changed.append(evidence)
    removed_indices = {item["index"] for item in removed}
    kept = [i for i in range(len(request["messages"])) if i not in removed_indices]
    selected["messages"] = [selected["messages"][i] for i in kept]
    return selected, {"version": VERSION, "member_id": member_id, "selected_indices": kept,
        "removed_indices": sorted(removed_indices), "removed_feedback": removed,
        "compacted_feedback": changed, "conservatively_retained_feedback": retained,
        "original_request_sha256": digest(json_bytes(request)),
        "projected_request_sha256": digest(json_bytes(selected)),
        "scope": "New Gamma: registered ordinary errors only. Actual presentation precedes replacement/history. No business recovery, retry, action correction or schema/page/initial-information change."}


@cache
def worker_type():
    from .harness_policy_v040 import worker_type as prior_worker_type

    class OrganizationHarnessWorker(prior_worker_type()):
        def _complete(self, messages, tools):
            self.transport.bind_turn(self.role_id, self._association)
            try:
                return super()._complete(messages, tools)
            finally:
                self.transport.unbind_turn(self.role_id, self._association)

        def _emit(self, kind, payload):
            super()._emit(kind, payload)
            ledger = getattr(self.transport, "feedback_ledger", None)
            if ledger is None:
                return
            binding = {}
            if kind == "model_attempt" and payload.get("stage") == "finished" and payload.get("status") == "success":
                binding = self.transport.generation_binding(payload["call_id"], payload["response"])
            transition = ledger.observe_event(kind, payload,
                source_event_id=event_identity(kind, payload), **binding)
            if transition:
                super()._emit("format_feedback_lifecycle_v044", {"worker_id": self.role_id,
                    "call_id": payload.get("call_id"), "trigger": kind, "evidence": transition})

    return OrganizationHarnessWorker


def __getattr__(name):
    if name == "OrganizationHarnessWorker":
        return worker_type()
    raise AttributeError(name)
