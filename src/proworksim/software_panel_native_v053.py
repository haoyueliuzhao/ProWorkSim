"""One pinned native OpenHands agent over a preselected SWE-smith task.

The SDK owns the conversation. This module adapts only the unchanged local raw
model provider, bounded container terminal, and per-episode evidence. It does
not reuse the old six-task inventory or its environment admission.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

from .storage import atomic_write, digest, json_bytes

VERSION = "software-panel-native-v0.53"
CONDITION = "raw_qwen35_9b_native_openhands"
CONTRACT = {
    "context_limit": 18432, "max_output_tokens": 2048,
    "enable_thinking": False, "preserve_thinking": False, "temperature": .7,
    "top_p": 1., "top_k": 0, "repetition_penalty": 1.,
    "eos_token_ids": [248044, 248046], "pad_token_id": 248044,
    "max_generation_seconds": 600,
}
LIMITS = {
    "tokens": 500000, "decisions": 128, "attempts": 128,
    "soft_seconds": 5400, "hard_seconds": 6000, "max_residents": 4,
}
PUBLIC_TEST_COMMAND = "bridge_run_tests"
TERMINAL_DESCRIPTION = """Execute one self-contained bash command in the task's Docker repository.
Each command starts a fresh noninteractive bash at /testbed. File edits persist,
but cd/export/shell variables and background jobs never carry between commands.
is_input=True, reset=True and empty polling commands are rejected without execution.
timeout is a hard bounded command limit clamped to 1..60 seconds; no interactive
continuation exists. The repository and its original Docker runtime are accessible;
external network, other episodes and host experiment files are inaccessible.
Run exactly bridge_run_tests, without arguments, for the original repository test
command over the visible tests. Hidden task tests are unavailable to the agent and
are restored only for final grading. Other shell commands are exploratory.
The final original SWE-smith harness
evaluates only the one candidate exported at closure in a separate original image.
The result is the official terminal observation with the real exit code."""
TASK_SUFFIX = """

Work directly in the repository at /testbed inside the original task Docker image.
The official terminal tool uses a fresh noninteractive bash for each command:
cd/export and interactive jobs do not persist. Use one self-contained command,
anchored at /testbed. File edits persist. For the original repository test command,
run exactly bridge_run_tests without arguments; this runs the visible tests only.
Hidden task tests are restored for final grading and are unavailable during work.
Original tests and test collection configuration are restored for final grading;
the candidate export contains repository source, without the actor's environment.
Other commands are exploratory.
External network and host experiment files are inaccessible. Use the native finish
tool when done. The one final candidate exported at closure, before any final score,
is evaluated with the original SWE-smith harness in an independent original image.
"""


def ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def checked(reference):
    path = Path(reference["path"])
    if not path.is_absolute() or ref(path) != reference:
        raise ValueError("A frozen v053 evidence reference changed")
    return path


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(json_bytes(value))
    return ref(path)


class LocalStop(BaseException):
    """A declared local model budget/context boundary; not a system failure."""

    def __init__(self, reason):
        self.reason = reason


class InitialRequestCaptured(BaseException):
    pass


class PublicSystemFault(RuntimeError):
    """An environment, identity, accounting or provider integrity failure."""


@dataclass
class EpisodeLedger:
    """Reserve before generation and settle only identified actual token IDs."""

    identity: dict
    binding: dict
    decisions: int = 0
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    inflight: dict | None = None
    calls: list = field(default_factory=list)

    @property
    def actual(self):
        return self.prompt_tokens + self.completion_tokens

    def decide(self, native):
        if self.inflight is not None:
            raise PublicSystemFault("An in-flight native generation cannot be replayed")
        if self.decisions >= LIMITS["decisions"] or self.attempts >= LIMITS["attempts"]:
            raise LocalStop("decision_or_attempt_limit")
        self.decisions += 1
        if native.get("fits") is not True:
            raise LocalStop("full_native_context_preexecution_rejection")
        prompt = native.get("prompt_tokens")
        if type(prompt) is not int or prompt <= 0:
            raise PublicSystemFault("Native prompt token accounting is absent")
        reservation = prompt + CONTRACT["max_output_tokens"]
        if reservation > LIMITS["tokens"] - self.actual:
            raise LocalStop("full_request_token_reservation_insufficient")
        return reservation

    def reserve(self, native, request_ref, reservation):
        if (self.inflight is not None
                or reservation != native["prompt_tokens"] + CONTRACT["max_output_tokens"]
                or reservation > LIMITS["tokens"] - self.actual):
            raise PublicSystemFault("Invalid native token reservation")
        self.attempts += 1
        self.inflight = {
            "attempt": self.attempts, "reservation": reservation,
            "request": request_ref, "native_input_sha256": native["sha256"],
        }

    def settle(self, native, result, response_ref):
        usage = result.get("usage", {})
        if (self.inflight is None or result.get("actor_identity") != self.identity
                or result.get("input") != native
                or self.inflight.get("native_input_sha256") != native["sha256"]
                or any(type(usage.get(k)) is not int for k in
                       ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != native["prompt_tokens"]
                or usage["completion_tokens"] != len(result.get("output_ids", []))
                or not 0 < usage["completion_tokens"] <= CONTRACT["max_output_tokens"]
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                or not 0 < usage["total_tokens"] <= self.inflight["reservation"]
                or not result.get("attempt_id")
                or any(call["native_attempt_id"] == result["attempt_id"] for call in self.calls)):
            raise PublicSystemFault("Native identity or actual usage cannot settle its reservation")
        self.prompt_tokens += usage["prompt_tokens"]
        self.completion_tokens += usage["completion_tokens"]
        self.calls.append({
            "native_attempt_id": result["attempt_id"], "request": self.inflight["request"],
            "response": response_ref, "usage": copy.deepcopy(usage),
            "native_input_sha256": native["sha256"],
        })
        self.inflight = None

    def snapshot(self):
        return {
            "version": VERSION, "episode_binding": copy.deepcopy(self.binding),
            "decisions": self.decisions, "attempts": self.attempts,
            "complete_responses": len(self.calls), "known_actual_tokens": self.actual,
            "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
            "inflight": copy.deepcopy(self.inflight),
            "uncertain_reservation_tokens": self.inflight["reservation"] if self.inflight else 0,
            "complete_actual_tokens": self.actual if self.inflight is None else None,
            "token_limit": LIMITS["tokens"], "decision_limit": LIMITS["decisions"],
            "attempt_limit": LIMITS["attempts"], "calls": copy.deepcopy(self.calls),
            "automatic_model_retries": False, "local_dollar_cost_estimate": None,
        }


def classify_episode(*, status, stop_reason, sdk_status, ledger, guard, grade, error=None):
    """Unknown technical outcomes never become zeros; model stops retain score."""
    reasons = []
    if status == "execution_fault":
        reasons.append("public_execution_fault")
    if ledger.get("inflight") is not None:
        reasons.append("incomplete_native_generation")
    if not all(guard.get(k) is True for k in (
            "learning_unchanged", "rng_restored_exactly",
            "actor_identity_unchanged", "software_binding_unchanged")):
        reasons.append("evaluation_integrity_guard")
    if type(grade.get("R_code")) is not int or grade["R_code"] not in (0, 1):
        reasons.append("official_harness_outcome_unknown")
    if grade.get("technical_error"):
        reasons.append("official_harness_technical_error")
    if reasons:
        return {"status": "technical_unknown", "R_code": None,
                "decision": "global_pause", "reasons": reasons, "error": error}
    failure = None
    if grade["R_code"] == 0:
        failure = stop_reason or ("model_finished_incomplete"
                                 if sdk_status == "finished" else "model_sdk_local_exit")
    return {"status": "complete", "R_code": grade["R_code"], "decision": "continue",
            "failure_type": failure, "reasons": [], "selected_by_reward": False}


def next_pending_rows(rows, *, started_slot_ids, active_count, paused):
    """Dispatch in frozen order, never by reward, and never replay an entered row."""
    if type(active_count) is not int or not 0 <= active_count <= LIMITS["max_residents"]:
        raise ValueError("At most four resident workers are allowed")
    ids = [row["slot_id"] for row in rows]
    if len(ids) != len(set(ids)) or not set(started_slot_ids) <= set(ids):
        raise ValueError("Scheduler rows and entered identities must be unique and bound")
    if paused:
        return []
    return [row for row in rows if row["slot_id"] not in started_slot_ids][
        :LIMITS["max_residents"] - active_count]


def assert_episode_binding(row, *, panel_sha256, backend_identity):
    if (not isinstance(panel_sha256, str) or len(panel_sha256) != 64
            or not row.get("slot_id") or not row.get("task_id")
            or type(row.get("seed")) is not int or not 0 <= row["seed"] < 2**63
            or row.get("repeat_index") not in (1, 2, 3)
            or backend_identity.get("task_id") != row["task_id"]
            or backend_identity.get("fresh_initial_state") is not True):
        raise ValueError("One frozen v053 row and an independent matching initial state are required")
    return {
        "version": VERSION, "condition": CONDITION, "panel_sha256": panel_sha256,
        "slot_id": row["slot_id"], "task_id": row["task_id"],
        "sampling_seed": row["seed"], "repeat_index": row["repeat_index"],
        "window_id": "software-panel-v053:" + row["slot_id"],
        "backend_identity": copy.deepcopy(backend_identity),
    }


class MetadataOwner:
    """Actual tokenizer/rendering path; no model, tensors or evaluation guard."""

    path = "project"
    contract = CONTRACT

    def __init__(self, tokenizer, *, model_manifest):
        manifest = json.loads(checked(model_manifest).read_bytes())
        from .candidate_runtime_v015 import CHECKPOINTS
        declared = CHECKPOINTS["qwen3.5-9b"]
        if (manifest.get("repo_id") != declared["repo_id"]
                or manifest.get("declared_hf_revision") != declared["revision"]):
            raise ValueError("Initial capture requires the same registered raw model")
        self.tokenizer = tokenizer
        self.identity = {
            "raw_release": True, "trained_adapter_loaded": False,
            "checkpoint": None, "adapter_sha256": None,
            "base_manifest": copy.deepcopy(model_manifest),
            "base_revision": declared["revision"], "metadata_only": True,
        }

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        from .software_calibration_runtime_v051 import prepare_native_input
        native = prepare_native_input(self.tokenizer, request, CONTRACT)
        return native["rendered_prompt"], native["actual_prompt_messages"], native


def validate_owner(owner, *, metadata_only=False, allow_cpu_fixture=False):
    from .software_calibration_runtime_v051 import CalibrationActor
    identity = owner.freeze_identity()
    formal = isinstance(owner, CalibrationActor)
    if (owner.path != "project" or owner.contract != CONTRACT
            or identity.get("raw_release") is not True
            or identity.get("checkpoint") is not None
            or identity.get("adapter_sha256") is not None
            or identity.get("trained_adapter_loaded", False) is not False):
        raise ValueError("v053 uses the unchanged raw/no-adapter local numerical provider")
    if not formal and not metadata_only and not allow_cpu_fixture:
        raise ValueError("A metadata or programmed owner cannot enter a formal episode")
    return identity, formal


class NativeBridge:
    """Shared request adaptation; all model decisions still come from the SDK."""

    def __init__(self, *, owner, binding, folder, initial_capture=None):
        self.owner, self.binding = owner, copy.deepcopy(binding)
        self.folder, self.initial_capture = Path(folder), initial_capture
        self.identity = owner.freeze_identity()
        self.ledger = EpisodeLedger(self.identity, self.binding)
        self.started, self.stop_reason = time.monotonic(), None
        self.events, self.commands, self.rejections = [], [], []
        self.captured = None
        (self.folder / "sdk-events.jsonl").touch(exist_ok=False)
        self.save()

    def save(self):
        write(self.folder / "ledger.json", {
            **self.ledger.snapshot(), "stop_reason": self.stop_reason,
            "preexecution_rejections": self.rejections,
        })

    def on_event(self, event):
        value = event.model_dump(mode="json")
        self.events.append(value)
        with (self.folder / "sdk-events.jsonl").open("ab") as stream:
            stream.write(json.dumps(value, ensure_ascii=False).encode() + b"\n")

    def stop(self, reason, native=None):
        self.stop_reason = reason
        self.rejections.append(write_new(
            self.folder / f"rejection-{len(self.rejections):03d}.json", {
                **self.binding, "reason": reason, "generation_started": False,
                "new_tool_side_effect": False, "decisions": self.ledger.decisions,
                "attempts": self.ledger.attempts,
                "remaining_tokens": LIMITS["tokens"] - self.ledger.actual,
                "elapsed_seconds": time.monotonic() - self.started, "native_input": native,
            }))
        self.save()
        raise LocalStop(reason)

    def completion(self, messages, tools, kwargs):
        from litellm.types.utils import ModelResponse
        from openhands.sdk.llm import Message
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
        from .candidate_runtime_v017 import parse_candidate_generated
        from .deterministic_work_v024 import deterministic_tool_ids
        if time.monotonic() - self.started >= LIMITS["soft_seconds"]:
            self.stop("administrative_soft_deadline")
        request = {
            "model": "raw-qwen3.5-9b-v053",
            "messages": [
                message.to_chat_dict(cache_enabled=False, vision_enabled=False,
                                    function_calling_enabled=True, force_string_serializer=True,
                                    send_reasoning_content=True) for message in messages],
            "tools": [
                dict(tool.to_openai_tool(add_security_risk_prediction=bool(
                    kwargs.get("add_security_risk_prediction", False)))) for tool in tools],
            "temperature": CONTRACT["temperature"], "max_tokens": CONTRACT["max_output_tokens"],
            "stream": False, "tool_choice": "auto",
        }
        if {tool["function"]["name"] for tool in request["tools"]} != {"terminal", "finish"}:
            raise PublicSystemFault("Only the frozen native terminal and finish tools are allowed")
        _, _, native = self.owner.prepare_request(request)
        if self.initial_capture is not None:
            self.captured = {
                "original_request": write_new(self.folder / "original-request.json", request),
                "native_input": write_new(self.folder / "native-input.json", native),
            }
            self.initial_capture(copy.deepcopy(request), copy.deepcopy(native))
            raise InitialRequestCaptured()
        try:
            reservation = self.ledger.decide(native)
        except LocalStop as stop:
            self.stop(stop.reason, native)
        request_ref = write_new(
            self.folder / f"request-{self.ledger.decisions:03d}.json",
            {**self.binding, "request": request, "native_input": native})
        self.ledger.reserve(native, request_ref, reservation)
        self.save()
        result = self.owner.generate_native(native)
        response_ref = write_new(
            self.folder / f"response-{self.ledger.attempts:03d}.json",
            {**self.binding, "native_result": result})
        # Actual provider usage is settled before response parsing. Malformed
        # generated content must not erase real compute from the token ledger.
        self.ledger.settle(native, result, response_ref)
        self.save()
        message, parse_error = parse_candidate_generated(result["raw_generated_text"], request)
        message = deterministic_tool_ids(message, request, result["raw_generated_text"])
        body = {
            "id": "oh-" + result["attempt_id"], "object": "chat.completion",
            "model": request["model"], "choices": [{
                "index": 0, "message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": result["usage"],
        }
        write_new(self.folder / f"sdk-response-{self.ledger.attempts:03d}.json", {
            **self.binding, "native_result": response_ref, "sdk_response": body,
            "protocol_parse_error": parse_error, "native_finish_reason": result["finish_reason"],
        })
        raw = ModelResponse(**body)
        return LLMResponse(
            message=Message.from_llm_chat_message(raw.choices[0].message),
            raw_response=raw, metrics=MetricsSnapshot(
                model_name=request["model"], accumulated_token_usage=TokenUsage(
                    model=request["model"], prompt_tokens=self.ledger.prompt_tokens,
                    completion_tokens=self.ledger.completion_tokens)))


def sdk_provenance(*, tools_overlay=None):
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    from .software_bridge_openhands_v052 import sdk_provenance as pinned_sdk
    actual = pinned_sdk(tools_overlay=tools_overlay)
    return {
        "version": VERSION + "-sdk",
        **{k: actual[k] for k in ("sdk_version", "sdk_commit", "tools_version", "modules",
                                 "tools_overlay", "imported_tool_dependencies")},
        "official_loop_modified": False, "managed_worker_loop_used": False,
        "preset": "official_Agent_Conversation_TerminalTool_FinishTool_container_executor",
        "full_default_preset": False, "terminal_description": TERMINAL_DESCRIPTION,
        "terminal_description_sha256": digest(TERMINAL_DESCRIPTION.encode()),
        "task_suffix_sha256": digest(TASK_SUFFIX.encode()),
    }


def bind_sdk(reference):
    declared = json.loads(checked(reference).read_bytes())
    actual = sdk_provenance(tools_overlay=declared["tools_overlay"]["path"])
    if declared != actual:
        raise ValueError("Pinned v053 official SDK/tools/template identity changed")
    return actual


class ContainerBridge(NativeBridge):
    def __init__(self, *, backend, **kwargs):
        self.backend = backend
        self.public_fault = None
        super().__init__(**kwargs)

    def terminal(self, action):
        from openhands.tools.terminal.definition import TerminalObservation
        from openhands.tools.terminal.metadata import CmdOutputMetadata
        if time.monotonic() - self.started >= LIMITS["hard_seconds"]:
            self.stop("administrative_hard_deadline_before_tool")
        if self.public_fault is not None:
            raise PublicSystemFault(self.public_fault)
        index = len(self.commands)
        if action.is_input or action.reset or not action.command.strip():
            result = {
                "returncode": 2,
                "output": "This executor has no persistent interactive session; use one self-contained command.",
                "execution_kind": "unsupported_interactive_request", "side_effect": False,
            }
        else:
            try:
                if action.command.strip() == PUBLIC_TEST_COMMAND:
                    result = self.backend.run_public_tests()
                    result["execution_kind"] = "original_repository_public_test_command"
                else:
                    result = self.backend.execute(
                        action.command, timeout_seconds=min(60, max(1, action.timeout or 30)))
                    result["execution_kind"] = "original_docker_exploratory_shell"
                if result.get("exception_info") or type(result.get("returncode")) is not int:
                    raise PublicSystemFault("Container execution failed: " + str(result.get("exception_info")))
            except Exception as exc:
                # Some official SDK tool wrappers turn exceptions into tool
                # observations. Persist the public fault and refuse further
                # generations even when the wrapper catches this exception.
                self.public_fault = f"{type(exc).__name__}: {exc}"
                write_new(self.folder / "public-system-fault.json", {
                    **self.binding, "error": self.public_fault, "command_index": index})
                raise
        receipt = {
            "version": VERSION, "episode_binding": self.binding, "index": index,
            "action": action.model_dump(mode="json"), "result": result,
            "native_decision": self.ledger.decisions,
            "elapsed_seconds": time.monotonic() - self.started,
        }
        self.commands.append(write_new(self.folder / f"command-{index:03d}.json", receipt))
        code = 124 if result["returncode"] == -1 else result["returncode"]
        return TerminalObservation.from_text(
            text=result["output"], command=action.command, exit_code=code, timeout=code == 124,
            metadata=CmdOutputMetadata(exit_code=code, working_dir=self.backend.working_dir))

    def completion(self, messages, tools, kwargs):
        if self.public_fault is not None:
            raise PublicSystemFault(self.public_fault)
        return super().completion(messages, tools, kwargs)


def collect_episode(*, owner, row, panel_sha256, task, backend, reference_runtime,
                    episode_folder, initial_capture=None, allow_cpu_fixture=False):
    """One original Agent/Conversation invocation and one pre-scoring export."""
    from .software_bridge_openhands_v052 import sdk_types
    folder = Path(episode_folder).resolve()
    if folder.exists() or task.get("instance_id") != row["task_id"]:
        raise ValueError("A new episode directory and the exact source task are required")
    binding = assert_episode_binding(
        row, panel_sha256=panel_sha256, backend_identity=backend.identity)
    identity, formal = validate_owner(
        owner, metadata_only=initial_capture is not None, allow_cpu_fixture=allow_cpu_fixture)
    binding["actor_identity"] = identity
    folder.mkdir(parents=True)
    persistence = folder / "sdk-config"
    persistence.mkdir()
    os.environ["OH_PERSISTENCE_DIR"] = str(persistence)
    sdk = bind_sdk(reference_runtime)
    from openhands.sdk import Agent, Conversation
    from openhands.sdk.agent import base as official_base
    from openhands.sdk.tool import Tool, register_tool
    from openhands.tools.terminal import TerminalTool
    if official_base._SOUL_PATH.exists():
        raise ValueError("A personal SOUL.md cannot enter the fixed native prompt")
    # The SDK uses this empty directory only for its local configuration discovery.
    # Model terminal actions always execute in the independently owned container.
    workspace = folder / "sdk-workspace"
    workspace.mkdir()
    bridge = ContainerBridge(
        owner=owner, binding=binding, backend=backend, folder=folder, initial_capture=initial_capture)
    llm_type, executor_type = sdk_types()
    registration = "v053_native_terminal_" + uuid.uuid4().hex
    # The official factory validates a local directory even with a supplied
    # executor; its directory is never used by our container executor.
    state = SimpleNamespace(workspace=SimpleNamespace(working_dir=str(workspace)))
    terminal = TerminalTool.create(state, executor=executor_type(bridge))[0]
    terminal = terminal.model_copy(update={"description": TERMINAL_DESCRIPTION})
    register_tool(registration, terminal)
    llm = llm_type(
        model="openai/raw-qwen3.5-9b-v053", usage_id=CONDITION, num_retries=0,
        stream=False, caching_prompt=False, max_input_tokens=CONTRACT["context_limit"],
        max_output_tokens=CONTRACT["max_output_tokens"], temperature=CONTRACT["temperature"])
    llm._bridge = bridge
    agent = Agent(
        llm=llm, tools=[Tool(name=registration)], include_default_tools=["FinishTool"],
        mcp_config={}, condenser=None, agent_context=None, tool_concurrency_limit=1)
    conversation = Conversation(
        agent=agent, workspace=workspace, persistence_dir=folder / "conversations",
        callbacks=[bridge.on_event], plugins=[], max_iteration_per_run=LIMITS["decisions"],
        stuck_detection=True, visualizer=None, delete_on_close=False)
    before = owner.capture_evaluation_state() if initial_capture is None else None
    status, error, guard, captured = "closed", None, {}, False
    try:
        if initial_capture is None:
            owner.begin_window(binding["window_id"])
            owner.reseed(row["seed"], label=row["slot_id"])
        problem = task.get("problem_statement")
        if not isinstance(problem, str) or not problem.strip():
            raise PublicSystemFault("Official source problem statement is absent")
        conversation.send_message(problem + TASK_SUFFIX)
        conversation.run()
    except InitialRequestCaptured:
        status, captured = "initial_request_captured", True
    except LocalStop as stop:
        status, bridge.stop_reason = "safe_local_stop", stop.reason
    except Exception as exc:
        status = "execution_fault"
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        sdk_status = str(conversation.state.execution_status.value)
        try:
            conversation.close()
            if initial_capture is None:
                owner.finish_evaluation([], folder / "owner-evaluation")
                guard = owner.finish_evaluation_guard(before)
                guard.update(
                    actor_identity_unchanged=owner.freeze_identity() == identity,
                    software_binding_unchanged=sdk_provenance() == sdk,
                    backend_identity_unchanged=backend.identity == binding["backend_identity"])
                if guard["backend_identity_unchanged"] is not True:
                    guard["software_binding_unchanged"] = False
                write(folder / "evaluation-guard.json", guard)
        except Exception as exc:
            status = "execution_fault"
            error = {"type": type(exc).__name__, "message": str(exc), "phase": "closing_guard"}
    if captured:
        return {
            **binding, "status": status, **bridge.captured, "sdk_provenance": sdk,
            "decisions": 0, "attempts": 0, "tool_executions": 0, "model_generations": 0,
            "guard_claimed": False, "capture_counters": {
                "native_SDK_LLM_entries": 1, "adapter_decisions": bridge.ledger.decisions,
                "attempts": bridge.ledger.attempts, "reservation_tokens": 0,
                "responses": len(bridge.ledger.calls), "tool_actions": len(bridge.commands),
                "model_generations": bridge.ledger.attempts},
        }
    if initial_capture is not None:
        raise PublicSystemFault("Initial capture did not stop at the native request boundary")
    if bridge.public_fault is not None:
        status, error = "execution_fault", {"type": "ContainerFault", "message": bridge.public_fault}
    if status == "closed" and sdk_status != "finished":
        codes = {event.get("code") for event in bridge.events}
        if sdk_status == "stuck":
            status, bridge.stop_reason = "safe_local_stop", "official_sdk_stuck"
        elif "MaxIterationsReached" in codes:
            status, bridge.stop_reason = "safe_local_stop", "decision_or_attempt_limit"
        else:
            status, error = "execution_fault", {"type": "UnexpectedSDKExit", "message": sdk_status}
    bridge.save()
    # The backend owns the single export lock and refuses a second export.
    # Neither the model nor any score can select another candidate afterwards.
    candidate = backend.export_candidate(folder / "final-candidate")
    checked(candidate)
    result = {
        **binding, "status": status, "sdk_execution_status": sdk_status,
        "error": error, "stop_reason": bridge.stop_reason, "ledger": bridge.ledger.snapshot(),
        "ledger_source": ref(folder / "ledger.json"), "candidate_lock": candidate,
        "sdk_provenance": sdk, "sdk_events": ref(folder / "sdk-events.jsonl"),
        "tool_commands": bridge.commands, "episode_guard": guard,
        "formal_native_provider": formal, "fixture_only": not formal,
        "elapsed_seconds": time.monotonic() - bridge.started,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0,
    }
    write_new(folder / "result.json", result)
    return result
