"""Scripted-only end-to-end Flash wire and cash/accounting controls."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_contract_v105 as contract
from proworksim import software_benchmark_deepseek_adapter_v105 as remote
from proworksim import software_benchmark_deepseek_api_v105 as api
from proworksim import software_benchmark_deepseek_api_v064 as prior_api
from proworksim import software_benchmark_managed_v105 as managed
from proworksim import software_benchmark_managed_v064 as base_managed
from proworksim import software_benchmark_budget_closure_v103 as budget
from proworksim.storage import digest, json_bytes


def response(prompt=98304, *, reasoning=False):
    message = {"role": "assistant", "content": "scripted response without a reasoning field"}
    if reasoning:
        message["reasoning_content"] = "unexpected scripted thinking"
    return {"id": "cpu-response-v105", "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": 30,
            "total_tokens": prompt + 30, "prompt_cache_hit_tokens": 100,
            "prompt_cache_miss_tokens": prompt - 100,
            "completion_tokens_details": {"reasoning_tokens": 1 if reasoning else 0}}}


def fixture(tmp_path, arm, *, body=None, error=None, used=4_883_127):
    calls, counts = [], []

    def counter(wire):
        counts.append(copy.deepcopy(wire))
        assert wire["thinking"] == {"type": "disabled"}
        return {"prompt_tokens": 98304, "request_sha256": digest(json_bytes(wire)),
                "method": "scripted count, not a provider/tokenizer measurement"}

    class ScriptedHTTP:
        def request(self, method, path, payload=None):
            assert (method, path) == ("POST", "/chat/completions")
            calls.append(copy.deepcopy(payload))
            if error:
                raise error
            return body if body is not None else response()

    names = remote.NATIVE_TOOLS if arm == "REF" else {"read_file"}
    client = api.DeepSeekClient(ledger_path=tmp_path / "cpu-cash.sqlite",
        api_key="cpu-only-no-credential", allowed_tool_names=names, transport=ScriptedHTTP())
    broker = remote.HostDeepSeekTransport(client=client, counter=counter,
        metadata_dir=tmp_path / "host", authorize=lambda payload: {
            "condition_id": "fixture", "token_budget": 5_000_000})
    adapter = remote.DeepSeekEpisodeAdapter(post=broker.post, arm=arm, slot_id="v105:fixture",
        condition_id="fixture", token_budget=5_000_000, folder=tmp_path / "adapter",
        allowed_tool_names=names)
    adapter.ledger.actual = used  # Synthetic earlier usage, never an old experiment mutation.
    tools = [{"type": "function", "function": {"name": name,
              "parameters": {"type": "object", "properties": {}}}} for name in sorted(names)]
    messages = [{"role": "system", "content": "CPU-only fixture"},
                {"role": "user", "content": json.dumps({"observation": {"task": "fixture"}})}]
    return SimpleNamespace(adapter=adapter, client=client, broker=broker,
                           calls=calls, counts=counts, messages=messages, tools=tools)


def test_frozen_disabled_mode_and_no_remote_search(tmp_path):
    f = fixture(tmp_path, "REF")
    request = f.adapter.request(f.messages, f.tools)
    assert request["thinking"] == {"type": "disabled"}
    assert request["temperature"] == request["top_p"] == 1
    assert "reasoning_effort" not in request and "seed" not in request
    assert contract.validate_condition(contract.condition("REF"))["input_plus_output_tokens"] == 5_000_000
    for change in ({"thinking": {"type": "enabled"}}, {"temperature": True},
                   {"tools": [{"type": "web_search"}]}, {"web_search": True}):
        with pytest.raises(ValueError):
            contract.validate_payload({**request, **change}, f.adapter.allowed_tool_names)
    with pytest.raises(ValueError):
        f.broker.post("/search", {"wire": request})
    assert not f.calls


@pytest.mark.parametrize("arm", ["REF", "PROJECT"])
def test_both_arms_send_same_affordable_output_without_reasoning(tmp_path, arm):
    f = fixture(tmp_path, arm)
    body = f.adapter.complete(f.adapter.request(f.messages, f.tools))
    assert body["choices"][0]["message"].get("reasoning_content") is None
    assert len(f.calls) == 1 and f.calls[0]["max_tokens"] == 18_569
    assert f.calls[0]["thinking"] == {"type": "disabled"}
    assert f.adapter.ledger.calls[0]["reservation"] == 116_873
    assert f.client.ledger.request_status("v105:fixture:0001")["max_output_tokens"] == 18_569
    assert f.adapter.ledger.actual == 4_981_461
    assert f.client.ledger.snapshot()["cap_nanoyuan"] == 350_000_000_000
    assert f.adapter.ledger.calls[0]["normalized_usage"]["cache_hit_tokens"] == 100
    assert all(c["thinking"] == {"type": "disabled"} for c in f.counts)


def test_project_member_team_wire_and_cash_use_identical_output_cap(tmp_path):
    f = fixture(tmp_path, "PROJECT")
    used = f.adapter.ledger.actual
    owner = managed.ProjectOwner(f.adapter, window_id="v105:fixture", identity={"policy_version": "fixture"})
    context = budget.RemainingBudgetContextTransport(owner, tmp_path / "context")
    team = base_managed.ManagedTeamBudget(members=["member_001"], team_id="v105:fixture",
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
    accountant = budget.RemainingBudgetAccountant({"model": "deepseek-flash", "api_key_env": None,
        "base_url": "http://127.0.0.1", "backend_id": "explicit_test_fixture", "thinking": False,
        "budget": {"max_total_tokens": 5_000_000, "max_http_attempts": 512,
                   "max_decisions": 512, "max_context_bytes": 128 * 1024**2}}, transport=context)
    context.bind_budget_sources("member_001", meter=meter, team_budget=team, local_limit=5_000_000)
    team.consume_decision("member_001", "current")
    context.bind_turn("member_001", {"worker_id": "member_001", "call_id": "current"})
    request = {"messages": f.messages, "tools": f.tools}
    prepared = context.prepare_for_budget(request)
    reservation = accountant._reserve(request, prepared=prepared)
    accountant._admit({"meter": meter}, reservation, "current")
    team.reserve("member_001", "current", reservation)
    team.begin_attempt("member_001", "current")
    body = context.complete(request, timeout_seconds=1800)["body"]
    accountant._charge({"meter": meter}, body, reservation)
    team.settle("member_001", "current", body)
    assert prepared["reserved_output_tokens"] == f.calls[0]["max_tokens"] == 18569
    assert meter["budget_accounted_tokens"] == team.snapshot()["charged_tokens"] == f.adapter.ledger.actual


def test_unexpected_thinking_is_settled_but_withheld(tmp_path):
    f = fixture(tmp_path, "REF", body=response(reasoning=True))
    with pytest.raises(api.ProviderOutputBoundViolation, match="thinking"):
        f.adapter.complete(f.adapter.request(f.messages, f.tools))
    assert f.adapter.ledger.actual == 4_981_461
    assert f.client.ledger.request_status("v105:fixture:0001")["status"] == "settled"
    assert f.adapter.halted and not f.adapter.history.messages


def test_unknown_attempt_retains_cash_and_cannot_replay(tmp_path):
    f = fixture(tmp_path, "REF", error=TimeoutError("scripted uncertain response"))
    request = f.adapter.request(f.messages, f.tools)
    with pytest.raises(api.APIUncertainFailure):
        f.adapter.complete(request)
    assert f.client.ledger.request_status("v105:fixture:0001")["status"] == "uncertain"
    assert f.adapter.ledger.snapshot()["uncertain_reserved_tokens"] == 116873
    with pytest.raises(remote.RemoteEpisodeBoundary):
        f.adapter.complete(request)
    assert len(f.calls) == 1


def test_old_cash_policy_cannot_be_reopened_as_new_budget(tmp_path):
    path = tmp_path / "old.sqlite"
    prior_api.BudgetLedger(path)
    with pytest.raises(ValueError, match="another immutable budget policy"):
        api.BudgetLedger(path)
    assert prior_api.BudgetLedger(path).snapshot()["cap_nanoyuan"] == 1500_000_000_000


def test_zero_model_projection_has_no_service_identity_and_real_run_requires_false(tmp_path):
    from proworksim import software_benchmark_sdk_bundle_v105 as bundle
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim.software_benchmark_public_context_v062 import VERSION as context_version

    path = tmp_path / "condition.json"
    path.write_bytes(json_bytes(contract.condition("REF")))
    row = {"slot_id": "v105:fixture", "source_slot_id": "public-fixture", "seed": 1,
           "condition_id": contract.condition("REF")["condition_id"], "arm": "REF",
           "execution_arm": "REF", "model_key": "DEEPSEEK", "instance_id": "fixture__1"}
    host = {**row, "configuration": reference(path),
            "public_task": {"instance_id": "fixture__1", "repo": "fixture/test",
                            "base_commit": "a" * 40, "problem_statement": "CPU fixture"}}
    kwargs = {"public_context": {"version": context_version, "instance_id": "fixture__1",
                                 "visible_text": "Public environment only", "visible_facts": {}},
              "public_environment": {"kind": "official_image", "image_id": "sha256:" + "b" * 64,
                  "source_config_sha256": "b" * 64, "public_python": "/opt/venv/bin/python",
                  "environment": {"PATH": "/opt/venv/bin:/usr/bin:/bin"}}}
    values = bundle.controller_inputs(host, row, {}, {}, "http://127.0.0.1:18210",
                                      diagnostic=True, **kwargs)
    projected = json.loads(values["controller-config.json"])
    assert projected["diagnostic"] and projected["model_identity_value"] == {}
    with pytest.raises(ValueError, match="non-thinking"):
        bundle.controller_inputs(host, row, {}, {}, "http://127.0.0.1:18219", **kwargs)
    projected = bundle.controller_inputs(host, row, {}, {"thinking": False},
                                         "http://127.0.0.1:18219", **kwargs)
    assert json.loads(projected["controller-config.json"])["model_identity_value"]["thinking"] is False
