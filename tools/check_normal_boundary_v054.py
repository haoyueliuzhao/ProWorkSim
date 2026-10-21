"""Small synthetic normal-budget closure control; no model, GPU, real task or SDK replay."""
from contextlib import nullcontext
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_exact_transport_v054 import RefLedger
from proworksim.software_benchmark_match_v054 import AccountingFault, DispatchStopped, EpisodeLedger
from proworksim.software_benchmark_normal_boundary_v054 import (
    FormalOwnerService, NormalEpisodeBoundary, known_boundary, unwrap_normal_boundary,
)
from proworksim.software_benchmark_owner_ipc_v054 import VERSION
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-wrapper-only", action="store_true")
    args = parser.parse_args()
    if args.official_wrapper_only:
        from openhands.sdk.conversation.exceptions import ConversationRunError
        import uuid
        output = ROOT / "runs/software-benchmark-v054/normal-boundary-control-r2"
        output.mkdir(parents=True, exist_ok=False)
        boundary = NormalEpisodeBoundary("all_model_attempt_limit")
        assert unwrap_normal_boundary(boundary) is boundary
        wrapped = ConversationRunError(uuid.uuid4(), boundary)
        wrapped.__cause__ = boundary
        assert unwrap_normal_boundary(wrapped) is boundary
        wrapped.__cause__ = None
        assert unwrap_normal_boundary(wrapped) is None
        fault = AccountingFault("all_model_attempt_limit")
        wrapped = ConversationRunError(uuid.uuid4(), fault)
        wrapped.__cause__ = fault
        assert unwrap_normal_boundary(wrapped) is None
        assert unwrap_normal_boundary(RuntimeError("all_model_attempt_limit")) is None
        receipt = write_new(output / "receipt.json", {
            "status": "passed", "scope": "actual installed SDK exception type; no Conversation/model/GPU run",
            "checks": ["direct_exact_boundary", "official_wrapper_exact_direct_cause",
                "missing_cause_rejected", "accounting_fault_not_reclassified", "text_matching_rejected"],
            "actual_model_calls": 0, "GPU_loads": 0, "formal_slots_claimed": 0,
            "prior_ledger_control": reference(ROOT / "runs/software-benchmark-v054/normal-boundary-control-r1/receipt.json"),
            "sources": [reference(ROOT / "src/proworksim/software_benchmark_normal_boundary_v054.py"), reference(__file__)]})
        print(json.dumps(receipt))
        return
    output = ROOT / "runs/software-benchmark-v054/normal-boundary-control-r1"
    output.mkdir(parents=True, exist_ok=False)
    match = EpisodeLedger(identity={})
    match.attempts = 128
    bridge = SimpleNamespace(ledger=match)
    def complete_request(*_, **kwargs):
        return match.admit({"fits": True, "prompt_tokens": 1}, kwargs["usage_id"])
    bridge.complete_request = complete_request
    service = object.__new__(FormalOwnerService)
    service.identity, service.sequences = {}, {}
    service.entered, service.closed, service.bridge = True, False, bridge
    service.root, service.snapshot = output, {}
    service.generation_context = nullcontext
    calls = []
    service.owner = SimpleNamespace(
        finish_evaluation=lambda *_: calls.append("finish_evaluation"),
        finish_evaluation_guard=lambda *_: {"learning_unchanged": True, "rng_restored_exactly": True})
    common = {"version": VERSION, "identity_sha256": digest(json_bytes({})), "session": "synthetic"}
    result = service.dispatch({**common, "sequence": 1, "operation": "match_complete",
                               "arguments": {"request": {}, "usage_id": "agent"}})
    assert result["terminal_boundary"]["reason"] == "all_model_attempt_limit"
    assert not service.closed and match.attempts == 128
    finished = service.dispatch({**common, "sequence": 2, "operation": "finish", "arguments": {}})
    assert calls == ["finish_evaluation"] and finished["guard"]["rng_restored_exactly"]
    ref = RefLedger()
    ref.actual = 499999
    try:
        ref.reserve({"prompt_tokens": 1}, "condenser", {})
        raise AssertionError("Insufficient full reservation was accepted")
    except DispatchStopped as error:
        assert known_boundary(error, ref.snapshot())["reason"] == "full_input_and_output_reservation_insufficient"
    assert known_boundary(AccountingFault("all_model_attempt_limit"), ref.snapshot()) is None
    unknown = {**ref.snapshot(), "inflight": {"reservation": 32769}, "complete_actual_tokens": None}
    assert known_boundary(DispatchStopped("all_model_attempt_limit"), unknown) is None
    assert known_boundary(DispatchStopped("formal_model_execution_not_authorized"), ref.snapshot()) is None
    receipt = write_new(output / "receipt.json", {
        "status": "passed", "checks": ["actual_MATCH_ledger_attempt_cap_preserved",
            "normal_RPC_boundary_keeps_original_finish_guard_available",
            "REF_condenser_full_reservation_boundary", "accounting_fault_and_unknown_usage_not_reclassified",
            "authorization_fault_not_reclassified"], "actual_model_calls": 0, "GPU_loads": 0,
        "formal_slots_claimed": 0, "scope": "real ledgers and service dispatch with explicit synthetic owner guard",
        "sources": [reference(ROOT / "src/proworksim/software_benchmark_normal_boundary_v054.py"), reference(__file__)]})
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
