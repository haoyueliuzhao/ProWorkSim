"""Changed-source and missing-route counterexamples for qualification reuse."""
import copy

import pytest

from proworksim.storage import atomic_write, json_bytes
from scripts import software_organization_admission_v047 as admission
from scripts.software_organization_admission_v044 import EvidenceReader
from scripts.software_organization_v047 import assignments
from scripts.run_ne_v021 import reference


def control_fixture(tmp_path):
    sources = {"src/proworksim/new_v047.py": "source-hash-fixture"}
    path = tmp_path / "tokenizer.json"
    units = [u for seq in assignments().values() for u in seq]
    tokenizer = {"passed": True, "model_weights_loaded": False, "new_model_calls": 0,
        "context_limit": 18432, "reserved_output_tokens": 2048, "source_files": sources,
        "source_unchanged_during_routes": True, "required_routes": 44,
        "routes": [{"route_id": u["slot_id"], "passed": True, "min_selected_headroom": 100,
                    "prepared_requests": 2, "programmed_responses": 2} for u in units]}
    atomic_write(path, json_bytes(tokenizer))
    value = {"version": "software-organization-qualification-v0.47", "passed": True,
        "source_files": sources, "new_model_calls": 0, "new_backward_calls": 0,
        "model_weights_loaded": False, "source_unchanged_during_controls": True,
        "controls": {key: {"passed": True} for key in admission.REQUIRED_CONTROLS},
        "ruff": {"returncode": 0}, "pytest": {"tests": 1},
        "artifact_refs": [reference(path)], "initial_tokenizer_control": reference(path)}
    return value, tokenizer, path, sources


def test_only_new_isolated_code_can_reuse_old_numerics():
    old = {"src/proworksim/native.py": "unchanged"}
    current = {**old, "src/proworksim/new_v047.py": "new"}
    receipt = admission.source_reuse(old, current)
    assert receipt["historical_files_unchanged"] and receipt["new_source_files"] == 1
    with pytest.raises(ValueError):
        admission.source_reuse(old, {**current, "src/proworksim/native.py": "changed"})
    with pytest.raises(ValueError):
        admission.source_reuse(old, {**current, "src/quiet_numeric_fix.py": "extra"})


def test_complete_cpu_inventory_is_source_bound(tmp_path):
    value, _, _, sources = control_fixture(tmp_path)
    assert admission.validate_cpu(value, sources, EvidenceReader())["passed"]
    with pytest.raises(ValueError):
        admission.validate_cpu(value, {**sources, "extra": "changed"}, EvidenceReader())


@pytest.mark.parametrize("mutation", ["missing_route", "duplicate_route", "negative_headroom", "new_model", "changed_source"])
def test_incomplete_or_changed_materials_cannot_pass(tmp_path, mutation):
    value, tokenizer, path, sources = control_fixture(tmp_path)
    if mutation == "missing_route":
        tokenizer["routes"].pop()
    elif mutation == "duplicate_route":
        tokenizer["routes"][-1] = copy.deepcopy(tokenizer["routes"][0])
    elif mutation == "negative_headroom":
        tokenizer["routes"][0]["min_selected_headroom"] = -1
    elif mutation == "new_model":
        tokenizer["new_model_calls"] = 1
    else:
        tokenizer["source_files"] = {}
    atomic_write(path, json_bytes(tokenizer))
    value["initial_tokenizer_control"] = reference(path)
    value["artifact_refs"] = [reference(path)]
    with pytest.raises(ValueError):
        admission.validate_cpu(value, sources, EvidenceReader())


def test_missing_closure_control_does_not_pass(tmp_path):
    value, _, _, sources = control_fixture(tmp_path)
    value["controls"].pop("deadline_dispatch_cancellation_and_inflight_close")
    with pytest.raises(ValueError):
        admission.validate_cpu(value, sources, EvidenceReader())


def test_material_reuse_allows_only_explicit_cpu_helper_changes():
    old = {"src/proworksim/software_organization_v047.py": "world",
           "src/proworksim/software_organization_runtime_v047.py": "runtime",
           "scripts/software_organization_qualification_v047.py": "old_fixture"}
    revised = {**old, "scripts/software_organization_qualification_v047.py": "new_fixture"}
    assert admission.validate_material_source_reuse(old, revised)["production_sources_unchanged"]
    for name in ("src/proworksim/software_organization_v047.py", "src/proworksim/software_organization_runtime_v047.py"):
        with pytest.raises(ValueError, match="production/numerical"):
            admission.validate_material_source_reuse(old, {**revised, name: "different"})
    with pytest.raises(ValueError, match="inventory"):
        admission.validate_material_source_reuse(old, {**revised, "src/proworksim/hidden_v047.py": "extra"})
