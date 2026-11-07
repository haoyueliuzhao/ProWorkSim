"""Actual episode/config/controller identity chain, without API or Docker."""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_alignment_contract_v146 as alignment
from proworksim import software_benchmark_episode_v146 as episode
from proworksim import software_benchmark_runtime_inputs_v146 as inputs
from proworksim import software_benchmark_sdk_bundle_v146 as bundle
from proworksim import software_benchmark_scope_v146 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION
from test_public_runtime_bindings_v141 import prepared

ROOT = Path(__file__).resolve().parents[1]


def actual_controller():
    path = ROOT / "tools/run_role_baseline_controller_v146.py"
    spec = importlib.util.spec_from_file_location("v146_actual_controller_cpu", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize("group", ["FREE2", "REVIEW2"])
@pytest.mark.parametrize("attempt", [1, 2])
def test_real_controller_accepts_new_id_keeps_seed_role_and_rejects_old_invalid_attempt(
    tmp_path, group, attempt
):
    row, public, entry, base, _, ready, host = prepared(tmp_path, group)
    old_slot = row["slot_id"]
    row = {
        **row,
        "slot_id": f"v146:{old_slot}:attempt{attempt}",
        "original_slot_id": old_slot,
        "recovery_round": attempt,
        "recovery_attempt": attempt,
    }
    host = {**host, "slot_id": row["slot_id"]}
    actor = inputs.actor_inputs(base, public_test_entry=entry, row=row)
    context = {
        "version": CONTEXT_VERSION,
        "instance_id": row["instance_id"],
        "visible_text": "Public context",
        "visible_facts": {"cwd": "/testbed"},
    }
    result = bundle.controller_inputs(
        host,
        row,
        ready,
        {"thinking": False, "model": "deepseek-flash"},
        "http://127.0.0.1:18219",
        public_context=context,
        public_environment=public,
        public_test_entry=entry,
        actor_config=actor["config"],
    )
    config = json.loads(result["controller-config.json"])
    controller = actual_controller()
    assert controller.validate_config(config) == config
    assert controller.validate_ready(config, ready) == ready
    assert config["slot_id"] == row["slot_id"] and config["seed"] == row["seed"] == 141
    assert config["condition_id"] == row["condition_id"]
    assert config["organization_id"] == group and config["fixed_members"] == row["fixed_members"]
    assert config["execution_alignment"] == alignment.shared_strategy(group)
    assert config["configuration"]["path"] == "/pws/control/condition.json"
    assert inputs.controller_inputs is bundle.controller_inputs
    for changed in (
        {**config, "slot_id": old_slot},
        {**config, "slot_id": f"v146:{old_slot}:attempt3"},
        {**config, "seed": 142},
        {**config, "fixed_members": ["member_001"]},
        {**config, "version": "v142-role-baseline-controller-r1"},
    ):
        with pytest.raises(ValueError):
            controller.validate_config(changed)


def test_actual_episode_builder_and_row_config_bind_new_scope_bundle_and_plan():
    plan = scope.load(reference(scope.PLAN_FILE))
    guards = []

    def guard(operation, **identity):
        guards.append((operation, identity))
        return {
            "status": "approved",
            "execution_alignment_version": alignment.VERSION,
            "source_index": {"CPU_only": True},
            "plan": reference(scope.PLAN_FILE),
        }

    value = episode.build_episode(scope=scope, guard=guard)
    assert value.runtime is bundle
    assert value._run.__globals__["runtime"] is bundle
    assert value._run.__globals__["BATCH"] == scope.BATCH_ROOT
    assert value.run_episode.__globals__["_run"] is value._run
    assert value.allowed_organization_ids == ("FREE2", "REVIEW2")
    assert value.new_system_parent_slice is False
    assert (
        bundle.actor_inputs is inputs.actor_inputs
        and bundle.controller_inputs is inputs.controller_inputs
    )
    imports = [
        node.module
        for node in ast.walk(value.memory_transformed_ast)
        if isinstance(node, ast.ImportFrom)
    ]
    assert "software_benchmark_project_closure_v141" in imports
    for group in ("FREE2", "REVIEW2"):
        for attempt in (1, 2):
            row = next(
                r
                for r in plan["rows"]
                if r["organization_id"] == group and r["recovery_round"] == attempt
            )
            host, condition, limits = value._row_and_config(row, False)
            assert host["slot_id"] == row["slot_id"] and host["slot_index"] == row["slot_index"]
            assert host["seed"] == row["seed"] and host["source_slot_id"] == row["source_slot_id"]
            assert condition["condition_id"] == row["condition_id"]
            assert (
                limits["input_plus_output_tokens"]
                == row["generation_token_upper_bound"]
                == 5_000_000
            )
            assert "/software-benchmark-v146/" in row["configuration"]["path"]
            old = copy.deepcopy(row)
            old["slot_id"] = row["original_slot_id"]
            with pytest.raises(ValueError):
                value._row_and_config(old, False)
            changed = {**row, "recovery_attempt": 3}
            with pytest.raises(ValueError):
                value._row_and_config(changed, False)
    assert guards[0][0] == "v066.run"
    assert not any(op not in {"v066.run"} for op, _ in guards)
