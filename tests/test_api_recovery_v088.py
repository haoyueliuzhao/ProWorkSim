import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_scope_v088 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('prepare88_test', 'prepare_api_recovery_v088.py')
runner = module('runner88_test', 'run_api_recovery_v088.py')
launcher = module('launcher88_test', 'launch_api_recovery_v088.py')


def row(slot, index):
    return {'slot_id': slot, 'slot_index': index, 'model_key': 'DEEPSEEK',
            'condition_id': 'DEEPSEEK_REF_B5000K', 'configuration': {'original': slot}, 'arm': 'REF'}


def test_recovery_excludes_old_live_and_restores_failed_terminal_without_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(scope.original, 'BATCH_ROOT', tmp_path)
    rows = [row('old-live', 1), row('failed-closed', 2), row('requested-unknown', 3), row('unused', 4)]
    (tmp_path/'episodes/1').mkdir(parents=True)
    (tmp_path/'episodes/1/result.json').write_text('incomplete live writer; must not be read')
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    folder = tmp_path/'episodes/2'
    folder.mkdir()
    original = write_new(folder/'result.json', {**rows[1], 'status': 'closed', 'quiescence': quiet,
        'retained_objects': [], 'api_administrative_truncation': True})
    state = {'generation': {'old-live': {'status': 'external_running', 'result': None}}}
    value = prepare.recover_partition(rows, state, continuing={'old-live'}, scheduled={'failed-closed'},
        requested={'requested-unknown'}, claims_root=tmp_path/'resource-claims', roots=(tmp_path,))
    generations, eligible, recovered, _, _ = value
    assert generations['old-live'] == state['generation']['old-live']
    assert generations['failed-closed']['result'] == original
    assert generations['failed-closed']['administrative_truncation'] is True
    assert generations['requested-unknown']['status'] == 'technical_unknown'
    assert eligible == ['unused'] and recovered == ['failed-closed']


def test_failed_consumed_slot_needs_actual_quiescence_not_just_missing_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(scope.original, 'BATCH_ROOT', tmp_path)
    slot = row('failed', 2)
    (tmp_path/'episodes/2').mkdir(parents=True)
    with pytest.raises(ValueError, match='trustworthy terminal'):
        prepare.recover_partition([slot], {'generation': {}}, continuing=set(), scheduled={'failed'},
            requested=set(), claims_root=tmp_path/'claims', roots=(tmp_path,))


def test_recovery_accepts_only_the_audited_zero_dispatch_select_failure(tmp_path):
    transport = write_new(tmp_path/'transport.json', {'generation_requests': 0,
        'error': {'type': 'ValueError', 'message': 'filedescriptor out of range in select()'}})
    result = write_new(tmp_path/'result.json', {'shared_integrity_fault': 'trusted_model_bridge_initialization_failed',
        'model_calls': 0, 'model_dispatch_started': False, 'model_transport': transport})
    failure = {'kind': 'shared_generation_integrity_failure', 'result': result}
    assert prepare.validate_failure({'failure': failure}) == failure
    with pytest.raises(ValueError, match='recorded'):
        prepare.validate_failure({'failure': {'kind': 'unknown'}})
    changed = write_new(tmp_path/'changed.json', {'shared_integrity_fault': 'trusted_model_bridge_initialization_failed',
        'model_calls': 1, 'model_dispatch_started': True, 'model_transport': transport})
    with pytest.raises(ValueError, match='audited'):
        prepare.validate_failure({'failure': {**failure, 'result': changed}})


def authorize_fixture(monkeypatch, tmp_path):
    def ref(path):
        return {'path': str(path)}
    monkeypatch.setattr(scope, 'reference', ref)
    monkeypatch.setattr(scope, 'HISTORY_ROOT', tmp_path/'history')
    monkeypatch.setattr(scope, 'HANDOFF_ROOT', tmp_path/'handoff')
    auth = {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': ref(scope.prior.AUTH_FILE), 'source_index': ref(scope.SOURCE_FILE),
        'parent_authorization': ref(parent.AUTHORIZATION), 'desired_API_concurrency': 48,
        'maximum_API_concurrency': 48, 'maximum_starting_pairs': 16, 'API_cash_cap_CNY': '1500.00',
        'coordinator_memory_bytes': scope.API_MEMORY_BYTES,
        'coordinator_memory_high_bytes': scope.API_MEMORY_HIGH_BYTES,
        'nofile_soft_limit': scope.NOFILE, 'manager_CPU_count': 8, 'Qwen_lifecycle_operations': 0,
        'per_container_limits_changed': False, 'grading_requires_live_API_parent': False}
    original_row = {'slot_id': 'old-closed', 'model_key': 'DEEPSEEK', 'input_plus_output_tokens': 5_000_000,
                    'instance_id': 'original-instance'}
    plan = {'original_plan': ref(scope.original.PLAN_FILE), 'inventory': ref(scope.INVENTORY_FILE),
        'handoff': ref(scope.PREDECESSOR_PROOF),
        'API_ledger': str(scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'),
        'planned_API_slots': 1000, 'new_preparation_model_calls': 0}
    inventory = {'allowed_generation_slot_ids': ['unused'], 'excluded_old_scheduled_slot_ids': ['old-closed'],
        'generation': {'old-closed': {'status': 'closed', 'result': {'same': True}}},
        'continuing_old_owned_slot_ids': []}
    values = {str(scope.AUTH_FILE): auth, str(scope.SOURCE_FILE): {'files': []},
        str(scope.BATCH_ROOT/'plan-seal.json'): {'authorization': ref(scope.AUTH_FILE), 'plan': ref(scope.PLAN_FILE)},
        str(scope.PLAN_FILE): plan, str(scope.INVENTORY_FILE): inventory}
    monkeypatch.setattr(scope, 'load', lambda value: values[value['path']])
    monkeypatch.setattr(scope.original, 'require_v066_allowed', lambda *args, **kwargs: {'plan': {'original': True}})
    monkeypatch.setattr(scope.original, '_cached_json', lambda _: {'rows': [original_row]})
    return auth, original_row


def test_parent_release_does_not_authorize_generation_but_fixed_grading_still_validates_scope(tmp_path, monkeypatch):
    authority, original_row = authorize_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(parent, 'require_qualified', lambda: (_ for _ in ()).throw(PermissionError('parent released')))
    assert scope.require_grading_allowed('v076.run', slot_id='old-closed') == authority
    with pytest.raises(PermissionError, match='parent released'):
        scope.require_allowed('v076.run', slot_id='old-closed')
    with pytest.raises(PermissionError, match='never API requests'):
        scope.require_grading_allowed('v088.api.request', slot_id='old-closed')
    original_row['model_key'] = 'QWEN'
    with pytest.raises(PermissionError, match='original DeepSeek'):
        scope.require_grading_allowed('v076.run', slot_id='old-closed')
    original_row['model_key'] = 'DEEPSEEK'
    authority['grading_requires_live_API_parent'] = True
    with pytest.raises(PermissionError, match='sealed authority'):
        scope.require_grading_allowed('v076.run', slot_id='old-closed')


def test_actual_episode_integrates_high_FD_and_local_scope_in_private_namespaces(tmp_path, monkeypatch):
    from proworksim import software_benchmark_io_v088 as io
    from proworksim import software_benchmark_failure_scope_v088 as isolation
    from proworksim import software_benchmark_episode_v066 as original
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'authority.json')
    write_new(scope.AUTH_FILE, {'approved': True})
    binding = runner.episode_binding_class()(lambda *a, **k: {}, watchdog_guard=lambda: {}, qwen_target=0)
    ns = binding.api.run_episode.__globals__
    assert ns is not vars(original)
    assert ns['DockerStdioChannel'] is io.DockerStdioChannel
    assert ns['OwnedActorPair'].attach.__globals__['DockerStdioChannel'] is io.DockerStdioChannel
    assert ns['classify_failure_scope'] is isolation.classify_failure_scope
    assert original.classify_failure_scope is not isolation.classify_failure_scope


def test_grading_policy_cannot_create_unparented_actors(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'authority.json')
    write_new(scope.AUTH_FILE, {'approved': True})
    policy, grading = runner.grading_bindings(SimpleNamespace(admission=lambda: {}))
    assert grading.delegate.base.run_request.__globals__['policy'] is policy
    with pytest.raises(PermissionError, match='cannot create actors'):
        policy._write_claim(tmp_path/'actor.json', {'spec': {'role': 'actor'}})
    with pytest.raises(PermissionError, match='cannot create actors'):
        policy._write_claim(tmp_path/'volume.json', {'spec': {'role': 'volume'}})
    assert not (tmp_path/'actor.json').exists()


def test_scoring_recovery_never_competes_with_the_continuing_owner(monkeypatch):
    slots = [row('old', 1), row('ours', 2)]
    entries = {slot['slot_id']: {'status': 'closed', 'result': {'same': slot['slot_id']}} for slot in slots}
    calls = []
    monkeypatch.setattr(prepare, 'original_score', lambda row, generation, endpoint:
        (calls.append((row['slot_id'], endpoint)) or None, (endpoint, row, generation['result'], False)))
    jobs, _ = prepare.recover_jobs(slots, entries, {}, {}, continuing={'old'})
    assert calls == [('ours', 'code')] and len(jobs) == 1


def test_new_service_soft_memory_boundary_is_private_and_keeps_the_hard_cap():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert command[:2] == ['systemd-run', '--user']
    assert '--property=MemoryHigh=32G' in command and '--property=MemoryMax=64G' in command
    assert '--property=CPUQuota=800%' in command and '--property=LimitNOFILE=16384' in command
    assert scope.cpu_affinity() == list(range(168, 176))
    assert not any(value in ('--system', 'stop', 'restart') for value in command)


def test_live_old_snapshot_is_used_only_for_its_original_owned_ids():
    own = {'generation': {'failed': {'status': 'technical_unknown'}, 'old': {'status': 'external_running'}},
           'scores': {}, 'deliveries': {}}
    old = {'generation': {'old': {'status': 'closed'}, 'new': {'status': 'not_started'}}, 'scores': {}, 'deliveries': {}}
    before = copy.deepcopy(own)
    result = runner.combined_history(own, old, {'old'}, {'new'})
    assert result['generation'] == {'failed': {'status': 'technical_unknown'}, 'old': {'status': 'closed'}}
    assert own == before


@pytest.mark.parametrize('already_final', [False, True])
def test_preparation_records_whether_the_captured_old_history_was_final(tmp_path, monkeypatch, already_final):
    for name in ('HANDOFF_ROOT', 'HISTORY_ROOT', 'OLD_API_ROOT', 'BATCH_ROOT'):
        value = tmp_path/name
        value.mkdir()
        monkeypatch.setattr(scope, name, value)
    old = {'generation': {'old': {'status': 'closed'}, 'foreign': {'status': 'not_started'}},
           'scores': {}, 'deliveries': {}}
    if already_final:
        (scope.HANDOFF_ROOT/'stopped.json').write_text('{}')
        target = scope.HISTORY_ROOT/'historical-results.json'
    else:
        target = scope.OLD_API_ROOT/'cursor.json'
    import json
    target.write_text(json.dumps(old))
    calls = []
    monkeypatch.setattr(prepare.handoff, 'validate_launch_pause', lambda: calls.append('validated'))
    history, owned, frozen, final = prepare.continuing_history({'old_owned_slot_ids': ['old']})
    assert final is already_final
    assert calls == ([] if already_final else ['validated'])
    assert history['generation'] == {'old': old['generation']['old']}
    assert owned == ['old'] and Path(frozen['path']).read_bytes() == target.read_bytes()
