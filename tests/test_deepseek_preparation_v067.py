import copy

import pytest

from proworksim import software_benchmark_deepseek_runtime_v067 as runtime


def canonical_usage():
    return {"usage_capture_complete": True, "unresolved_calls": [], "calls": [
        {"call_id": "v064:neutral:thinking-tools:r1:1", "purpose": "preparation",
         "prompt_tokens": 340, "completion_tokens": 45, "reasoning_tokens": 0,
         "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 340, "accounted_cost_cny": "0.00052"},
        {"call_id": "v064:neutral:thinking-tools:r1:2", "purpose": "preparation",
         "prompt_tokens": 407, "completion_tokens": 7, "reasoning_tokens": 0,
         "prompt_cache_hit_tokens": 256, "prompt_cache_miss_tokens": 151, "accounted_cost_cny": "0.00018412"}]}


def test_two_explicit_canonical_parts_are_total_without_total_tokens_field():
    usage = canonical_usage()
    assert all("total_tokens" not in call for call in usage["calls"])
    result = runtime.validate_existing_preparation_usage(usage, {"actual_known_input_output_tokens": 799})
    assert result["prompt_tokens"] == 747 and result["completion_tokens"] == 52
    assert result["actual_input_plus_output_tokens"] == 799


@pytest.mark.parametrize("mutation", ["missing_completion", "bool_prompt", "duplicate", "unknown", "wrong_total"])
def test_missing_unknown_and_mismatched_usage_is_not_zero_filled(mutation):
    usage = copy.deepcopy(canonical_usage())
    qualification = {"actual_known_input_output_tokens": 799}
    if mutation == "missing_completion":
        usage["calls"][0].pop("completion_tokens")
    elif mutation == "bool_prompt":
        usage["calls"][0]["prompt_tokens"] = True
    elif mutation == "duplicate":
        usage["calls"][1]["call_id"] = usage["calls"][0]["call_id"]
    elif mutation == "unknown":
        usage["unresolved_calls"] = [{"call_id": "unknown"}]
    elif mutation == "wrong_total":
        qualification["actual_known_input_output_tokens"] = 798
    with pytest.raises(runtime.APIQualificationPending):
        runtime.validate_existing_preparation_usage(usage, qualification)


def test_new_sidecar_guard_is_required_before_any_formal_initialization():
    value = runtime.DeepSeekRuntime()
    with pytest.raises(runtime.APIQualificationPending, match="own explicit scoped guard"):
        value.initialize_for_run()
    assert value.client is None and value.counter is None
    assert runtime.IDENTITY_FILE.is_relative_to(runtime.SIDECAR_ROOT)
    assert runtime.LEDGER == runtime.predecessor.LEDGER


def test_sidecar_guard_failure_precedes_primary_guard_and_client():
    calls = []
    def guard(operation, **identity):
        calls.append((operation, identity))
        raise PermissionError("sidecar not sealed")
    value = runtime.DeepSeekRuntime(scope_guard=guard)
    with pytest.raises(PermissionError, match="not sealed"):
        value.initialize_for_run()
    assert calls == [("v067.api.request", {"slot_id": None, "instance_id": None})]
    assert value.client is None and value.counter is None
