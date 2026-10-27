from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_deepseek_runtime_v064 as runtime
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def reserve(ledger, request_id, slot_id, condition):
    return ledger.reserve(request_id=request_id, slot_id=slot_id, condition=condition, usage_id="agent",
        request_sha256="a"*64, max_output_tokens=32768, prompt_upper_bound=100)


def ledger_fixture(tmp_path, monkeypatch):
    path, qualification = tmp_path / "cash.sqlite", tmp_path / "qualification.json"
    monkeypatch.setattr(runtime, "LEDGER", path)
    monkeypatch.setattr(runtime, "QUALIFICATION", qualification)
    write_new(qualification, {"passed": True})
    return api.BudgetLedger(path, max_concurrency=64)


def test_constructor_and_pending_status_do_not_load_keys_or_create_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "LEDGER", tmp_path / "absent.sqlite")
    monkeypatch.setattr(runtime, "QUALIFICATION", tmp_path / "absent.json")
    monkeypatch.setattr(api, "load_api_key", lambda *_: pytest.fail("No key load before formal initialization"))
    value = runtime.DeepSeekRuntime()
    assert value.client is None
    assert value.budget_status()["state"] == "qualification_pending"
    assert not runtime.LEDGER.exists()
    with pytest.raises(runtime.APIQualificationPending):
        value.logical_resident()


def test_budget_status_distinguishes_temporary_cash_hold_exhaustion_and_halt(tmp_path, monkeypatch):
    ledger = ledger_fixture(tmp_path, monkeypatch)
    assert runtime.budget_status()["state"] == "ready"
    monkeypatch.setattr(api, "CAP_NANOYUAN", api.ABSOLUTE_RESERVATION_NANOYUAN)
    reserve(ledger, "one", "v064:slot", "condition")
    waiting = runtime.budget_status()
    assert waiting["state"] == "waiting_inflight_cash" and waiting["temporary_wait"] is True
    ledger.uncertain("one", {"reason": "no provider receipt"})
    stopped = runtime.budget_status()
    assert stopped["state"] == "cash_exhausted" and stopped["temporary_wait"] is False
    with ledger._transaction() as db:
        db.execute("INSERT INTO metadata VALUES ('halted','accounting_fault')")
    assert runtime.budget_status()["state"] == "shared_halted"


def test_usage_preserves_known_withheld_output_and_separate_unknown_cash(tmp_path, monkeypatch):
    ledger = ledger_fixture(tmp_path, monkeypatch)
    row = {"model_key": "DEEPSEEK", "slot_id": "v064:task:condition:1", "condition_id": "condition"}
    reserve(ledger, "known", row["slot_id"], row["condition_id"])
    body = {"id": "known-response", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 32769, "total_tokens": 32869,
                      "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20}}
    with pytest.raises(api.ProviderOutputBoundViolation):
        ledger.settle("known", body)
    reserve(ledger, "unknown", row["slot_id"], row["condition_id"])
    ledger.uncertain("unknown", {"reason": "socket_closed"})
    result = runtime.usage_for_slot(row)
    assert result["usage_capture_complete"] is False
    assert result["calls"][0]["completion_tokens"] == 32769
    assert result["calls"][0]["reasoning_tokens"] is None
    actual_nano = ledger.request_status("known")["settled_nanoyuan"]
    assert Decimal(result["calls"][0]["accounted_cost_cny"]) == Decimal(actual_nano)/api.NANOYUAN
    unknown = result["unresolved_calls"][0]
    assert unknown["reserved_tokens"] == 32868 and unknown["reserved_cost_cny"] == "5.24288"
    assert unknown["reservation_is_actual_usage"] is False


def test_tool_inventory_uses_actual_sdk_function_names(tmp_path, monkeypatch):
    def schema(name):
        return {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
    native = {name: schema(name) for name in ("execute_bash", "str_replace_editor")}
    monkeypatch.setattr(runtime.sdk, "OUTPUT", tmp_path / "sdk")
    (tmp_path / "sdk").mkdir()
    write_new(tmp_path / "sdk/manifest.json", {"adapter": reference(runtime.sdk.__file__),
              "probe": {"interfaces": {model: {"tool_schemas": native} for model in ("QWEN", "DEEPSEEK")}}})
    fixture = tmp_path / "fixture"
    monkeypatch.setattr(runtime, "PROJECT_FIXTURE", fixture)
    fixture.mkdir()
    write_new(fixture / "result.json", {"passed": True, "real_model_calls": 0,
              "actual_single_agent_SDK_runtime": True})
    folder = fixture / "runtime/managed-transport/request-00001"
    folder.mkdir(parents=True)
    write_new(folder / "wire-request.json", {"tools": [schema("read_file"), schema("staff_done")]})
    monkeypatch.setattr(runtime, "SCHEMA_FILE", tmp_path / "schemas.json")
    ref = runtime.prepare_schema_inventory()
    value = json.loads(open(ref["path"]).read())
    assert value["tool_names"]["REF"] == ["execute_bash", "str_replace_editor"]
    assert value["tool_names"]["PROJECT"] == ["read_file", "staff_done"]


def test_runtime_factory_rejects_foreign_slot_condition_tools_and_output_limit(tmp_path, monkeypatch):
    row = {"slot_id": "v064:task:group:1", "condition_id": "group", "model_key": "DEEPSEEK",
           "instance_id": "task", "arm": "PROJECT", "input_plus_output_tokens": 5_000_000}
    value = runtime.DeepSeekRuntime()
    client = SimpleNamespace()
    client.fork_for_episode = lambda: client
    value.client, value.counter = client, lambda _: {}
    value.rows = {row["slot_id"]: row}
    value.schemas = {"tool_names": {"PROJECT": ["read_file", "staff_done"]}}
    monkeypatch.setattr(runtime.policy, "require_v064_allowed", lambda *args, **kwargs: None)
    transport = value.transport_factory(row, tmp_path / "episode")
    payload = {"slot_id": row["slot_id"], "condition": "group", "request_id": row["slot_id"]+":0001",
               "usage_id": "agent", "wire": {"max_tokens": 32768,
                   "tools": [{"type": "function", "function": {"name": name}}
                             for name in ("read_file", "staff_done")]}}
    assert transport.authorize(payload)["token_budget"] == 5_000_000
    for changed in ({"condition": "another"}, {"request_id": row["slot_id"]+":9999"},
                    {"wire": {"max_tokens": 32769}}, {"wire": {"max_tokens": 32768, "tools": []}}):
        with pytest.raises(ValueError):
            transport.authorize({**payload, **changed})
    with pytest.raises(ValueError, match="frozen planned"):
        value.transport_factory({**row, "input_plus_output_tokens": 10_000_000}, tmp_path / "other")
