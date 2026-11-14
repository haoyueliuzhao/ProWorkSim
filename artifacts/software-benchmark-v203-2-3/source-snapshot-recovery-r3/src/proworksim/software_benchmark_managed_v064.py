"""REF-aligned model resources around the real, repaired S1 managed interface.

All transport is supplied by the controller; this module has no network client,
keys, shell, Docker API or hidden evaluator. The same actor remains accountable
for one managed action per opportunity and explicit versioned delivery.
"""
from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
import time

from . import software_benchmark_world_v064 as world
from .software_benchmark_candidates_v054 import reference, write_new
from .software_feedback_v044 import OrdinaryFeedbackLedger, _association, _body
from .software_context_v048 import _prepare, _protected_request, validate_reference_projection
from .software_context_v034 import observation_messages
from .software_calibration_collector_v051 import SingleMemberBudget
from .software_benchmark_managed_worker_v056 import worker_type as managed_worker_type
from .software_benchmark_exact_transport_v057 import normalize_response
from .repository_sources_v054 import RepositorySources, tree_manifest
from .storage import atomic_write, digest, json_bytes

VERSION = "v064-ref-aligned-managed-runtime-r1"
CONTEXT_LIMIT, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS = 131072, 98304, 32768
ATTEMPT_LIMIT, REQUEST_SECONDS = 512, 1800
SOFT_SECONDS, HARD_SECONDS = 21600, 23400
MAX_RAW_CONTEXT_BYTES = 128 * 1024**2
SDK_CONTEXT_SELECTION = "full_history"


class ManagedBeforeDispatch(BaseException):
    """Trusted broker proves no new model/provider attempt was dispatched."""


class ManagedTeamBudget(SingleMemberBudget):
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
            charge["usage_status"] = "reported_model_usage"
            self._state["records"][call_id]["charge"] = copy.deepcopy(charge)
        return charge


class ManagedFeedbackLedger(OrdinaryFeedbackLedger):
    """Actual API response + exact sent request, never synthetic token traces."""
    def __init__(self):
        super().__init__()
        self.evidence_kind = "settled_model_provider_usage_v064"

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
                or team_accounting.get("usage_status") != "reported_model_usage"
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
            "generation_started": True, "evidence_kind": "settled_model_provider_usage_v064",
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
    """Keep full history until capacity requires oldest complete work removal."""
    _, feedback, static, deduplication, referenced, references = _prepare(request, ledger, member_id)
    _, protected = _protected_request(referenced)
    pairs = protected["complete_tool_rounds"]
    observations = [index for index, _ in observation_messages(referenced)]
    protected_observations = {observations[0], observations[-1]} if observations else set()
    if pairs:
        before_latest = [index for index in observations if index < pairs[-1][0]]
        if before_latest:
            protected_observations.add(before_latest[-1])
    units, covered = [], set()
    for pair in pairs[:-1]:
        unit = set(pair)
        preceding = [index for index in observations if index < pair[0]]
        if preceding and preceding[-1] not in protected_observations:
            unit.add(preceding[-1])
        units.append(unit)
        covered.update(unit)
    units.extend({index} for index in observations
                 if index not in protected_observations and index not in covered)
    removed, measurements = set(), []
    selected = copy.deepcopy(referenced)
    removable = iter(units)
    while True:
        selected["messages"] = [copy.deepcopy(message) for i, message in enumerate(referenced["messages"])
                                if i not in removed]
        wire = adapter.request(selected["messages"], selected.get("tools"))
        measured = adapter.count(wire)
        count = measured.get("prompt_tokens")
        wire_sha = digest(json_bytes(wire))
        if (type(count) is not int or count < 0
                or measured.get("request_sha256", measured.get("generation_request_sha256")) != wire_sha
                or measured.get("context_limit", CONTEXT_LIMIT) != CONTEXT_LIMIT):
            raise ValueError("Model counting must bind this exact complete wire request")
        method = measured.get("method") or measured.get("backend")
        if not isinstance(method, str) or not method:
            raise ValueError("Model counting requires an explicit method")
        fits = count <= MAX_INPUT_TOKENS and count + MAX_OUTPUT_TOKENS <= CONTEXT_LIMIT
        measurements.append({"removed_indices": sorted(removed), "prompt_tokens": count})
        if fits:
            break
        unit = next(removable, None)
        if unit is None:
            break
        removed.update(unit)
    indices = [i for i in range(len(referenced["messages"])) if i not in removed]
    validation = validate_reference_projection(selected, static, indices, references)
    mapped = [feedback["selected_indices"][i] for i in indices]
    projection = {"version": VERSION, "fits": fits, "count_method": method,
        "measurement": measured,
        "provider_input_ids_available": measured.get("exact_provider_token_ids_available", False),
        "selected_prompt_token_reservation": count, "reserved_output_tokens": MAX_OUTPUT_TOKENS,
        "context_limit": CONTEXT_LIMIT, "maximum_input_tokens": MAX_INPUT_TOKENS,
        "measurements": measurements, "sdk_context_selection": SDK_CONTEXT_SELECTION,
        "format_feedback_projection": feedback, "static_deduplication": deduplication,
        "same_input_references": references, "reference_validation": validation,
        "selected_indices": mapped,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in mapped],
        "original_request_sha256": digest(json_bytes(request)),
        "selected_request_sha256": digest(json_bytes(selected)),
        "wire_request_sha256": wire_sha,
        "capacity_protected_observation_indices": sorted(protected_observations),
        "latest_complete_round_preserved": protected["latest_complete_round_preserved"]}
    return selected, wire, projection


class ManagedContextTransport:
    def __init__(self, owner, directory):
        self.owner, self.directory = owner, Path(directory)
        self.counter, self._turn, self._prepared = 0, None, None
        self.feedback_ledger = ManagedFeedbackLedger()
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
        measure = {"version": "v064-managed-budget-preparation-r1",
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


class ProjectOwner:
    """Key-free facade over the exact same model broker used by REF."""
    def __init__(self, adapter, *, window_id, identity):
        if (adapter.limits.get("context_limit") != CONTEXT_LIMIT
                or adapter.maximum_output_tokens != MAX_OUTPUT_TOKENS
                or adapter.maximum_input_tokens != MAX_INPUT_TOKENS
                or adapter.thinking is not True or not isinstance(adapter.model, str)
                or not adapter.model or not isinstance(window_id, str) or not window_id
                or not isinstance(identity, dict) or not identity.get("policy_version")):
            raise ValueError("PROJECT requires the same explicit REF model resources and frozen identity")
        self.adapter, self.window_id, self.identity = adapter, window_id, copy.deepcopy(identity)
        self.recipe = {"max_length": CONTEXT_LIMIT, "max_output_tokens": MAX_OUTPUT_TOKENS,
                       "temperature": .6}
        self.transport = self

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def complete(self, request, *, timeout_seconds):
        if timeout_seconds != REQUEST_SECONDS:
            raise ValueError("The managed request timeout must equal REF's 1800 seconds")
        body = self.adapter.complete(request, "agent")
        return {"http_status": 200, "body": body, "raw_body": json_bytes(body).decode(),
                "response_headers": {}, "response_redactions": []}


def worker_config(owner, case, *, public_initial_message):
    from .online_collection import _config
    if not isinstance(public_initial_message, str) or not public_initial_message.strip():
        raise ValueError("Bind the same public issue and environment guidance used by REF")
    config = _config(owner, world.MEMBERS[0],
                     world.member_instruction(case) + "\n\n" + public_initial_message,
                     case["role_decision_limits"])
    config.update(backend_id="key_free_model_broker_v064", model=owner.adapter.model,
                  api_key_env=None, thinking=True, reasoning_effort=None,
                  context_policy="full_history", format_error_policy="format_feedback_budgeted_v033",
                  max_output_tokens=MAX_OUTPUT_TOKENS, max_context_tokens=CONTEXT_LIMIT,
                  timeout_seconds=REQUEST_SECONDS)
    config["budget"].update(max_decisions=ATTEMPT_LIMIT, max_http_attempts=ATTEMPT_LIMIT,
                            max_total_tokens=case["team_limits"]["max_total_tokens"],
                            max_context_bytes=MAX_RAW_CONTEXT_BYTES)
    return config


def model_reservation(request, prepared):
    """Only the complete counted wire can reserve an actual model opportunity."""
    if prepared is None:
        raise ValueError("Managed requests require a bound, counted Gamma preparation")
    unsealed = {k: v for k, v in prepared.items() if k != "preparation_sha256"}
    if (prepared.get("version") != "v064-managed-budget-preparation-r1"
            or prepared.get("preparation_sha256") != digest(json_bytes(unsealed))
            or prepared.get("original_request_sha256") != digest(json_bytes(request))
            or prepared.get("reserved_output_tokens") != MAX_OUTPUT_TOKENS
            or prepared.get("context_limit") != CONTEXT_LIMIT
            or type(prepared.get("prompt_tokens")) is not int):
        raise ValueError("The exact model preparation identity or resource limit changed")
    fits = 0 <= prepared["prompt_tokens"] <= MAX_INPUT_TOKENS
    if prepared.get("fits") is not fits:
        raise ValueError("The managed context qualification contradicts its measured tokens")
    if not fits:
        from .team_budget_v033 import V033PolicyBoundaryError
        raise V033PolicyBoundaryError("model_budget_exhausted", "full_context_capacity",
            memory={}, details={"limits": ["context_capacity"], "budget_kind": "context_capacity"})
    return {"request_bytes": len(json_bytes(request)),
            "input_token_reservation": prepared["prompt_tokens"],
            "output_token_reservation": MAX_OUTPUT_TOKENS,
            "token_reservation": prepared["prompt_tokens"] + MAX_OUTPUT_TOKENS,
            "cost_reservation_usd": 0, "method": prepared["count_method"],
            "reservation_kind": "bound_model_broker_count", "preparation": prepared,
            "monetary_authority": "trusted model broker ledger; never a controller USD estimate"}


@cache
def worker_type():
    from .model_policy import ModelPolicy
    from .software_benchmark_deepseek_adapter_v064 import RemoteEpisodeBoundary
    from .software_benchmark_ref_budget_v064 import BeforeQwenDispatch

    class BrokerAccountant(ModelPolicy):
        def _reserve(self, request, *, prepared=None, actor_identity=None):
            return model_reservation(request, prepared)

    class AlignedManagedWorker(managed_worker_type()):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._accountant = BrokerAccountant(self.config, transport=self.transport)
            self._accountant.bind_event_sink(self._emit)
            self.llm.max_input_tokens = MAX_INPUT_TOKENS

        def _sdk_response(self, body):
            try:
                projection, receipt = normalize_response(body)
            except Exception as error:
                self._fail("execution_integrity_error", "SDK reasoning projection failed: " + str(error))
            message = projection["choices"][0]["message"]
            for call in message.get("tool_calls") or []:
                if call["id"] in self._assistant_messages:
                    if self._assistant_messages[call["id"]] != body["choices"][0]["message"]:
                        self._fail("execution_integrity_error", "Recorded assistant provenance changed")
                    self._assistant_messages[call["id"]] = copy.deepcopy(message)
            self._emit("managed_reasoning_projection_v064", receipt)
            return super()._sdk_response(projection)

        def _complete(self, messages, tools):
            try:
                return super()._complete(messages, tools)
            except (ManagedBeforeDispatch, RemoteEpisodeBoundary, BeforeQwenDispatch) as error:
                self.team_budget.cancel_provider_before_dispatch(
                    self.role_id, self._association["call_id"], str(error))
                self.meter["http_attempts"] -= 1
                self._emit("model_broker_pre_dispatch_cancellation_v064", {
                    **self._association, "reason": str(error), "provider_dispatch_started": False,
                    "actual_tokens": 0, "reservation_released": True, "decision_consumed": True})
                self._fail("model_budget_exhausted", str(error), provider_dispatch_started=False)

    return AlignedManagedWorker


class PublicTestCallback:
    """A version-bound public-only call into the actor RPC; no host execution."""
    def __init__(self, callback, *, instance_id, hard_at, folder, clock=time.monotonic):
        if not callable(callback) or not instance_id or hard_at <= clock():
            raise ValueError("Bind an actual public-test RPC and a future episode deadline")
        self.callback, self.instance_id, self.hard_at = callback, instance_id, hard_at
        self.folder, self.clock = Path(folder), clock
        self.world, self.calls = None, 0

    def bind_world(self, prepared):
        if self.world is not None or prepared.case["case_id"] != self.instance_id:
            raise ValueError("Public test RPC must bind exactly its new task world once")
        self.world = prepared.world

    def __call__(self, *, files, entry_metadata, task, run_root):
        if self.world is None or self.clock() >= self.hard_at:
            raise ValueError("No public test is permitted without its live, bounded world")
        artifact, version, bundle = self.world._bundle(world.MEMBERS[0])
        tree = tree_manifest(files, entry_metadata)["tree_sha256"]
        if tree_manifest(bundle["files"], bundle["entry_metadata"])["tree_sha256"] != tree:
            raise ValueError("The public test request is not the current exact managed version")
        self.calls += 1
        request = {"version": VERSION, "instance_id": self.instance_id, "call_index": self.calls,
                   "source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
                   "tree_sha256": tree, "hard_deadline_monotonic": self.hard_at,
                   "hidden_evaluation": False, "arbitrary_command": False}
        folder = self.folder / f"test-{self.calls:04d}"
        folder.mkdir(parents=True, exist_ok=False)
        write_new(folder / "request.json", request)
        result = self.callback(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
                               request=copy.deepcopy(request))
        write_new(folder / "response.json", result)
        if (not isinstance(result, dict) or not isinstance(result.get("execution"), dict)
                or result["execution"].get("input_tree_sha256") != tree
                or type(result["execution"].get("executed")) is not bool
                or type(result.get("passed")) is not bool or not isinstance(result.get("groups"), dict)
                or (result["passed"] and not result["execution"]["executed"])):
            raise ValueError("The actor public-test receipt lacks truthful same-tree execution evidence")
        return result


def prepare_case(source_manifest, folder, *, max_total_tokens, public_test_callback, deadline):
    provider = RepositorySources(source_manifest)
    if len(provider.case_ids) != 1:
        raise ValueError("One isolated PROJECT controller receives exactly one public task")
    callback = PublicTestCallback(public_test_callback,
        instance_id=provider.case_ids[0], hard_at=deadline.hard_at,
        folder=Path(folder).parent / "public-test-rpc", clock=deadline.clock)
    provider.runner = callback
    prepared = world.build_software_collaboration_case(provider.case_ids[0], folder,
        provider=provider, max_total_tokens=max_total_tokens)
    callback.bind_world(prepared)
    return prepared


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None):
    """Construct the real managed SDK worker without dispatching a model call."""
    from . import software_calibration_collector_v051 as base
    from .experience import capture_port
    from .harness_port import HarnessPort
    from .software_organization_runtime_v038 import _CollectionOwner
    from .software_organization_runtime_v047 import NativeDispatchGate

    world.validate_case(prepared.case, provider=prepared.source_provider)
    if ((deadline.soft_seconds, deadline.hard_seconds) != (SOFT_SECONDS, HARD_SECONDS)
            or not isinstance(prepared.source_provider.runner, PublicTestCallback)
            or prepared.source_provider.runner.world is not prepared.world
            or prepared.source_provider.runner.hard_at != deadline.hard_at):
        raise ValueError("The actual public runner and deadlines must bind this aligned episode")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = base._StreamRecorder(folder / "experience.jsonl")
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = ManagedTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        require_exact_resident=False, **{key: prepared.case["team_limits"][key]
        for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    gate = NativeDispatchGate(owner.transport, deadline)
    context = ManagedContextTransport(_CollectionOwner(owner, gate), folder / "managed-transport")
    gate.context, context.native_dispatch_gate = context, gate
    facade = _CollectionOwner(owner, context)
    captured, interfaces, holder = {}, {}, {}
    worker_factory = worker_factory or worker_type()

    def create_member(member, record):
        interface = world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
        interfaces[member] = interface
        rows = base._StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        config = worker_config(owner, prepared.case, public_initial_message=public_initial_message)
        port = HarnessPort(capture_port(interface, rows), member, project_id=world.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(member, payload, association))
        worker = worker_factory(member, port.tools(), config, transport=context, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=SDK_CONTEXT_SELECTION)
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
    if any(event["kind"] in {"model_call", "tool_call"} for event in recorder.events) or before != prepared.world.store.load():
        base.close_runtime(runtime)
        raise ValueError("Managed assembly cannot sample a model or change world state")
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in runtime.labels:
        recorder.record("organization_session_born", runtime.birth_records[member], worker_id=member)
    runtime.note_population("initial")
    write_new(folder / "alignment.json", {
        "version": VERSION, "actual_managed_S1_runtime": True, "context_limit": CONTEXT_LIMIT,
        "maximum_input_tokens": MAX_INPUT_TOKENS, "maximum_output_tokens": MAX_OUTPUT_TOKENS,
        "sdk_context_selection": SDK_CONTEXT_SELECTION, "actual_team_limits": prepared.case["team_limits"],
        "sdk_run_iteration_limit_per_managed_opportunity": 2,
        "sdk_run_iteration_scope": "Pause after one managed action; not a two-step whole-episode limit",
        "public_initial_message_sha256": digest(public_initial_message.encode()),
        "model_calls_during_assembly": 0, "hidden_evaluation_accessible": False,
        "unmanaged_bash_added": False, "previous_32_test_and_500k_member_gates_retained": False})
    return runtime, captured, interfaces


