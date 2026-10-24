"""A repaired factory must not authorize replay or mix its slots with v056."""
import copy

import pytest

from proworksim import software_benchmark_execution_binding_v057 as binding
from proworksim import software_benchmark_runner_v057 as runner
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def config_for(tmp_path):
    policy = write_new(tmp_path / "policy.json", {
        **binding.POLICY_FIELDS,
        "sources": [reference(binding.ROOT / name) for name in binding.REQUIRED_SOURCES],
    })
    slot = {"slot_id": "v057:synthetic-ref-repaired", "instance_id": "synthetic-task",
            "condition_id": "REF_B5000K", "execution_group": "REF_REPAIRED_V057",
            "arm": "REF", "seed": 20261024057001, "input_plus_output_tokens": 5000000}
    slots = write_new(tmp_path / "slots.json", {"version": "v057-ref-repaired-slots-r1", "slots": [slot]})
    auth = write_new(tmp_path / "authorization.json", {
        "version": "v057-ref-repaired-authorization-r1", "execution_authorized": True,
        "slots_sha256": slots["sha256"], "slot_ids": [slot["slot_id"]],
    })
    return {"execution_policy": policy, "execution_group": "REF_REPAIRED_V057",
        "slot_id": slot["slot_id"], "condition_id": slot["condition_id"],
        "slots": slots, "authorization": auth, "public_task": {"instance_id": slot["instance_id"]}}, slot


def test_new_slots_are_explicitly_separate_and_old_namespace_is_rejected(tmp_path):
    config, slot = config_for(tmp_path)
    assert runner.planned_slot(config) == slot
    with pytest.raises(ValueError, match="fresh v057"):
        runner.planned_slot(config | {"slot_id": "v056:synthetic-ref-repaired"})
    with pytest.raises(ValueError, match="fresh v057"):
        runner.planned_slot(config | {"execution_group": "REF"})


def test_budget_or_seed_cannot_be_replaced_under_same_authorization(tmp_path):
    config, _ = config_for(tmp_path)
    with pytest.raises(ValueError, match="predeclared"):
        runner.planned_slot(config | {"condition_id": "REF_B10000K"})
    with pytest.raises(ValueError, match="predeclared"):
        runner.planned_slot(config | {"seed": 99})


def test_policy_rejects_unbounded_recovery_and_incomplete_source_seal(tmp_path):
    config, _ = config_for(tmp_path)
    import json
    policy = json.loads(binding.checked(config["execution_policy"]).read_bytes())
    altered = copy.deepcopy(policy)
    altered["maximum_stuck_corrections"] = 100
    ref = write_new(tmp_path / "unbounded.json", altered)
    with pytest.raises(ValueError, match="Unexpected"):
        binding.validate_execution_policy(ref)
    altered = copy.deepcopy(policy)
    altered["sources"].pop()
    ref = write_new(tmp_path / "unsealed.json", altered)
    with pytest.raises(ValueError, match="complete versioned source seal"):
        binding.validate_execution_policy(ref)
