"""Remote-usage seam for the genuine S1 World and OpenHands managed worker.

Gamma1 information transformations and single-action delivery semantics are
retained. Provider usage replaces unavailable local token traces explicitly.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_interfaces_v055 import (
    MODEL, VERSION, RemoteEpisodeBoundary,
)
from .software_feedback_v044 import OrdinaryFeedbackLedger, _association, _body
from .software_context_v048 import _prepare, _protected_request, validate_reference_projection
from .software_calibration_collector_v051 import SingleMemberBudget
from .storage import atomic_write, digest, json_bytes


class RemoteTeamBudget(SingleMemberBudget):
    def cancel_provider_before_dispatch(self, member, call_id, reason):
        """Only the adapter's proven pre-HTTP boundary may release this hold."""
        with self._lock:
            row = self._record(member, call_id)
            if row["status"] != "attempting" or "charge" in row:
                raise ValueError("Only the unsettled adapter-bound attempt may be cancelled")
            row.update(status="cancelled_before_attempt", attempt_started=False,
                       dispatch_started=False, framework_transport_entered=True,
                       provider_dispatch_started=False, provider_cancellation_reason=reason)

    def settle(self, member, call_id, body=None):
        charge = super().settle(member, call_id, body)
        if charge["usage_status"] == "reported_actual_trace":
            charge["usage_status"] = "reported_api_usage"
            self._state["records"][call_id]["charge"] = copy.deepcopy(charge)
        return charge


class RemoteFeedbackLedger(OrdinaryFeedbackLedger):
    """Actual API response + exact sent request, never synthetic token traces."""
    def __init__(self):
        super().__init__()
        self.evidence_kind = "settled_official_api_usage_v055"

    def record_presentation(self, member_id, association, selected_request, response, *,
                            accounting, team_accounting, selected_input_ids_sha256=None,
                            selected_request_ref=None, response_ref=None, source_event_id=None):
        _association(member_id, association)
        body = _body(response)
        usage = body.get("usage", {})
        if (not body.get("id") or body.get("generation_started") is False
                or selected_input_ids_sha256 is not None
                or accounting.get("usage_status") != "reported"
                or accounting.get("reported_usage") != usage
                or team_accounting.get("usage_status") != "reported_api_usage"
                or team_accounting.get("charged_tokens") != usage.get("total_tokens")
                or team_accounting.get("response_body_sha256") != digest(json_bytes(body))
                or team_accounting.get("response_id") != body["id"]
                or usage.get("total_tokens") != usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                or selected_request_ref is None or response_ref is None):
            raise ValueError("Remote feedback requires settled API usage and exact request/response provenance")
        key = member_id + ":" + association["call_id"]
        if key in self.generations:
            raise ValueError("One actual generation cannot establish presentation twice")
        receipt = {"member_id": member_id, "call_id": association["call_id"],
            "decision_index": association["decision_index"], "source_event_id": source_event_id,
            "selected_request_sha256": digest(json_bytes(selected_request)),
            "selected_request_ref": copy.deepcopy(selected_request_ref),
            "response_ref": copy.deepcopy(response_ref), "response_id": body["id"],
            "response_body_sha256": digest(json_bytes(body)),
            "input_ids_sha256": None, "output_ids_sha256": None,
            "accounting": copy.deepcopy(accounting), "team_accounting": copy.deepcopy(team_accounting),
            "generation_started": True, "evidence_kind": "settled_official_api_usage_v055",
            "provider_token_ids_available": False}
        self.generations[key] = {**copy.deepcopy(receipt), "response": copy.deepcopy(body)}
        presented = []
        for record in self.records.values():
            if record["member_id"] != member_id or record["decision_index"] >= association["decision_index"]:
                continue
            matches = [i for i, message in enumerate(selected_request["messages"])
                       if message in (record["original_message"], record["visible_message"])]
            if len(matches) != 1:
                continue
            item = {**copy.deepcopy(receipt), "message_index": matches[0],
                    "presented_content_sha256": digest(selected_request["messages"][matches[0]]["content"].encode())}
            record["presentations"].append(item)
            presented.append({"feedback_id": record["feedback_id"], **item})
        return presented


def project_request(request, *, adapter, ledger, member_id):
    """The same Gamma1 transforms and oldest complete-round capacity removal."""
    _, feedback, static, deduplication, referenced, references = _prepare(request, ledger, member_id)
    _, protected = _protected_request(referenced)
    pairs = protected["complete_tool_rounds"]
    removed, measurements = set(), []
    selected = copy.deepcopy(referenced)
    removable = iter(pairs[:-1])
    while True:
        selected["messages"] = [copy.deepcopy(message) for i, message in enumerate(referenced["messages"])
                                if i not in removed]
        wire = adapter.request(selected["messages"], selected.get("tools"))
        measured = adapter.count(wire)
        count = measured["prompt_tokens"]
        fits = count + adapter.maximum_output_tokens <= adapter.limits["context_limit"]
        measurements.append({"removed_indices": sorted(removed), "estimated_prompt_tokens": count})
        if fits:
            break
        pair = next(removable, None)
        if pair is None:
            break
        removed.update(pair)
    indices = [i for i in range(len(referenced["messages"])) if i not in removed]
    validation = validate_reference_projection(selected, static, indices, references)
    mapped = [feedback["selected_indices"][i] for i in indices]
    projection = {"version": VERSION, "fits": fits, "count_method": measured["method"],
        "measurement": measured,
        "provider_tokenizer_proof": measured.get("exact_provider_token_ids_available", False),
        "provider_input_ids_available": measured.get("exact_provider_token_ids_available", False),
        "selected_prompt_token_reservation": count, "reserved_output_tokens": adapter.maximum_output_tokens,
        "context_limit": adapter.limits["context_limit"], "measurements": measurements,
        "format_feedback_projection": feedback, "static_deduplication": deduplication,
        "same_input_references": references, "reference_validation": validation,
        "selected_indices": mapped,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in mapped],
        "original_request_sha256": digest(json_bytes(request)),
        "selected_request_sha256": digest(json_bytes(selected)),
        "wire_request_sha256": digest(json_bytes(wire)),
        "latest_complete_round_preserved": protected["latest_complete_round_preserved"]}
    return selected, wire, projection


class RemoteContextTransport:
    def __init__(self, owner, directory):
        self.owner, self.directory = owner, Path(directory)
        self.counter, self._turn, self._prepared = 0, None, None
        self.feedback_ledger = RemoteFeedbackLedger()
        self._generation_bindings = {}

    def bind_turn(self, member_id, association):
        if self._turn is not None or association.get("worker_id") != member_id:
            raise ValueError("One real S1 runner turn must bind each request")
        self._turn = {"member_id": member_id, "association": copy.deepcopy(association)}

    def unbind_turn(self, member_id, association):
        if self._turn != {"member_id": member_id, "association": association}:
            raise ValueError("Remote runner turn changed inside one request")
        self._turn = None

    def prepare_for_budget(self, request):
        if self._turn is None or self._prepared is not None:
            raise ValueError("Only an unused bound runner turn may prepare")
        selected, wire, projection = project_request(request, adapter=self.owner.adapter,
            ledger=self.feedback_ledger, member_id=self._turn["member_id"])
        measure = {"version": "v055-remote-budget-preparation-r1",
            "original_request_sha256": digest(json_bytes(request)),
            "selected_request_sha256": digest(json_bytes(selected)),
            "wire_request_sha256": digest(json_bytes(wire)),
            "prompt_tokens": projection["selected_prompt_token_reservation"],
            "reserved_output_tokens": projection["reserved_output_tokens"],
            "context_limit": projection["context_limit"], "fits": projection["fits"],
            "count_method": projection["count_method"], "window_id": self.owner.window_id,
            "actor_identity": self.owner.freeze_identity()}
        measure["preparation_sha256"] = digest(json_bytes(measure))
        self._prepared = {"original": copy.deepcopy(request), "selected": selected,
                          "wire": wire, "projection": projection, "measurement": measure,
                          "turn": copy.deepcopy(self._turn)}
        return copy.deepcopy(measure)

    def discard_prepared_request(self, request):
        if self._prepared and self._prepared["original"] != request:
            raise ValueError("Cannot discard another prepared request")
        self._prepared = None

    def complete(self, request, **kwargs):
        pending, self._prepared = self._prepared, None
        if (pending is None or pending["turn"] != self._turn or pending["original"] != request
                or not pending["projection"]["fits"]):
            raise ValueError("Only the admitted exact remote request may dispatch")
        self.counter += 1
        folder = self.directory / f"request-{self.counter:05d}"
        folder.mkdir(parents=True, exist_ok=False)
        for name, value in (("original-request", request), ("selected-request", pending["selected"]),
                            ("wire-request", pending["wire"]), ("projection", pending["projection"]),
                            ("budget-preparation", pending["measurement"]), ("runner-turn", self._turn)):
            atomic_write(folder / (name + ".json"), json_bytes(value))
        response = self.owner.transport.complete(pending["wire"], **kwargs)
        atomic_write(folder / "response.json", json_bytes(response))
        self._generation_bindings[self._turn["association"]["call_id"]] = {
            "selected_request": copy.deepcopy(pending["selected"]),
            "selected_input_ids_sha256": None,
            "selected_request_ref": reference(folder / "selected-request.json"),
            "response_ref": reference(folder / "response.json"),
            "response_body_sha256": digest(json_bytes(response["body"]))}
        return response

    def generation_binding(self, call_id, response):
        binding = self._generation_bindings.pop(call_id, None)
        if binding is None or binding.pop("response_body_sha256") != digest(json_bytes(response["body"])):
            raise ValueError("Settled remote generation lacks its exact response binding")
        return binding


class RemoteProjectOwner:
    def __init__(self, adapter, *, window_id):
        self.adapter, self.window_id = adapter, window_id
        self.recipe = {"max_length": 18432, "max_output_tokens": 2048, "temperature": 0.7}
        self.transport = self

    def freeze_identity(self):
        return {"policy_version": VERSION, "provider": "official_direct_deepseek",
                "model": MODEL, "thinking": self.adapter.thinking,
                "provider_weight_revision_pinnable": False, "trained_adapter_loaded": False}

    def complete(self, request, *, timeout_seconds):
        if timeout_seconds != 600:
            raise ValueError("Retain the managed request timeout")
        body = self.adapter.complete(request, "agent")
        return {"http_status": 200, "body": body, "raw_body": json_bytes(body).decode(),
                "response_headers": {}, "response_redactions": []}


def remote_worker_type():
    from .software_calibration_collector_v051 import worker_type
    from .model_policy import ModelPolicy
    from .team_budget_v033 import V033PolicyBoundaryError

    class RemoteAccountant(ModelPolicy):
        def _reserve(self, request, *, prepared=None, actor_identity=None):
            if prepared is None:
                raise ValueError("Managed remote requests require a bound Gamma1 preparation")
            unsealed = {k: v for k, v in prepared.items() if k != "preparation_sha256"}
            if (prepared["version"] != "v055-remote-budget-preparation-r1"
                    or prepared["preparation_sha256"] != digest(json_bytes(unsealed))
                    or prepared["original_request_sha256"] != digest(json_bytes(request))):
                raise ValueError("Remote preparation identity changed")
            if not prepared["fits"]:
                raise V033PolicyBoundaryError("model_budget_exhausted", "conservative_context_capacity",
                    memory={}, details={"limits": ["context_capacity"], "budget_kind": "context_capacity"})
            return {"request_bytes": len(json_bytes(request)),
                "input_token_reservation": prepared["prompt_tokens"],
                "output_token_reservation": prepared["reserved_output_tokens"],
                "token_reservation": prepared["prompt_tokens"] + prepared["reserved_output_tokens"],
                "cost_reservation_usd": 0, "method": prepared["count_method"],
                "reservation_kind": "remote_conservative_prompt_estimate", "preparation": prepared,
                "monetary_authority": "shared_v055_CNY_ledger_not_this_legacy_USD_meter"}

    class RemoteWorker(worker_type()):
        def __init__(self, role_id, tools, config, **kwargs):
            config = copy.deepcopy(config)
            adapter = kwargs["transport"].owner.adapter
            config.update(backend_id="deepseek_direct_v055", model=MODEL,
                base_url="https://api.deepseek.com", api_key_env="DEEPSEEK_API_KEY", model_revision=VERSION,
                thinking=adapter.thinking, reasoning_effort="high" if adapter.thinking else None)
            super().__init__(role_id, tools, config, **kwargs)
            self._accountant = RemoteAccountant(self.config, transport=self.transport)
            self._accountant.bind_event_sink(self._emit)

        def _complete(self, messages, tools):
            try:
                return super()._complete(messages, tools)
            except RemoteEpisodeBoundary as error:
                # BaseException deliberately passes the legacy transport's
                # generic Exception=>uncertain-usage handler. The remote seam
                # raises this type only before an actual provider dispatch.
                self.team_budget.cancel_provider_before_dispatch(
                    self.role_id, self._association["call_id"], str(error))
                self.meter["http_attempts"] -= 1
                self._emit("provider_pre_dispatch_cancellation_v055", {
                    **self._association, "reason": str(error),
                    "provider_dispatch_started": False, "actual_tokens": 0,
                    "reservation_released": True, "decision_consumed": True})
                self._fail("model_budget_exhausted", str(error), provider_dispatch_started=False)

    return RemoteWorker


def build_runtime(owner, prepared, folder, *, deadline):
    """Assemble the real S1 managed interface with a remote-usage budget class."""
    from . import software_calibration_collector_v051 as base
    from . import software_benchmark_world_v054 as world
    from .experience import capture_port
    from .harness_port import HarnessPort
    from .software_organization_runtime_v038 import _CollectionOwner
    from .software_organization_runtime_v047 import NativeDispatchGate

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    world.validate_case(prepared.case, provider=prepared.source_provider)
    recorder = base._StreamRecorder(folder / "experience.jsonl")
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = RemoteTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        require_exact_resident=False, **{k: prepared.case["team_limits"][k]
        for k in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    gate = NativeDispatchGate(owner.transport, deadline)
    context = RemoteContextTransport(_CollectionOwner(owner, gate), folder / "remote-transport")
    gate.context, context.native_dispatch_gate = context, gate
    facade = _CollectionOwner(owner, context)
    captured, interfaces, holder = {}, {}, {}
    worker_factory = remote_worker_type()

    def create_member(member, record):
        interface = world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
        interfaces[member] = interface
        rows = base._StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        config = base._config(facade, member, world.member_instruction(prepared.case),
                              {member: prepared.case["team_limits"]["max_decisions"]})
        config.update(context_policy="full_history", format_error_policy="format_feedback_budgeted_v033")
        port = HarnessPort(capture_port(interface, rows), member, project_id=world.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(member, payload, association))
        worker = worker_factory(member, port.tools(), config, transport=context, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=base.SDK_CONTEXT_SELECTION)
        base.specialize_control_tools(worker)
        return port, worker

    ports, workers = {}, {}
    for member in prepared.case["active_roles"]:
        ports[member], workers[member] = create_member(member, base._registry(prepared.world)[member])
    runtime = base.OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
        recorder=recorder, member_factory=create_member, deadline=deadline)
    holder["runtime"], gate.runtime = runtime, runtime
    runtime.owner = facade
    runtime.sync_members()
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    prepared.world.runtime_availability = runtime.availability
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in runtime.labels:
        recorder.record("organization_session_born", runtime.birth_records[member], worker_id=member)
    runtime.note_population("initial")
    return runtime, captured, interfaces
