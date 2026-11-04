"""Lossless same-input compaction of registered PROJECT observation history.

The latest observation stays literal and complete. Only declared older static
fields equal to that same authorized input are represented by explicit pointers.
SDK events, tool results, failures, source versions, and summary sources remain
unchanged. Both SDK counting and actual dispatch use this exact projection.
"""
from __future__ import annotations

import copy
from functools import cache
import json
import re

from . import software_benchmark_history_v110 as previous
from .software_benchmark_history_budget_v110 import AlignedManagedTeamBudget, ManagedSummaryAdapter, SummaryTrace
from .software_benchmark_budget_closure_v103 import affordable_output_cap, PREPARATION_VERSION, VERSION as OUTPUT_POLICY_VERSION
from .software_benchmark_managed_v064 import CONTEXT_LIMIT, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS, ATTEMPT_LIMIT
from .software_context_v041 import MEMBER_SCOPE_FIELDS, _member_identity
from .software_context_v048 import _protected_request
from .software_feedback_v044 import project_format_feedback
from .storage import digest, json_bytes

VERSION = "v117-lossless-registered-observation-history-r1"
REFERENCE_KEY = "_v117_same_input_static_fields"
REFERENCE_MEANING = (
    "Only the listed historical static fields are omitted. Their exact values are in the "
    "latest complete authorized observation at anchor_message_index in this same input. "
    "All remaining fields describe this historical observation, not a new state or evidence."
)
STATIC_PATHS = (
    "/role_task", "/observation/contract", "/observation/root_goal",
    "/observation/file_directory", "/observation/file_count", "/observation/editable_paths",
    "/observation/editable_paths_scope", "/observation/source_readonly_policy",
    "/observation/action_error_policy", "/observation/scheduling", "/observation/shared_resource_limits",
    "/observation/execution_condition", "/observation/aligned_resource_allowances",
    "/observation/public_test_selection", "/observation/tool_navigation", "/observation/purpose",
)
ROOT_HASH_FIELDS = ("source_contract_sha256", "initial_binding_sha256", "file_policy_sha256")
_MISSING = object()


def _loads(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Ambiguous duplicate observation JSON key")
            value[key] = item
        return value
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    json_bytes(value)
    return value


def _get(value, pointer):
    for key in pointer.split("/")[1:]:
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def _parent(value, pointer):
    parts = pointer.split("/")[1:]
    for key in parts[:-1]:
        value = value[key]
    return value, parts[-1]


def _contains_marker(value):
    if isinstance(value, dict):
        return REFERENCE_KEY in value or any(_contains_marker(item) for item in value.values())
    return isinstance(value, list) and any(_contains_marker(item) for item in value)


def _scope(payload, member_id):
    observation = payload.get("observation")
    if not isinstance(observation, dict):
        return None
    identity = _member_identity(observation)
    if identity is None or identity["actor_id"] != member_id:
        return None
    if (not isinstance(payload.get("role_task"), str) or not payload["role_task"]
            or not isinstance(observation.get("contract"), (str, dict)) or not observation["contract"]
            or not isinstance(observation.get("root_goal"), dict)):
        return None
    hashes = {name: observation.get(name) for name in ROOT_HASH_FIELDS}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        return None
    return {"member": identity, "root_hashes": hashes,
            "role_task_sha256": digest(payload["role_task"].encode()),
            "contract_sha256": digest(json_bytes(observation["contract"]))}


def _marker(index, anchor_hash, original_hash, fields):
    return {"version": VERSION, "anchor_message_index": index, "anchor_content_sha256": anchor_hash,
            "original_content_sha256": original_hash, "omitted_equal_paths": list(fields), "meaning": REFERENCE_MEANING}


def project_observation_history(request, *, member_id, registered_observations):
    """A reversible presentation transform; never delete a message or tool round."""
    registered = tuple(registered_observations)
    if not isinstance(member_id, str) or not member_id or any(not isinstance(value, str) for value in registered):
        raise ValueError("Bind the real member and its registered original observations")
    trusted = set(registered)
    selected = copy.deepcopy(request)
    observations = []
    for index, message in enumerate(request["messages"]):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str) or content not in trusted:
            continue
        payload = _loads(content)
        if isinstance(payload, dict) and isinstance(payload.get("observation"), dict):
            observations.append((index, payload))
    evidence = {"version": VERSION, "member_id": member_id, "static_allowlist": list(STATIC_PATHS),
                "registered_observation_indices": [i for i, _ in observations], "rewritten_observations": [],
                "original_request_sha256": digest(json_bytes(request)), "removed_messages": [],
                "latest_full_observation_preserved": True, "tool_results_and_nonobservations_unchanged": True,
                "source_and_budget_events_mutated": False, "summary_sources_mutated": False}
    if observations:
        anchor_index, anchor = observations[-1]
        anchor_content = request["messages"][anchor_index]["content"]
        anchor_hash, scope = digest(anchor_content.encode()), _scope(anchor, member_id)
        evidence.update(anchor_message_index=anchor_index, anchor_content_sha256=anchor_hash,
                        member_scope_fields=list(MEMBER_SCOPE_FIELDS))
        for index, original in observations[:-1]:
            if scope is None or _scope(original, member_id) != scope or _contains_marker(original) or _contains_marker(anchor):
                continue
            payload, removed = copy.deepcopy(original), []
            for pointer in STATIC_PATHS:
                old, current = _get(original, pointer), _get(anchor, pointer)
                if old is _MISSING or current is _MISSING or json_bytes(old) != json_bytes(current):
                    continue
                parent, key = _parent(payload, pointer)
                del parent[key]
                removed.append(pointer)
            if not removed:
                continue
            original_text = request["messages"][index]["content"]
            payload[REFERENCE_KEY] = _marker(anchor_index, anchor_hash, digest(original_text.encode()), removed)
            text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            if len(text.encode()) >= len(original_text.encode()):
                continue  # No reason to enlarge small synthetic/historical inputs.
            selected["messages"][index]["content"] = text
            evidence["rewritten_observations"].append({"message_index": index, "omitted_equal_paths": removed,
                "original_content_sha256": digest(original_text.encode()), "selected_content_sha256": digest(text.encode()),
                "original_bytes": len(original_text.encode()), "selected_bytes": len(text.encode()), "scope": scope})
    evidence["selected_request_sha256"] = digest(json_bytes(selected))
    evidence["validation"] = validate_projection(request, selected, evidence)
    return selected, evidence


def validate_projection(original, selected, evidence):
    """Rehydrate from the literal anchor and compare every original request byte."""
    if (evidence.get("version") != VERSION or evidence.get("static_allowlist") != list(STATIC_PATHS)
            or evidence.get("original_request_sha256") != digest(json_bytes(original))
            or evidence.get("selected_request_sha256") != digest(json_bytes(selected))):
        raise ValueError("Observation projection has no exact original/selected binding")
    restored = copy.deepcopy(selected)
    seen = set()
    for row in evidence["rewritten_observations"]:
        index, anchor_index = row["message_index"], evidence["anchor_message_index"]
        if index in seen or type(index) is not int or type(anchor_index) is not int or not 0 <= index < anchor_index < len(original["messages"]):
            raise ValueError("Invalid or duplicate same-input observation reference")
        seen.add(index)
        if selected["messages"][anchor_index] != original["messages"][anchor_index]:
            raise ValueError("The current complete observation was altered")
        anchor_text = selected["messages"][anchor_index]["content"]
        if digest(anchor_text.encode()) != evidence["anchor_content_sha256"]:
            raise ValueError("The retained current observation is not the referenced anchor")
        source_text = original["messages"][index]["content"]
        source, payload, anchor = _loads(source_text), _loads(selected["messages"][index]["content"]), _loads(anchor_text)
        fields = row["omitted_equal_paths"]
        if (not fields or len(fields) != len(set(fields)) or any(path not in STATIC_PATHS for path in fields)
                or _scope(source, evidence["member_id"]) != row["scope"] or _scope(anchor, evidence["member_id"]) != row["scope"]
                or digest(source_text.encode()) != row["original_content_sha256"]
                or digest(selected["messages"][index]["content"].encode()) != row["selected_content_sha256"]
                or payload.pop(REFERENCE_KEY, None) != _marker(anchor_index, evidence["anchor_content_sha256"], row["original_content_sha256"], fields)):
            raise ValueError("Same-input static reference lost its provenance or member/root scope")
        for pointer in fields:
            target = _get(anchor, pointer)
            if target is _MISSING or _get(payload, pointer) is not _MISSING or json_bytes(_get(source, pointer)) != json_bytes(target):
                raise ValueError("A removed field is not exactly recoverable from this input")
            parent, key = _parent(payload, pointer)
            parent[key] = copy.deepcopy(target)
        # Restoring removed dictionary keys changes insertion order. Compare
        # strict JSON values (including bool vs int), then restore the original
        # literal content only after the entire structure is proven equal.
        canonical = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        if canonical(payload) != canonical(source):
            raise ValueError("Projection changed another observation field")
        restored["messages"][index]["content"] = source_text
    if json_bytes(restored) != json_bytes(original):
        raise ValueError("Observation projection changed a message, failure, tool result, or request setting")
    return {"passed": True, "lossless_same_input_reconstruction": True,
            "restored_request_sha256": digest(json_bytes(restored)), "rewritten_observations": len(seen)}


def _select(request, ledger, member_id, observations):
    formatted, feedback = project_format_feedback(request, ledger=ledger, member_id=member_id)
    selected, history = project_observation_history(formatted, member_id=member_id, registered_observations=observations)
    return selected, feedback, history


@cache
def managed_counting_llm_type():
    from .harness_sdk import ResidentBridgeLLM
    from .software_benchmark_deepseek_prefix_v055_r2 import pending_tail_tool_ids

    class ManagedCountingLLM(ResidentBridgeLLM):
        def get_token_count(self, messages, tools=None, **kwargs):
            worker = self._worker
            worker._history_trace_v110.assert_healthy()
            if not messages:
                return 0
            if set(kwargs) - {"add_security_risk_prediction", "on_token", "call_context"}:
                raise ValueError("Unexpected PROJECT token count parameters")
            adapter = worker.transport.owner.adapter
            definitions = [{"type": "function", "function": row} for row in worker.definitions] if tools else []
            request = adapter.request(previous._project_messages(messages, worker), definitions)
            pending = pending_tail_tool_ids(request["messages"])
            selected, _, _ = worker.transport.select_for_member(request, worker.role_id)
            counted = adapter.request(selected["messages"], selected.get("tools"))
            return (adapter.count_prefix(counted, pending) if pending else adapter.count(counted))["prompt_tokens"]

    return ManagedCountingLLM


class SummarizingManagedContextTransport(previous.SummarizingManagedContextTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._observation_sources_v117 = {}

    def bind_observation_source(self, worker):
        member = worker.role_id
        if (member in self._observation_sources_v117 or worker.transport is not self
                or worker.meter["decisions"] != 0 or worker._in_step):
            raise ValueError("Bind one fresh real worker observation source per member")
        self._observation_sources_v117[member] = worker

    def select_for_member(self, request, member):
        worker = self._observation_sources_v117.get(member)
        if worker is None or worker.transport is not self or worker.role_id != member:
            raise ValueError("Observation compaction lacks its exact original worker source")
        return _select(request, self.feedback_ledger, member, worker._observation_texts)

    def prepare_for_budget(self, request):
        if self._turn is None or self._prepared is not None:
            raise ValueError("Only an unused bound turn may prepare")
        member = self._turn["member_id"]
        selected, feedback, history = self.select_for_member(request, member)
        _, protected = _protected_request(selected)
        adapter = self.owner.adapter
        wire = adapter.request(selected["messages"], selected.get("tools"))
        measured = adapter.count(wire)
        prompt = measured["prompt_tokens"]
        meter, team, local_limit = self._budget_sources_v103[member]
        state = team.snapshot()
        values = {"local_available_tokens": local_limit-meter["budget_accounted_tokens"],
                  "team_available_tokens": state["available_tokens"],
                  "adapter_available_tokens": adapter.ledger.token_budget-adapter.ledger.actual}
        if state.get("integrity_failure") or adapter.ledger.inflight is not None or min(values.values()) < 0:
            raise ValueError("Unresolved accounting cannot prepare another agent request")
        available = min(values.values())
        cap = affordable_output_cap(prompt, available)
        if cap != MAX_OUTPUT_TOKENS:
            wire["max_tokens"] = cap
            measured = adapter.count(wire)
            if measured["prompt_tokens"] != prompt:
                raise ValueError("Output cap changed the counted input")
        fits = prompt <= MAX_INPUT_TOKENS and prompt+cap <= CONTEXT_LIMIT
        adjustment = {"version": OUTPUT_POLICY_VERSION, **values, "available_tokens": available,
            "team_state_sha256": state["state_sha256"], "maximum_output_tokens": MAX_OUTPUT_TOKENS,
            "actual_output_cap": cap, "reduced": cap != MAX_OUTPUT_TOKENS,
            "input_and_history_unchanged": True, "automatic_submission": False,
            "no_positive_output_room": available <= prompt}
        projection = {"version": VERSION, "fits": fits, "count_method": measured["method"], "measurement": measured,
            "selected_prompt_token_reservation": prompt, "reserved_output_tokens": cap,
            "context_limit": CONTEXT_LIMIT, "maximum_input_tokens": MAX_INPUT_TOKENS,
            "sdk_context_selection": "full_history_with_lossless_static_references",
            "format_feedback_projection": feedback, "observation_history_projection": history,
            "selected_indices": list(feedback["selected_indices"]), "removed_indices": [],
            "capacity_history_dropped": False, "original_request_sha256": digest(json_bytes(request)),
            "selected_request_sha256": digest(json_bytes(selected)), "wire_request_sha256": digest(json_bytes(wire)),
            "latest_complete_round_preserved": protected["latest_complete_round_preserved"],
            "output_budget_adjustment": adjustment}
        measure = {"version": PREPARATION_VERSION, "original_request_sha256": digest(json_bytes(request)),
            "selected_request_sha256": digest(json_bytes(selected)), "wire_request_sha256": digest(json_bytes(wire)),
            "prompt_tokens": prompt, "reserved_output_tokens": cap, "context_limit": CONTEXT_LIMIT, "fits": fits,
            "count_method": measured["method"], "window_id": self.owner.window_id,
            "actor_identity": self.owner.freeze_identity(), "output_budget_adjustment": adjustment,
            "history_policy": VERSION, "observation_projection_lossless": True}
        measure["preparation_sha256"] = digest(json_bytes(measure))
        self._prepared = {"original": copy.deepcopy(request), "selected": selected, "wire": wire,
                          "projection": projection, "measurement": copy.deepcopy(measure), "turn": copy.deepcopy(self._turn)}
        return measure


class HistoryWorkerMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (not isinstance(self.team_budget, AlignedManagedTeamBudget)
                or not isinstance(self.transport, SummarizingManagedContextTransport)
                or self.meter["decisions"] != 0 or self._in_step):
            raise ValueError("v117 history needs the fresh same-pool managed runtime")
        self.transport.bind_observation_source(self)
        self._history_trace_v110 = SummaryTrace(directory=self.directory/"history-summaries", owner_id=self.role_id, event_sink=self._emit)
        self._history_trace_v110.bind_conversation(self.conversation)
        from .software_benchmark_deepseek_adapter_v105 import build_native_llm
        summary_adapter = ManagedSummaryAdapter(self, self.transport.owner.adapter, self._history_trace_v110)
        summary_llm = build_native_llm(summary_adapter, normalization_folder=self.directory/"summary-response-projections")
        summary_llm.usage_id = "condenser"
        counting = managed_counting_llm_type()(model="openai/"+self.config["model"], usage_id="agent",
            num_retries=0, stream=False, caching_prompt=False, max_input_tokens=MAX_INPUT_TOKENS,
            max_output_tokens=MAX_OUTPUT_TOKENS, temperature=self.config["temperature"])
        counting._worker = self
        condenser = previous.build_condenser(summary_llm, trace=self._history_trace_v110)
        conversation = self.conversation
        with conversation.state:
            agent = conversation.agent.model_copy(update={"llm": counting, "condenser": condenser})
            conversation.agent = agent
            conversation.state.agent = agent
            self.agent, self.llm = agent, counting
            for llm in (counting, condenser.llm):
                if llm.usage_id in conversation.llm_registry.list_usage_ids():
                    raise ValueError("Managed model-use identity was already registered")
                conversation.llm_registry.add(llm)
                conversation._bind_conversation_context(llm)
            conversation.max_iteration_per_run = ATTEMPT_LIMIT
        self._history_policy_v117 = {"version": VERSION, "condenser": dict(previous.CONDENSER_PARAMETERS),
            "same_model_pool": True, "summary_adds_agent_decision": False,
            "one_agent_action_per_opportunity": True, "SDK_iteration_limit": ATTEMPT_LIMIT,
            "silent_capacity_history_drop": False, "latest_complete_observation_literal": True,
            "SDK_count_and_actual_dispatch_share_projection": True, "original_summary_sources_retained": True}

    def _complete(self, messages, tools):
        self._history_trace_v110.assert_healthy()
        try:
            return super()._complete(messages, tools)
        finally:
            body = self._last_body
            if (isinstance(body, dict) and body.get("id") and isinstance(body.get("usage"), dict)
                    and self.transport.owner.adapter.ledger.inflight is None):
                self._history_trace_v110.mark_presented(body)

    def snapshot(self):
        value = super().snapshot()
        if hasattr(self, "_history_policy_v117"):
            value["history_policy_v117"] = copy.deepcopy(self._history_policy_v117)
        return value


@cache
def history_worker_type():
    from .software_benchmark_managed_v105 import worker_type

    class CompactManagedHistoryWorker(HistoryWorkerMixin, worker_type()):
        pass

    return CompactManagedHistoryWorker
