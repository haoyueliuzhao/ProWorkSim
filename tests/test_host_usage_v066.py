import copy
import json

import pytest

from proworksim import software_benchmark_host_usage_v066 as host
from proworksim.software_benchmark_full_plan_v064 import group_profiles
from proworksim.software_benchmark_ref_budget_v064 import PairedQwenAdapter
from proworksim.software_benchmark_match_v054 import AccountingFault


def condition(arm="REF"):
    group = group_profiles()[f"QWEN_{arm}_B5000K"]
    return {**group, "version": "v064-full-comparison-condition-r1", "single_agent": True,
        "thinking": True, "training": False, "inference": {**group["inference"], "automatic_retries": 0,
            "temperature": .6, "top_p": .95, "top_k": 20, "min_p": 0., "presence_penalty": 0.,
            "repetition_penalty": 1., "chat_template_kwargs": {"enable_thinking": True}}}


IDENTITY = {"model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "vllm_version": "0.32.0",
    "raw_release": True, "adapter_sha256": None,
    "model_manifest_sha256": "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6",
    "context_limit": 131072, "max_output_tokens": 32768, "port": 18210,
    "service_admission_complete": True, "deployment_version": "v064-owned-user-ref-resident-r1",
    "host_runtime_revision": "v066-owned-resident-fixture"}


class Wire:
    port, timeout_seconds = 18210, 1800

    def __init__(self):
        self.generations, self.count, self.output = 0, 10, 7
        self.folder, self.fail, self.invalid_usage = None, False, False
        self.before_post = []

    def post(self, path, payload):
        if path == "/tokenize":
            return {"tokens": list(range(self.count)), "count": self.count, "max_model_len": 131072}
        self.generations += 1
        # Inspect the independent on-disk journal from inside the fake forward:
        # the reservation must already survive without controller state.
        state = host.read_host_ledger(self.folder)
        assert state["attempts"] == self.generations
        assert state["uncertain_reserved_tokens"] == self.count + 32768
        self.before_post.append(state)
        if self.fail:
            raise host.HTTPFailure("scripted missing reply after possible dispatch")
        output = 32769 if self.invalid_usage else self.output
        return {"id": f"reply-{self.generations}", "model": host.REF_MODEL,
            "usage": {"prompt_tokens": self.count, "completion_tokens": output,
                      "total_tokens": self.count + output},
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "fixture"}}]}


def setup(tmp_path, arm="REF"):
    spec = condition(arm)
    slot = f"v064:fixture:{spec['condition_id']}:1"
    wire = Wire()
    broker = host.HostUsageTransport(wire, tmp_path / "host", slot, condition=spec, service_identity=IDENTITY)
    wire.folder = broker.folder
    adapter = PairedQwenAdapter(transport=broker, folder=tmp_path / "controller", slot_id=slot, seed=1,
                               service_identity=IDENTITY, condition=spec, allowed_tools={"fixture"})
    return wire, broker, adapter


def request(adapter, text="fixture"):
    return adapter.request([{"role": "user", "content": text}],
        [{"type": "function", "function": {"name": "fixture", "parameters": {"type": "object"}}}])


@pytest.mark.parametrize("arm", ["REF", "PROJECT"])
def test_durable_intent_before_forward_and_usage_before_reply(tmp_path, arm):
    wire, broker, adapter = setup(tmp_path, arm)
    answer = adapter.complete(request(adapter), "agent")
    saved = json.loads((broker.folder / "0001.json").read_bytes())
    assert saved["before_controller_forward"] and saved["usage"] == answer["usage"]
    assert wire.before_post[0]["complete_actual_tokens"] is None
    assert broker.snapshot()["complete_actual_tokens"] == 17
    result = {"ledger": adapter.ledger.snapshot()}
    host.reconcile_host_usage(result, broker.snapshot())
    assert result["model_calls"] == 1 and result["known_actual_tokens"] == 17


def test_lost_response_stays_bounded_and_other_slot_is_independent(tmp_path):
    wire, broker, adapter = setup(tmp_path / "lost")
    wire.fail = True
    with pytest.raises(AccountingFault):
        adapter.complete(request(adapter), "agent")
    snapshot = host.read_host_ledger(broker.folder)
    assert snapshot["complete_actual_tokens"] is None and snapshot["known_actual_tokens"] == 0
    assert snapshot["uncertain_reserved_tokens"] == 32778
    with pytest.raises(host.HTTPFailure):
        broker.post("/v1/chat/completions", request(adapter))
    assert wire.generations == 1
    other_wire, other, other_adapter = setup(tmp_path / "independent")
    other_adapter.complete(request(other_adapter), "agent")
    assert other_wire.generations == 1 and other.snapshot()["complete_actual_tokens"] == 17


def test_host_response_recovers_controller_unknown_without_inventing_zero(tmp_path):
    _, broker, adapter = setup(tmp_path)
    adapter.complete(request(adapter), "agent")
    stale = copy.deepcopy(broker.delegate.before_post[0])
    result = {"ledger": stale}
    host.reconcile_host_usage(result, broker.snapshot())
    assert result["host_accounting_recovered"] and result["known_actual_tokens"] == 17
    assert result["ledger"]["uncertain_reserved_tokens"] == 0
    assert result["controller_ledger_before_host_reconciliation"]["uncertain_reserved_tokens"] == 32778


def test_empty_host_journal_does_not_erase_an_entered_intent_without_stronger_proof(tmp_path):
    _, broker, adapter = setup(tmp_path)
    adapter.count(request(adapter))  # Count-only RPC is not a literal zero-RPC channel.
    result = {"model_calls": None, "model_dispatch_started": True}
    host.reconcile_host_usage(result, broker.snapshot())
    assert result["ledger"]["complete_actual_tokens"] == 0
    assert result["host_possible_forwarded_attempts"] == 0
    assert result["model_calls"] == 0 and result["model_dispatch_started"] is True
    assert result["original_model_dispatch_started_before_host_reconciliation"] is True
    assert result["zero_model_generation_proven"] is False


def test_reconciliation_preserves_original_unsent_controller_decision_count(tmp_path):
    _, broker, adapter = setup(tmp_path)
    adapter.complete(request(adapter), "agent")
    original = adapter.ledger.snapshot()
    original["decisions"] += 1  # A later controller budget boundary consumed a decision but sent no call.
    result = {"ledger": original}
    host.reconcile_host_usage(result, broker.snapshot())
    assert result["ledger"]["attempts"] == 1 and result["ledger"]["decisions"] == 2
    assert result["ledger"]["known_actual_tokens"] == 17


def test_response_persistence_failure_retains_original_possible_dispatch(tmp_path, monkeypatch):
    wire, broker, adapter = setup(tmp_path)
    save = host._durable_new
    def fail_settlement(path, body):
        if path.parent == broker.folder and path.name == "0001.json":
            raise OSError("scripted settlement disk error")
        return save(path, body)
    monkeypatch.setattr(host, "_durable_new", fail_settlement)
    with pytest.raises(AccountingFault):
        adapter.complete(request(adapter), "agent")
    assert wire.generations == 1
    recovered = host.read_host_ledger(broker.folder)
    assert recovered["complete_actual_tokens"] is None and recovered["uncertain_reserved_tokens"] == 32778
    assert recovered["known_actual_tokens"] == 0


def test_missing_count_prevents_forward_and_bad_actual_usage_is_integrity_fault(tmp_path):
    wire, broker, adapter = setup(tmp_path)
    with pytest.raises(host.HTTPFailure):
        broker.post("/v1/chat/completions", request(adapter))
    assert wire.generations == 0 and broker.snapshot()["attempts"] == 0
    wire.invalid_usage = True
    with pytest.raises(AccountingFault):
        adapter.complete(request(adapter), "agent")
    with pytest.raises(host.HostUsageIntegrityError):
        broker.snapshot()
    assert (broker.folder / "dispatches/0001.json").is_file()


def test_journal_tampering_and_complete_controller_disagreement_are_rejected(tmp_path):
    _, broker, adapter = setup(tmp_path)
    adapter.complete(request(adapter), "agent")
    bad = adapter.ledger.snapshot()
    bad["known_actual_tokens"] += 1
    with pytest.raises(host.HostUsageIntegrityError):
        host.reconcile_host_usage({"ledger": bad}, broker.snapshot())
    receipt = broker.folder / "dispatches/0001.json"
    value = json.loads(receipt.read_bytes())
    value["reservation"] += 1
    receipt.write_text(json.dumps(value))
    with pytest.raises(host.HostUsageIntegrityError):
        host.read_host_ledger(broker.folder)


def quiet_proofs():
    result = {"slot_id": "v064:fixture:QWEN_PROJECT_B7500K:1", "model_calls": None,
              "model_dispatch_started": True, "model_bridge_thread_finished": True}
    bridge = {"version": host.WIRE_VERSION, "ready": True, "status": "channel_closed",
        "requests": 0, "failed_requests": 0, "count_requests": 0,
        "generation_requests": 0, "predispatch_admission_replies": 0}
    writers = {"all_quiet": True, "errors": [], "create_result_unknown_roles": [],
        "writers": [{"role": role, "state": {"Running": False, "Pid": 0, "OOMKilled": role == "controller"}}
                    for role in ("actor", "controller")]}
    cleanup = {"quiescent": True, "cleanup_errors": [], "create_result_unknown": False}
    return result, bridge, writers, cleanup


def test_zero_rpc_oom_recovery_requires_finished_bridge_and_complete_quiescence():
    result, bridge, writers, cleanup = quiet_proofs()
    original = copy.deepcopy(result)
    proof = host.zero_request_recovery(result, bridge=bridge, writers=writers, cleanup=cleanup)
    assert proof["proved_no_model_RPC"] and proof["prior_model_dispatch_started"] is True
    assert result == original  # The caller preserves the original entered/intent record.
    for kind in ("count", "generation", "thread", "writer", "cleanup", "missing_proof"):
        r, b, w, c = quiet_proofs()
        if kind == "count":
            b["count_requests"] = 1
        elif kind == "generation":
            b["generation_requests"] = 1
        elif kind == "thread":
            r["model_bridge_thread_finished"] = False
        elif kind == "writer":
            w["writers"][0]["state"]["Pid"] = 234
        elif kind == "cleanup":
            c["create_result_unknown"] = True
        else:
            del w["errors"]
        assert host.zero_request_recovery(r, bridge=b, writers=w, cleanup=c) is None


def test_exact_reservation_does_not_add_a_full_context_budget_gate(tmp_path):
    wire, broker, adapter = setup(tmp_path)
    wire.count, wire.output = 98304, 32768
    large = request(adapter, "large")
    for _ in range(37):
        adapter.complete(large, "agent")
    wire.count = 11000
    adapter.complete(request(adapter, "medium"), "agent")
    remaining = broker.manifest["token_limit"] - broker.snapshot()["known_actual_tokens"]
    assert 32778 < remaining < 131072
    wire.count, wire.output = 10, 7
    adapter.complete(request(adapter, "small"), "agent")
    assert broker.snapshot()["complete_actual_tokens"] == adapter.ledger.actual
    assert wire.generations == 39
