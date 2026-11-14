"""Read-only completed-gold validation and narrow recovery namespace controls."""
import json
import pytest
from proworksim import software_benchmark_requests_recovery_v203_2_3_r3 as recovery
from proworksim import software_benchmark_grading_v203_2_3_r3 as grading
from proworksim.software_benchmark_candidates_v054 import reference


def config():
    scope=recovery.formal_scope
    plan=scope.load(reference(scope.PLAN_FILE))
    return scope.load(plan['environments'][recovery.TASK]['configuration'])


def test_component_transform_changes_no_original_per_control_rule():
    for prefix in ('control-r2-','control-r3-'):
        source=recovery.component_source(prefix)
        assert 'len(value.get("controls", [])) != 1' in source
        assert 'validate_transport_evidence(receipt, quiet, observed, identity, folder)' in source
        assert 'receipt.get("status") != "official_report"' in source
    with pytest.raises(ValueError):recovery.component_source('arbitrary-')


def test_actual_completed_r2_gold_passes_full_unchanged_component_body(tmp_path):
    path=tmp_path/'gold.json'
    path.write_text(json.dumps(recovery.component_document('gold')))
    result=recovery.validate_component('gold',reference(path),config())
    assert result['controls'][0]['patch_kind']=='gold'
    altered=json.loads(path.read_text());altered['controls'][0]['patch_kind']='empty'
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError):recovery.validate_component('gold',reference(path),config())


def test_new_empty_namespace_keeps_same_environment_and_one_control_only():
    policy=grading.scope.dispatch_view()
    plan=grading.scope.validate_plan(grading.scope.load(reference(grading.scope.PLAN_FILE)))
    assert set(plan['resources'])=={'control-r3-psf__requests-1766-empty'}
    value=grading.scorer(policy)
    assert value.environment.TLS_TASKS=={'psf__requests-1766'}
    assert grading.environment_adapter.RESOLUTION==recovery.environment.RESOLUTION
    assert value.validate_request.__globals__['MAX_GRADERS']==1
