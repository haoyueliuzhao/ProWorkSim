"""Real tiny-world closure plus production controller and bundle source bindings."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_project_closure_v141 as closure
from proworksim import software_benchmark_sdk_bundle_v141 as bundle
from proworksim import software_benchmark_content_tokenizer_v141 as tokenizer
from proworksim.software_benchmark_alignment_contract_v141 import condition
from proworksim.software_benchmark_candidates_v054 import checked

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fixture = module('v141_closure_world_fixture', ROOT/'tests/test_role_baseline_world_v141.py')
controller = module('v141_actual_controller_binding', ROOT/'tools/run_role_baseline_controller_v141.py')


@pytest.mark.parametrize('group', ['S1', 'FREE2', 'REVIEW2'])
def test_actual_world_dual_endpoint_and_historical_review(tmp_path, group):
    prepared, _, call, _ = fixture.prepare(tmp_path/'world', group)
    def act(member, tool, **args):
        return fixture.accepted(call, member, tool, **args)
    act('member_001', 'write_file', path='sample.py', text='value = 2\n')
    act('member_001', 'run_tests')
    patch = act('member_001', 'fix_patch', task_ids=[], message='Exact final candidate')
    if group == 'REVIEW2':
        act('member_002', 'integrate_patch', patch_id=patch['patch_id'])
        act('member_002', 'run_tests')
        act('member_002', 'org_review_patch', patch_id=patch['patch_id'], decision='accept', reason='Verified this adopted version')
    act('member_001', 'submit_integration', message='Explicit legal delivery')
    if group == 'REVIEW2':
        act('member_002', 'org_review_patch', patch_id=patch['patch_id'], decision='request_changes', reason='Later concern cannot erase historical delivery')
    act('member_001', 'write_file', path='sample.py', text='value = 3\n')
    slot = f"v142:{prepared.case['case_id']}:{condition(group)['condition_id']}:141"
    result = closure.export_managed_closure(prepared, tmp_path/'closed', slot_id=slot, sdk_closed=True)
    assert result['submitted'] and result['same_tree'] is False
    assert result['terminal_bundle']['files']['sample.py'] == 'value = 3\n'
    evidence = json.loads(checked(result['delivery_evidence']).read_bytes())
    snapshot = json.loads(checked(result['delivery_snapshot']).read_bytes())
    baseline = json.loads(checked(result['baseline_snapshot']).read_bytes())
    assert snapshot['candidate']['files']['sample.py'] == 'value = 2\n'
    assert closure.validate_delivery_evidence(evidence, snapshot, baseline)['organization_submission_verified']
    if group == 'REVIEW2':
        tampered = copy.deepcopy(evidence)
        proof = next(iter(tampered['organization_delivery_inventory'].values()))
        proof['independent_review']['test_evidence']['actor_id'] = 'member_001'
        with pytest.raises(ValueError):
            closure.validate_delivery_evidence(tampered, snapshot, baseline)
    with pytest.raises(FileExistsError):
        closure.export_managed_closure(prepared, tmp_path/'closed', slot_id=slot, sdk_closed=True)


def test_absent_delivery_is_not_final_tree_substitution(tmp_path):
    prepared, _, _, _ = fixture.prepare(tmp_path/'world', 'FREE2')
    slot = f"v142:{prepared.case['case_id']}:{condition('FREE2')['condition_id']}:1"
    result = closure.export_managed_closure(prepared, tmp_path/'closed', slot_id=slot, sdk_closed=True)
    assert result['submitted'] is False and result['same_tree'] is None
    assert result['delivery_validation']['legal_delivery_evidence'] is False
    with pytest.raises(ValueError):
        closure.validate_slot_identity(slot.replace('v142:', 'v131:'), prepared.case['case_id'])


def test_controller_production_route_and_local_counter_are_explicit():
    names = controller.main.__code__.co_names
    assert 'software_role_baseline_runtime_v141' in names
    assert 'software_fixed_organization_runtime_v131' not in names
    assert any(name.endswith('software_benchmark_project_closure_v141') for name in names)
    assert 'load_content_counter' in names
    peak = controller.process_resource_peak()
    assert peak['measured'] and peak['peak_rss_bytes'] > 0
    assert peak['scope'] == 'current_controller_process'
    source = (ROOT/'tools/run_role_baseline_controller_v141.py').read_text()
    assert 'require_content_counter=True' in source
    assert 'observation_token_counter=content_counter' in source
    assert bundle.ALIASES['controller.py'] == 'run_role_baseline_controller_v141.py'
    assert bundle.ALIASES['managed-worker.py'] == 'run_managed_worker_docker_v141.py'
    assert bundle.ALIASES['public-test-execution.py'] == 'public_test_execution_v141.py'
    assert 'software_collaboration_runtime_observer_v141.py' in bundle.NEW_MODULES
    value = tokenizer.descriptor()
    assert tokenizer.validate_descriptor(value) == value
    bad = copy.deepcopy(value)
    bad['require_content_counter'] = False
    with pytest.raises(ValueError):
        tokenizer.validate_descriptor(bad)


def test_controller_validates_actual_new_input_and_ready(tmp_path):
    bindings = module('v141_controller_input_fixture', ROOT/'tests/test_public_runtime_bindings_v141.py')
    row, public, entry, _, binding, ready, host = bindings.prepared(tmp_path, 'REVIEW2')
    from proworksim.software_benchmark_public_context_v062 import VERSION
    result = bindings.inputs.controller_inputs(host, row, ready, {'thinking': False}, {},
        public_context={'version': VERSION, 'instance_id': row['instance_id'],
                        'visible_text': 'fixture', 'visible_facts': {}},
        public_environment=public, public_test_entry=entry, actor_config=binding['config'])
    config = json.loads(result['controller-config.json'])
    assert controller.validate_config(config) == config
    assert controller.validate_ready(config, ready) == ready
    bad = copy.deepcopy(ready)
    bad['public_test_result_revision'] = 'v130-public-test-evidence-r1'
    with pytest.raises(ValueError):
        controller.validate_ready(config, bad)
