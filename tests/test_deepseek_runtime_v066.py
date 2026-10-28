from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_deepseek_runtime_v064 as predecessor
from proworksim import software_benchmark_deepseek_runtime_v066 as runtime


def ready():
    return {"state": "ready", "can_start_generation": True, "temporary_wait": False}


def fake_ledger(tmp_path, monkeypatch):
    ledger = api.BudgetLedger(tmp_path / "test-only.sqlite3", max_concurrency=64)

    @contextmanager
    def read():
        with ledger._connect() as db:
            db.execute("PRAGMA query_only=ON")
            yield db

    monkeypatch.setattr(runtime, "_ledger_read", read)
    monkeypatch.setattr(predecessor, "budget_status", ready)
    return ledger


def reserve(ledger, slot="v064:task:DEEPSEEK_PROJECT_B5000K:1"):
    ledger.reserve(request_id=slot + ":0001", slot_id=slot, condition="DEEPSEEK_PROJECT_B5000K",
        usage_id="agent", request_sha256="a" * 64, prompt_upper_bound=100, max_output_tokens=32768)


def test_unique_old_budget_and_qualification_no_constructor_io(monkeypatch):
    assert runtime.LEDGER == predecessor.LEDGER
    assert runtime.QUALIFICATION == predecessor.QUALIFICATION
    assert runtime.SCHEMA_FILE == predecessor.SCHEMA_FILE
    assert runtime.api.CAP_NANOYUAN == 1500 * 10**9
    monkeypatch.setattr(api, "load_api_key", lambda *_: pytest.fail("No key access in construction"))
    monkeypatch.setattr(api, "DeepSeekClient", lambda **_: pytest.fail("No client in construction"))
    value = runtime.DeepSeekRuntime()
    assert value.client is None and value.rows is None
    with pytest.raises(runtime.APIQualificationPending):
        value.logical_resident()


def test_uncertain_provider_attempt_stops_api_only_without_releasing_money(tmp_path, monkeypatch):
    ledger = fake_ledger(tmp_path, monkeypatch)
    reserve(ledger)
    assert runtime.budget_status()["can_start_generation"] is True
    ledger.uncertain("v064:task:DEEPSEEK_PROJECT_B5000K:1:0001", {"reason": "connection_lost"})
    before = ledger.snapshot()["committed_upper_cny"]
    result = runtime.budget_status()
    assert result["state"] == "shared_halted" and result["failure_scope"] == "API"
    assert result["qwen_stop_required"] is False and result["temporary_wait"] is False
    assert result["new_cash_budget"] is False and result["new_neutral_calls"] == 0
    assert ledger.snapshot()["committed_upper_cny"] == before == 5.24288


def test_bad_qualification_is_api_unavailable_without_key_or_neutral_retry(monkeypatch):
    monkeypatch.setattr(runtime.policy, "require_v066_allowed", lambda *_: None)
    monkeypatch.setattr(runtime, "budget_status", lambda: {"state": "qualification_failed"})
    monkeypatch.setattr(api, "load_api_key", lambda *_: pytest.fail("No key on failed old qualification"))
    with pytest.raises(runtime.APIUnavailable) as failure:
        runtime.DeepSeekRuntime().initialize_for_run()
    assert failure.value.failure_scope == "API"


def fixture_runtime(tmp_path, monkeypatch):
    ledger = fake_ledger(tmp_path, monkeypatch)
    row = {"slot_id": "v064:task:DEEPSEEK_PROJECT_B5000K:1", "slot_index": 25,
        "condition_id": "DEEPSEEK_PROJECT_B5000K", "model_key": "DEEPSEEK", "instance_id": "task",
        "arm": "PROJECT", "input_plus_output_tokens": 5_000_000, "seed": 1,
        "configuration": {"path": "old.json", "sha256": "a" * 64, "bytes": 2}}
    operations = []
    monkeypatch.setattr(runtime.policy, "require_v066_allowed",
        lambda operation, **kwargs: operations.append(operation))
    aborts = []
    client = SimpleNamespace(fork_for_episode=lambda: SimpleNamespace(
        transport=SimpleNamespace(abort=lambda: aborts.append("API"))))
    value = runtime.DeepSeekRuntime()
    value.client, value.counter = client, lambda _: {}
    value.rows = {row["slot_id"]: row}
    value.schemas = {"tool_names": {"PROJECT": ["read_file", "staff_done"]}}
    payload = {"slot_id": row["slot_id"], "condition": row["condition_id"],
        "request_id": row["slot_id"] + ":0001", "usage_id": "agent", "wire": {"max_tokens": 32768,
        "tools": [{"type": "function", "function": {"name": name}} for name in ("read_file", "staff_done")]}}
    return value, row, payload, ledger, operations, aborts


def test_frozen_slot_schema_and_single_broker_are_enforced(tmp_path, monkeypatch):
    value, row, payload, _, operations, _ = fixture_runtime(tmp_path, monkeypatch)
    transport = value.transport_factory(row, tmp_path / "episode")
    assert transport.authorize(payload)["token_budget"] == 5_000_000
    assert set(operations) == {"v066.api.request"}
    for changed in ({"seed": 2}, {"input_plus_output_tokens": 10_000_000}, {"slot_id": "v064:other"}):
        with pytest.raises(ValueError, match="eligible unchanged"):
            value.transport_factory({**row, **changed}, tmp_path / "other")
    with pytest.raises(ValueError, match="one fresh broker"):
        value.transport_factory(row, tmp_path / "duplicate")
    with pytest.raises(ValueError, match="schemas"):
        transport.authorize({**payload, "wire": {"max_tokens": 32768, "tools": []}})


def test_any_existing_api_attempt_forbids_replay(tmp_path, monkeypatch):
    value, row, _, ledger, _, _ = fixture_runtime(tmp_path, monkeypatch)
    reserve(ledger, row["slot_id"])
    with pytest.raises(ValueError, match="forbids replay"):
        value.transport_factory(row, tmp_path / "episode")


def test_provider_cancel_is_sticky_private_and_proven_before_dispatch(tmp_path, monkeypatch):
    value, row, payload, _, _, aborts = fixture_runtime(tmp_path, monkeypatch)
    transport = value.transport_factory(row, tmp_path / "episode")
    result = value.cancel_all()
    assert aborts == ["API"] and result["qwen_touched"] is False
    assert result["money_reservations_released"] is False
    with pytest.raises(api.PreDispatchBudgetStopped) as failure:
        transport.authorize(payload)
    assert failure.value.before_dispatch_proven is True
    with pytest.raises(api.PreDispatchBudgetStopped):
        value.transport_factory(row, tmp_path / "next")
