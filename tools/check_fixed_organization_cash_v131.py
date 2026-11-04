"""One real SDK team cash-boundary fixture; no provider, network, or Docker."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    folder = parser.parse_args().output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.environ["OH_PERSISTENCE_DIR"] = str(folder / "sdk-settings")

    def deny(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            raise AssertionError("No network or provider is allowed in the cash CPU control")
        if event == "subprocess.Popen":
            argv = args[1]
            allowed = {"init", "config", "add", "write-tree", "diff", "apply", "ls-files",
                       "read-tree", "hash-object", "cat-file", "update-index"}
            prefix = ["-c", "core.hooksPath=" + os.devnull,
                      "-c", "core.attributesFile=" + os.devnull,
                      "-c", "core.autocrlf=false", "-c", "core.filemode=true"]
            if (not isinstance(argv, (list, tuple)) or Path(argv[0]).name != "git"
                    or list(argv[1:9]) != prefix or len(argv) < 10 or argv[9] not in allowed
                    or "proworksim-v054-candidate-" not in str(args[2])):
                raise AssertionError("Only the existing local candidate codec is allowed")

    sys.addaudithook(deny)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "cash_fixture_v131", root / "tests/test_fixed_organization_v131.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    from proworksim import software_fixed_organization_runtime_v131 as managed
    from proworksim.software_benchmark_alignment_contract_v131 import condition
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_deepseek_contract_v105 import PreDispatchBudgetStopped
    from proworksim.software_benchmark_project_closure_v131 import export_managed_closure
    from proworksim.storage import digest, json_bytes

    prepared, deadline, public_calls = fixtures.fixture(folder / "case", "REVIEW")
    cfg = condition("REVIEW")
    slot = f"v131:fixture__team-1:{cfg['condition_id']}:131"
    requests, rejected = [], []

    def post(route, payload):
        assert payload["team_slot_id"] == slot
        member, wire = payload["member_id"], payload["wire"]
        if route in {"/tokenize", "/tokenize-prefix"}:
            return {"prompt_tokens": 256, "request_sha256": digest(json_bytes(wire)),
                    "method": "scripted CPU count",
                    "count_only_not_dispatchable": route.endswith("prefix")}
        assert route == "/chat/completions" and payload["slot_id"] == slot
        assert wire["tools"] == managed.member_wire_tools("REVIEW", member)
        if requests:
            assert not rejected, "The cash refusal must not be retried"
            rejected.append(copy.deepcopy(payload))
            raise PreDispatchBudgetStopped("group_cash_reservation_insufficient")
        assert member == "member_001"
        requests.append(copy.deepcopy(payload))
        return {"id": "cash-fixture-response-1", "model": "deepseek-flash",
                "object": "chat.completion", "created": 0,
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": None, "tool_calls": [{
                        "id": "cash-fixture-call-1", "type": "function", "function": {
                            "name": "write_file", "arguments": json.dumps({
                                "path": "sample.py", "text": "value = 2\n"})}}]}}],
                "usage": {"prompt_tokens": 256, "completion_tokens": 25,
                          "total_tokens": 281, "prompt_cache_hit_tokens": 0,
                          "prompt_cache_miss_tokens": 256}}

    owner = managed.build_team_owner(post, organization_id="REVIEW", slot_id=slot,
        condition_id=cfg["condition_id"], folder=folder / "model-ledger", deadline=deadline,
        identity={"policy_version": "scripted-cash-CPU-only"})
    runtime, _, _ = managed.build_runtime(owner, prepared, folder / "runtime", deadline=deadline,
        public_initial_message="Synthetic CPU fixture; no external service or benchmark.")
    try:
        boundary = managed.run_fragment(prepared, runtime)
        ledger = owner.save()
        write_new(folder / "boundary.json", boundary)
        write_new(folder / "ledger-snapshot.json", ledger)
        write_new(folder / "requests.json", {"scripted_responses": requests,
                                            "before_dispatch_refusals": rejected})
        assert len(requests) == len(rejected) == 1
        assert boundary["cash_censored"] is True
        assert boundary["closure_reason"] == "cash_budget_exhausted_before_dispatch", boundary
        assert boundary["execution_integrity_failure"] is None, boundary
        assert boundary["status"] == "bounded_work_closed"
        assert ledger["complete_actual_tokens"] == ledger["known_actual_tokens"] == 281
        assert ledger["attempts"] == ledger["decisions"] == len(ledger["calls"]) == 1
        assert ledger["inflight"] is None and ledger["uncertain_reserved_tokens"] == 0
        assert ledger["cash_censored"] is True
        assert runtime.team_budget.snapshot()["charged_tokens"] == 281
        assert sum(worker.meter["budget_accounted_tokens"]
                   for worker in runtime.policies.values()) == 281
        assert len(owner.cash_boundaries) == len(owner.pre_dispatch_boundaries) == 1
        assert owner.cash_boundaries[0]["new_provider_request_started"] is False
        assert public_calls == [] and prepared.world._software()["deliveries"] == []
    finally:
        managed.close_runtime(runtime)
    closure = export_managed_closure(prepared, folder / "closure", slot_id=slot, sdk_closed=True)
    assert closure["terminal_bundle"]["files"]["sample.py"] == "value = 2\n"
    evidence = json.loads(checked(closure["delivery_evidence"]).read_bytes())
    assert evidence["designated_delivery_member"] == "member_001"
    assert closure["submitted"] is False
    closure.pop("terminal_bundle")
    result = {"passed": True, "version": "v131-real-sdk-cash-before-dispatch-control-r1",
        "scripted_provider_responses": 1, "scripted_tokens": 281,
        "cash_refusals_before_dispatch": 1, "new_provider_calls_after_refusal": 0,
        "real_model_calls": 0, "real_model_tokens": 0, "API_calls": 0,
        "Docker_operations": 0, "public_test_calls": 0, "automatic_retry": False,
        "unknown_usage_reservations": 0, "aggregate_ledger_complete": True,
        "team_cash_censored_not_technical_unknown": True,
        "existing_member001_tree_locked": True, "automatic_submission": False,
        "closure": closure, "boundary": reference(folder / "boundary.json"),
        "ledger": reference(folder / "ledger-snapshot.json"),
        "requests": reference(folder / "requests.json"),
        "sources": [reference(managed.__file__), reference(
            root / "src/proworksim/software_benchmark_project_closure_v131.py"),
            reference(Path(__file__))]}
    print(json.dumps(write_new(folder / "summary.json", result), ensure_ascii=False))


if __name__ == "__main__":
    main()
