"""Settled-output boundaries use scripted CPU data, never a model or network."""
from __future__ import annotations

import copy
import json

import pytest

from proworksim import software_benchmark_qwen_truncation_v090 as policy
from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, RefLedger
from proworksim.storage import digest, json_bytes


def response(*, finish="length", content=None, reasoning="synthetic reasoning", calls=None):
    completion = 32768 if finish == "length" else 12
    return {"id": "synthetic-response", "model": REF_MODEL,
            "choices": [{"index": 0, "finish_reason": finish, "message": {
                "role": "assistant", "content": content, "reasoning": reasoning,
                "tool_calls": calls}}],
            "usage": {"prompt_tokens": 32, "completion_tokens": completion,
                      "total_tokens": completion + 32,
                      "completion_tokens_details": {"reasoning_tokens": completion}}}


class ScriptedDelegate:
    condition = {"model_key": "QWEN", "arm": "REF"}
    slot_id = "v064:cpu-fixture:0"

    def __init__(self, folder, body):
        self.folder, self.body = folder, body
        self.folder.mkdir()
        self.ledger = RefLedger()
        self.requests, self.count_requests = 0, 0
        self.after_settle = lambda _: None

    def count(self, request):
        self.count_requests += 1
        return {"prompt_tokens": 32, "sha256": digest(json_bytes(request))}

    def complete(self, request, usage_id):
        self.requests += 1
        self.ledger.reserve(self.count(request), usage_id,
                            write_new(self.folder / "request.json", request))
        self.ledger.settle(self.body, write_new(self.folder / "response.json", self.body))
        self.after_settle(self.ledger)
        return self.body


def setup(tmp_path, body=None):
    delegate = ScriptedDelegate(tmp_path / "raw", response() if body is None else body)
    guard = policy.ReasoningTruncationAdapter(delegate, folder=tmp_path / "guard",
        workspace_id=delegate.slot_id, progress_snapshot=lambda: {"tool_rpc_count": 7})
    return delegate, guard


REQUEST = {"model": REF_MODEL, "max_tokens": 32768, "messages": [], "tools": []}


@pytest.mark.parametrize(("changes", "kind", "stop"), [
    ({}, "reasoning_only", True),
    ({"content": "  \n"}, "reasoning_only", True),
    ({"finish": "stop"}, "reasoning_only", False),
    ({"reasoning": None}, "empty", False),
    ({"reasoning": None, "finish": "stop"}, "empty", False),
    ({"content": "Partial visible response"}, "visible_content", False),
    ({"calls": [{"id": "tool", "function": {"name": "think", "arguments": "{}"}}]}, "tool_calls", False),
])
def test_response_categories_preserve_original_and_only_match_exact_case(changes, kind, stop):
    body = response(**changes)
    original = copy.deepcopy(body)
    observed = policy.classify_response(body)
    assert observed["kind"] == kind and observed["requires_local_stop"] is stop
    assert body == original
    assert "synthetic reasoning" not in json.dumps(observed)


def test_first_truncation_is_fully_charged_sticky_and_not_fabricated_finish(tmp_path):
    delegate, guard = setup(tmp_path)
    with pytest.raises(policy.SettledReasoningTruncation) as caught:
        guard.complete(REQUEST, "agent")
    assert delegate.requests == 1
    assert json.loads((delegate.folder / "response.json").read_bytes()) == delegate.body
    ledger = delegate.ledger.snapshot()
    assert ledger["complete_actual_tokens"] == 32800 and ledger["inflight"] is None
    receipt = json.loads((guard.folder / "output-truncation.json").read_bytes())
    assert receipt["observed_tool_progress_unchanged"]
    assert not receipt["native_finish_fabricated"] and not receipt["filesystem_unchanged_claimed"]
    assert not receipt["generic_sdk_nudge_emitted_for_this_response"]
    assert not receipt["automatic_retry"] and not receipt["reasoning_replayed"]
    assert "synthetic reasoning" not in json.dumps(receipt)
    boundary = policy.unwrap_local_boundary(caught.value, guard)
    assert boundary["known_usage"] and boundary["generation_dispatched_at_boundary"]
    assert not boundary["native_finished"]
    for operation in (lambda: guard.count(REQUEST), lambda: guard.complete(REQUEST, "agent"),
                      lambda: guard.complete(REQUEST, "condenser")):
        with pytest.raises(policy.SettledReasoningTruncation) as same:
            operation()
        assert same.value is caught.value
    assert delegate.requests == delegate.count_requests == 1
    assert policy.unwrap_local_boundary(policy.SettledReasoningTruncation(policy.REASON), guard) is None


@pytest.mark.parametrize("usage_id", ["agent", "condenser"])
def test_other_outputs_and_condenser_keep_original_body_and_budget(tmp_path, usage_id):
    body = response(content="Already visible content") if usage_id == "agent" else response()
    delegate, guard = setup(tmp_path, body)
    assert guard.complete(REQUEST, usage_id) is body
    assert delegate.requests == 1 and delegate.ledger.actual == 32800
    assert guard.truncation_snapshot()["boundary"] is None


@pytest.mark.parametrize("fault", ["unknown_usage", "wrong_response_hash", "wrong_total"])
def test_uncertain_or_unbound_usage_is_never_a_local_boundary(tmp_path, fault):
    delegate, guard = setup(tmp_path)
    def corrupt(ledger):
        if fault == "unknown_usage":
            ledger.inflight = {"reservation": 1}
        elif fault == "wrong_response_hash":
            ledger.calls[-1]["response"]["sha256"] = "0" * 64
        else:
            ledger.actual += 1
    delegate.after_settle = corrupt
    with pytest.raises(policy.TruncationProtocolFault) as caught:
        guard.complete(REQUEST, "agent")
    assert policy.unwrap_local_boundary(caught.value, guard) is None
    assert not (guard.folder / "output-truncation.json").exists()
    with pytest.raises(policy.TruncationProtocolFault):
        guard.count(REQUEST)
    assert delegate.requests == 1


def test_protocol_conflicts_do_not_become_successful_truncations(tmp_path):
    body = response()
    body["choices"][0]["message"]["reasoning_content"] = "conflicting reasoning"
    delegate, guard = setup(tmp_path, body)
    with pytest.raises(policy.TruncationProtocolFault, match="Ambiguous"):
        guard.complete(REQUEST, "agent")
    assert delegate.ledger.actual == 32800 and guard.truncation_snapshot()["fault"]
    assert guard.truncation_snapshot()["boundary"] is None


def test_failure_to_record_boundary_remains_a_fault_not_a_known_stop(tmp_path, monkeypatch):
    delegate, guard = setup(tmp_path)
    def fail(*_):
        raise OSError("synthetic evidence disk failure")
    monkeypatch.setattr(policy, "write_new", fail)
    with pytest.raises(policy.TruncationProtocolFault, match="persist") as caught:
        guard.complete(REQUEST, "agent")
    assert policy.unwrap_local_boundary(caught.value, guard) is None
    assert delegate.requests == 1
    with pytest.raises(policy.TruncationProtocolFault):
        guard.complete(REQUEST, "agent")


def test_policy_requires_fresh_scope_and_immutable_post_stop_accounting(tmp_path):
    delegate, guard = setup(tmp_path)
    with pytest.raises(ValueError, match="fresh"):
        policy.ReasoningTruncationAdapter(delegate, folder=tmp_path / "second",
            workspace_id=delegate.slot_id, progress_snapshot=lambda: {"tool_rpc_count": 7})
    with pytest.raises(policy.SettledReasoningTruncation) as caught:
        guard.complete(REQUEST, "agent")
    delegate.ledger.actual += 1
    with pytest.raises(policy.TruncationProtocolFault, match="Ledger changed"):
        policy.unwrap_local_boundary(caught.value, guard)


def test_missing_persisted_boundary_is_not_accepted_as_known_closure(tmp_path):
    _, guard = setup(tmp_path)
    with pytest.raises(policy.SettledReasoningTruncation) as caught:
        guard.complete(REQUEST, "agent")
    (guard.folder / "output-truncation.json").unlink()
    with pytest.raises(policy.TruncationProtocolFault, match="evidence"):
        policy.unwrap_local_boundary(caught.value, guard)


def test_queued_second_completion_cannot_cross_the_first_local_stop(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    delegate, guard = setup(tmp_path)
    entered, release = Event(), Event()
    original = delegate.complete
    def paused(request, usage_id):
        entered.set()
        assert release.wait(5)
        return original(request, usage_id)
    delegate.complete = paused
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(guard.complete, REQUEST, "agent")
        assert entered.wait(5)
        two = pool.submit(guard.complete, REQUEST, "agent")
        release.set()
        with pytest.raises(policy.SettledReasoningTruncation) as first:
            one.result(timeout=5)
        with pytest.raises(policy.SettledReasoningTruncation) as second:
            two.result(timeout=5)
    assert first.value is second.value and delegate.requests == 1


def test_pinned_sdk_never_gets_to_its_generic_empty_response_nudge(tmp_path):
    """Run only a scripted SDK control via the already installed private loader."""
    import os
    from pathlib import Path
    import subprocess

    root = Path(__file__).resolve().parents[1]
    runtime = root / "runs/software-benchmark-v066/sdk-bundle-r1/stage/opt/pws-runtime"
    python = runtime / "bin/python"
    if not python.is_file():
        pytest.skip("Existing pinned SDK bundle is unavailable")
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join(map(str, [root / "src", runtime / "site", runtime / "overlay",
                                                 runtime / "upstream-tools"])),
               OH_PERSISTENCE_DIR=str(tmp_path / "empty-user-config"),
               LITELLM_LOCAL_MODEL_COST_MAP="True", PYTHON_DOTENV_DISABLED="1",
               PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")
    completed = subprocess.run([str(python), str(root / "tools/check_qwen_truncation_v090.py"),
                                "--output", str(tmp_path / "sdk")],
                               env=env, text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stdout[-3000:] + completed.stderr[-3000:]
    receipt = json.loads((tmp_path / "sdk/result.json").read_bytes())
    assert receipt["passed"] and receipt["scripted_responses"] == 1
    assert receipt["model_calls"] == receipt["remote_tool_calls"] == 0
    assert receipt["generic_nudges"] == 0 and receipt["known_boundary"]
    assert not any(receipt["forbidden_operations"].values())
