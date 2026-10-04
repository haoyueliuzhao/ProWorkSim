import copy

import pytest

from proworksim.candidate_runtime_v030 import candidate_profile as loading_profile
from proworksim.candidate_runtime_v031 import bind_profile, candidate_profile


@pytest.mark.parametrize("candidate", ["swe-next-14b", "devstral-small-2507"])
def test_final_binding_preserves_loading_facts_and_numerical_gates(candidate):
    original = {**loading_profile(candidate), "actual_lora_modules": ["layer.q_proj"],
                "actual_parameter_storage": {"frozen": "bfloat16"}, "torch": "measured-version"}
    before = copy.deepcopy(original)
    bound = bind_profile(original)
    declared = candidate_profile(candidate)
    assert all(bound[key] == value for key, value in declared.items())
    assert bound["actual_parameter_storage"] == original["actual_parameter_storage"]
    assert bound["actual_lora_modules"] == original["actual_lora_modules"]
    assert bound["torch"] == "measured-version" and original == before
    assert (bound["max_context_tokens"], bound["max_output_tokens"]) == (16384, 2048)
    assert (bound["logprob_max_atol"], bound["logprob_mean_atol"]) == (0.02, 0.002)
    assert bound["learning_execution"]["past_state_detach"] is False
    assert bound["learning_execution"]["sampling_path_changed"] is False


def test_binding_rejects_changed_original_loader_contract():
    original = loading_profile("swe-next-14b")
    original["temperature"] = 0.9
    with pytest.raises(ValueError, match="loader differs"):
        bind_profile(original)
