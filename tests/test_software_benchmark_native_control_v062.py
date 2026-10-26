"""Bounded continuation contracts; no models, networks, workers or scoring."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_exact_transport_v057 import ProjectionGuard, ResponseProjectionFault
from proworksim.software_benchmark_native_control_v062 import (
    FINISH_REVIEW,
    STUCK_CORRECTION,
    WORKFLOW_GUIDANCE,
    initial_message,
    run_controlled_conversation,
)


LIMITS = {"input_plus_output_tokens": 5_000_000, "agent_decisions": 512,
          "all_model_attempts": 512, "soft_seconds": 21600, "hard_seconds": 23400}
STARTED = {"started": 1, "soft_at": 21601, "hard_at": 23401}


class Ledger:
    def __init__(self):
        self.value = {"attempts": 0, "decisions": 0, "known_actual_tokens": 0,
                      "complete_actual_tokens": 0, "inflight": None, "uncertain_reserved_tokens": 0,
                      "token_limit": 5_000_000, "agent_decision_limit": 512,
                      "all_model_attempt_limit": 512}

    def snapshot(self):
        return copy.deepcopy(self.value)


class Conversation:
    def __init__(self, adapter, steps):
        self.state = SimpleNamespace(execution_status="idle")
        self.agent = SimpleNamespace(llm=SimpleNamespace(_adapter=adapter._v057_projection_guard))
        self.stuck_detector = object()
        self.adapter, self.steps, self.messages, self.maxima = adapter, list(steps), [], []

    def run(self):
        self.maxima.append(self.max_iteration_per_run)
        step = self.steps.pop(0)
        if callable(step):
            step(self)
            return
        ledger = self.adapter.ledger.value
        ledger["attempts"] += 1
        ledger["decisions"] += 1
        ledger["known_actual_tokens"] += 100
        ledger["complete_actual_tokens"] += 100
        self.state.execution_status = step

    def send_message(self, message, *, sender):
        assert self.state.execution_status in {"stuck", "finished"}
        self.messages.append((message, sender))
        self.state.execution_status = "idle"


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr("proworksim.software_benchmark_native_execution_v057.time.monotonic", lambda: 10)
    adapter = SimpleNamespace(ledger=Ledger())
    adapter._v057_projection_guard = ProjectionGuard(adapter, None)
    return adapter


def run(conversation, **kwargs):
    return run_controlled_conversation(conversation, adapter=conversation.adapter,
                                      started=STARTED, limits=LIMITS, **kwargs)


def test_original_issue_and_admitted_context_are_preserved_verbatim():
    issue = "An issue with literal whitespace.\n"
    context = "Public interpreter: /synthetic/bin/python"
    assert initial_message(issue, public_context=context) == issue + "\n\n" + WORKFLOW_GUIDANCE + "\n\n" + context


@pytest.mark.parametrize(("statuses", "corrections", "reviews", "final"), [
    (["stuck", "stuck", "finished", "finished"], 2, 1, "finished"),
    (["finished", "stuck", "stuck", "stuck"], 2, 1, "stuck"),
    (["stuck", "stuck", "stuck"], 2, 0, "stuck"),
])
def test_total_opportunities_and_same_cumulative_accounting(setup, statuses, corrections, reviews, final):
    conversation = Conversation(setup, statuses)
    events = []
    result = run(conversation, event_sink=events.append)
    assert (result["stuck_corrections"], result["finish_reviews"], result["final_sdk_status"]) == (
        corrections, reviews, final)
    assert conversation.maxima == list(range(512, 512 - len(statuses), -1))
    assert setup.ledger.value["known_actual_tokens"] == len(statuses) * 100
    assert len(conversation.messages) == corrections + reviews
    assert [message for message, _ in conversation.messages].count(STUCK_CORRECTION) == corrections
    assert [message for message, _ in conversation.messages].count(FINISH_REVIEW) == reviews
    assert result["events"] == events and not conversation.steps
    with pytest.raises(ValueError, match="fresh idle"):
        run(conversation)


@pytest.mark.parametrize("status", ["error", "paused", "waiting_for_confirmation", "idle"])
def test_other_sdk_boundaries_are_never_automatically_resumed(setup, status):
    conversation = Conversation(setup, [status])
    assert run(conversation)["sdk_runs"] == 1
    assert not conversation.messages


@pytest.mark.parametrize(("mutation", "reason"), [
    ({"known_actual_tokens": 5_000_000 - 32768, "complete_actual_tokens": 5_000_000 - 32768},
     "no_room_for_complete_output_reservation"),
    ({"decisions": 512}, "agent_decision_limit"),
    ({"attempts": 512}, "model_attempt_limit"),
])
def test_remaining_original_limits_prevent_a_review(setup, mutation, reason):
    def finish(conversation):
        setup.ledger.value.update(mutation)
        conversation.state.execution_status = "finished"
    conversation = Conversation(setup, [finish])
    result = run(conversation)
    assert result["events"][-1]["reason"] == reason
    assert not conversation.messages


def test_absolute_deadline_and_snapshot_limits_are_not_reset(setup, monkeypatch):
    def finish(conversation):
        conversation.state.execution_status = "finished"
        monkeypatch.setattr("proworksim.software_benchmark_native_execution_v057.time.monotonic", lambda: 21601)
    conversation = Conversation(setup, [finish])
    assert run(conversation)["events"][-1]["reason"] == "episode_deadline"
    assert not conversation.messages
    second = Conversation(setup, ["finished"])
    with pytest.raises(ValueError, match="original episode deadlines"):
        run_controlled_conversation(second, adapter=setup, started=STARTED | {"hard_at": 23402}, limits=LIMITS)
    setup.ledger.value["token_limit"] += 1
    with pytest.raises(ValueError, match="original episode limits"):
        run(second)


@pytest.mark.parametrize("mutation", [
    {"complete_actual_tokens": None}, {"inflight": {"reservation": 32768}},
    {"uncertain_reserved_tokens": 1}, {"complete_actual_tokens": 99},
])
def test_unresolved_or_inconsistent_usage_is_not_recovered(setup, mutation):
    def stuck(conversation):
        setup.ledger.value.update(mutation)
        conversation.state.execution_status = "stuck"
    conversation = Conversation(setup, [stuck])
    with pytest.raises(RuntimeError, match="uncertain model usage"):
        run(conversation)
    assert not conversation.messages


def test_swallowed_projection_failure_cannot_create_a_review_or_accept_closure(setup):
    def swallowed(conversation):
        setup._v057_projection_guard.fault = {"synthetic_failure": True}
        conversation.state.execution_status = "finished"
    conversation = Conversation(setup, [swallowed])
    with pytest.raises(ResponseProjectionFault):
        run(conversation)
    assert not conversation.messages


def test_exception_and_object_replacement_do_not_start_a_fresh_attempt(setup):
    def fail(conversation):
        raise RuntimeError("synthetic original exception")
    conversation = Conversation(setup, [fail])
    events = []
    with pytest.raises(RuntimeError, match="original exception"):
        run(conversation, event_sink=events.append)
    assert events[-1]["kind"] == "sdk_run_raised" and not conversation.messages

    def replace(conversation):
        conversation.adapter.ledger = Ledger()
        conversation.state.execution_status = "finished"
    other = Conversation(setup, [replace])
    with pytest.raises(RuntimeError, match="must remain bound"):
        run(other)
    assert not other.messages


def test_actual_pinned_sdk_control(tmp_path):
    """Use the existing ordinary-user loader; no package installs or namespaces."""
    import os
    import subprocess

    root = Path(__file__).resolve().parents[1]
    runtime = root / "runs/software-benchmark-v061/sdk-bundle-r3/stage/opt/pws-runtime"
    python = runtime / "bin/python"
    if not python.is_file():
        pytest.skip("Pinned local SDK bundle is not available")
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join(map(str, [root / "src", runtime / "site", runtime / "overlay",
                                                 runtime / "upstream-tools"])),
               OH_PERSISTENCE_DIR=str(tmp_path / "empty-user-config"), LITELLM_LOCAL_MODEL_COST_MAP="True",
               PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="",
               NVIDIA_VISIBLE_DEVICES="void")
    result = subprocess.run([str(python), str(root / "tools/check_native_control_v062.py"),
                             "--output", str(tmp_path / "sdk-control")],
                            env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-5000:]
    receipt = json.loads((tmp_path / "sdk-control/result.json").read_bytes())
    assert receipt["passed"] and receipt["model_calls"] == receipt["remote_tool_calls"] == 0
    assert receipt["same_agent_condenser_guard"] and not any(receipt["forbidden_operations"].values())
