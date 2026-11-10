"""Host-produced configuration must pass the actual isolated CLI consumer."""
import importlib.util
import json
import pytest

from proworksim import software_benchmark_scope_v193 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_alignment_contract_v193 import condition, GROUP_IDS
from proworksim.software_benchmark_runtime_inputs_v193 import controller_inputs, PUBLIC_FILES
from proworksim.software_public_test_view_v193 import VERSION as TEST_VIEW


def consumer():
    spec = importlib.util.spec_from_file_location('context_controller_193', scope.ROOT / 'tools/run_context_controller_v193.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emitted(group, diagnostic):
    plan = scope.load(reference(scope.PLAN_FILE))
    row = next(r for r in plan['rows'] if r['group_id'] == group)
    host = scope.load(row['configuration'])
    previous = scope.BATCH_ROOT.parents[1] / 'software-benchmark-v192/key-event-pilot-r1/diagnostic-1'
    # Original actor's public receipts are unchanged; no new container or model.
    ready = json.loads((previous / 'actor-ready.json').read_bytes())
    context = json.loads((previous / 'public-context-provenance.json').read_bytes())
    environment = json.loads((previous / 'public-environment.json').read_bytes())
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': row['instance_id'],
             'argv': host['public_test_entry']['argv'], 'cwd': '/testbed',
             'timeout_seconds': 1800, 'hidden_material_used': False}
    actor = {k: ready[k] for k in ('organization_id', 'fixed_members', 'member_count',
            'role_contract_version', 'role_catalog_sha256', 'public_test_result_revision',
            'public_test_contract_sha256')}
    actor.update(ready['public_test_files_sha256'])
    actor.update(public_test_entry=entry, public_test_dependencies=None, instance_id=row['instance_id'])
    payload = controller_inputs({**host, 'dataset_revision': condition(group)['dataset_revision']},
        row, ready, {} if diagnostic else {'thinking': False}, 'http://127.0.0.1:18219',
        diagnostic=diagnostic, public_context=context, public_environment=environment,
        public_test_entry=entry, actor_config=actor)
    config = json.loads(payload['controller-config.json'])
    config.update(lifecycle_deadline=123456789.0, maximum_lifecycle_seconds=600 if diagnostic else 24000)
    return config


@pytest.mark.parametrize('group', GROUP_IDS)
@pytest.mark.parametrize('diagnostic', [True, False])
def test_actual_host_config_roundtrips_through_cli_consumer(group, diagnostic):
    config = emitted(group, diagnostic)
    assert config['common_public_test_view_revision'] == TEST_VIEW
    assert consumer().validate_config(config) is config


def test_mismatched_or_missing_public_view_is_rejected():
    config = emitted('M1-5K', True)
    config['common_public_test_view_revision'] = 'unbound'
    with pytest.raises(ValueError, match='public-test view revision'):
        consumer().validate_config(config)
    del config['common_public_test_view_revision']
    with pytest.raises(ValueError, match='public-test view revision'):
        consumer().validate_config(config)
