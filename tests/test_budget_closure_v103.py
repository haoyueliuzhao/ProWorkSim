"""CPU-only accounting controls; all responses and token counts are scripted."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_budget_closure_v103 as repaired
from proworksim import software_benchmark_deepseek_adapter_v064 as remote
from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_managed_v064 as managed
from proworksim.staff_runtime import PolicyBoundaryError
from proworksim.storage import digest, json_bytes


def response(*, prompt=98304, output=30):
    return {"id": "scripted-response", "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant",
            "content": "scripted fixture", "reasoning_content": "scripted reasoning"}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": output,
            "total_tokens": prompt + output, "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": prompt}}


def fixture(tmp_path, *, used=4_883_127, prompt=98304, body=None, error=None):
    calls = []

    def counter(wire):
        return {"prompt_tokens": prompt, "request_sha256": digest(json_bytes(wire)),
                "method": "scripted CPU token bound"}

    class ScriptedHTTP:
        def request(self, method, path, payload=None):
            calls.append(copy.deepcopy(payload))
            if error is not None:
                raise error
            return response(prompt=prompt) if body is None else body

    client = api.DeepSeekClient(ledger_path=tmp_path / "test-only-cash.sqlite",
        api_key="cpu-only-not-a-credential", allowed_tool_names={"read_file"}, transport=ScriptedHTTP())
    broker = remote.HostDeepSeekTransport(client=client, counter=counter,
        metadata_dir=tmp_path / "host", authorize=lambda payload: {
            "condition_id": "fixture", "token_budget": 5_000_000})
    adapter = repaired.RemainingBudgetDeepSeekAdapter(post=broker.post, arm="PROJECT", slot_id="fixture",
        condition_id="fixture", token_budget=5_000_000, folder=tmp_path / "adapter",
        allowed_tool_names={"read_file"})
    adapter.ledger.actual = used  # Explicit synthetic starting state, no historical mutation.
    owner = managed.ProjectOwner(adapter, window_id="fixture", identity={"policy_version": "fixture"})
    context = repaired.RemainingBudgetContextTransport(owner, tmp_path / "context")
    team = managed.ManagedTeamBudget(members=["member_001"], team_id="fixture",
        max_total_tokens=5_000_000, max_decisions=512, max_attempts=512, require_exact_resident=False)
    team.consume_decision("member_001", "synthetic-history")
    team.reserve("member_001", "synthetic-history", {"token_reservation": used})
    team.begin_attempt("member_001", "synthetic-history")
    team.settle("member_001", "synthetic-history", {"id": "synthetic-history",
        "usage": {"prompt_tokens": used, "completion_tokens": 0, "total_tokens": used}})
    meter = {"budget_accounted_tokens": used, "budget_accounted_cost_usd": 0,
        "http_attempts": 1, "decisions": 2, "unknown_usage_attempts": 0,
        "reported_total_tokens": used, "reported_prompt_tokens": used,
        "reported_completion_tokens": 0, "cost_upper_bound_usd": 0}
    policy = repaired.RemainingBudgetAccountant({"model": "deepseek-flash", "api_key_env": None,
        "base_url": "http://127.0.0.1", "backend_id": "explicit_test_fixture",
        "budget": {"max_total_tokens": 5_000_000, "max_http_attempts": 512,
                   "max_decisions": 512, "max_context_bytes": 128 * 1024**2}}, transport=context)
    context.bind_budget_sources("member_001", meter=meter, team_budget=team, local_limit=5_000_000)
    team.consume_decision("member_001", "current")
    context.bind_turn("member_001", {"worker_id": "member_001", "call_id": "current"})
    request = {"messages": [{"role": "system", "content": "fixture rules"},
        {"role": "user", "content": json.dumps({"observation": {"task": "fixture"}})}],
        "tools": [{"type": "function", "function": {"name": "read_file",
            "parameters": {"type": "object", "properties": {}}}}]}
    return SimpleNamespace(context=context, adapter=adapter, broker=broker, client=client,
        team=team, meter=meter, policy=policy, calls=calls, request=request)


def reserve(f):
    prepared = f.context.prepare_for_budget(f.request)
    reservation = f.policy._reserve(f.request, prepared=prepared)
    f.policy._admit({"meter": f.meter}, reservation, "current")
    f.team.reserve("member_001", "current", reservation)
    f.team.begin_attempt("member_001", "current")
    return prepared, reservation


def test_last_request_uses_identical_small_cap_in_all_accounting_layers(tmp_path):
    f = fixture(tmp_path)
    original_request = copy.deepcopy(f.request)
    prepared, reservation = reserve(f)
    assert reservation["output_token_reservation"] == 18_569
    assert reservation["token_reservation"] == 116_873
    assert 98304 + 32768 > 116873  # The historical full-output gate refused this opportunity.
    body = f.context.complete(f.request, timeout_seconds=1800)["body"]
    f.policy._charge({"meter": f.meter}, body, reservation)
    f.team.settle("member_001", "current", body)
    assert f.request == original_request
    assert len(f.calls) == 1 and f.calls[0]["max_tokens"] == 18_569
    assert f.adapter.ledger.calls[0]["reservation"] == 116_873
    assert f.client.ledger.request_status("fixture:0001")["max_output_tokens"] == 18_569
    assert f.meter["budget_accounted_tokens"] == f.team.snapshot()["charged_tokens"] == f.adapter.ledger.actual
    assert f.adapter.ledger.actual == 4_981_461 < 5_000_000
    pending = json.loads((f.context.directory / "request-00001/budget-preparation.json").read_text())
    wire = json.loads((f.context.directory / "request-00001/wire-request.json").read_text())
    assert prepared == pending and prepared["wire_request_sha256"] == digest(json_bytes(wire))
    assert f.adapter.maximum_output_tokens == 32768


def test_regular_requests_keep_full_output_and_history(tmp_path):
    f = fixture(tmp_path, used=10)
    prepared, reservation = reserve(f)
    assert prepared["reserved_output_tokens"] == 32768
    assert reservation["token_reservation"] == 131072
    assert f.context._prepared["selected"] == f.request


def test_input_that_cannot_fit_still_stops_without_dispatch(tmp_path):
    f = fixture(tmp_path, used=4_950_000)
    with pytest.raises(PolicyBoundaryError):
        reserve(f)
    assert not f.calls and f.adapter.ledger.attempts == 0


def test_team_hold_reduces_cap_instead_of_stealing_other_reservations(tmp_path):
    f = fixture(tmp_path)
    f.team.consume_decision("member_001", "other-inflight")
    f.team.reserve("member_001", "other-inflight", {"token_reservation": 5000})
    prepared, reservation = reserve(f)
    assert prepared["reserved_output_tokens"] == 13_569
    assert reservation["token_reservation"] == 111_873
    assert f.team.snapshot()["held_tokens"] == 116_873


def test_uncertain_attempt_preserves_adaptive_hold_and_is_not_replayed(tmp_path):
    f = fixture(tmp_path, error=RuntimeError("scripted missing response"))
    _, reservation = reserve(f)
    with pytest.raises(api.APIUncertainFailure):
        f.context.complete(f.request, timeout_seconds=1800)
    assert f.adapter.ledger.snapshot()["uncertain_reserved_tokens"] == reservation["token_reservation"]
    assert f.client.ledger.request_status("fixture:0001")["status"] == "uncertain"
    with pytest.raises(remote.RemoteEpisodeBoundary):
        f.adapter.complete(f.calls[0])
    assert len(f.calls) == 1


def test_smaller_output_bound_violation_is_billed_and_withheld(tmp_path):
    f = fixture(tmp_path, body=response(output=18_570))
    reserve(f)
    with pytest.raises(api.ProviderOutputBoundViolation):
        f.context.complete(f.request, timeout_seconds=1800)
    assert f.adapter.ledger.actual == 5_000_001
    assert f.adapter.halted and not f.adapter.history.messages
    assert f.client.ledger.request_status("fixture:0001")["status"] == "settled"


def test_changed_preparation_is_rejected(tmp_path):
    f = fixture(tmp_path)
    prepared = f.context.prepare_for_budget(f.request)
    prepared["reserved_output_tokens"] += 1
    with pytest.raises(ValueError, match="exact measured"):
        repaired.model_reservation(f.request, prepared)
    assert not f.calls


def test_fixed_qwen_or_fixture_transport_keeps_old_preparation(tmp_path):
    f = fixture(tmp_path)
    f.adapter.remaining_budget_output_v103 = False
    prepared = f.context.prepare_for_budget(f.request)
    assert prepared["version"] == "v064-managed-budget-preparation-r1"
    assert prepared["reserved_output_tokens"] == 32768
    with pytest.raises(PolicyBoundaryError):
        f.policy._admit({"meter": f.meter}, repaired.model_reservation(f.request, prepared), "current")
    assert not f.calls
