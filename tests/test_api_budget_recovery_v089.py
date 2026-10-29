import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_api_scope_v089 as scope
from proworksim import software_benchmark_recovery_bindings_v089 as bindings
from proworksim import software_benchmark_recovery_grading_v089 as grading
from proworksim import software_benchmark_io_v088 as io
from proworksim import software_benchmark_failure_scope_v088 as failure
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('prepare89_test', 'prepare_api_budget_recovery_v089.py')
runner = module('runner89_test', 'run_api_budget_recovery_v089.py')
launcher = module('launcher89_test', 'launch_api_budget_recovery_v089.py')


def source_row(index=5773):
    return {'slot_id': f'v064:example-{index}:DEEPSEEK_REF_B5000K:1', 'slot_index': index,
        'instance_id': f'example-{index}', 'condition_id': 'DEEPSEEK_REF_B5000K',
        'model_key': 'DEEPSEEK', 'input_plus_output_tokens': 5_000_000,
        'seed': 1, 'configuration': {'old': True}}


def test_recovery_changes_only_operational_identity_and_never_original_configuration():
    source = source_row()
    original = {'slot_id': source['slot_id'], 'slot_index': source['slot_index'], 'seed': 1,
                'tools': ['same'], 'budget': 5_000_000}
    row = prepare.recovery_row(source, 6000, {'fresh': True})
    config = {**original, 'slot_id': row['slot_id'], 'slot_index': row['slot_index']}
    assert scope.validate_mapping(row, source, config, original) is row
    assert row['slot_id'].startswith('v064:') and row['slot_id'] != source['slot_id']
    assert row['original_slot_id'] == source['slot_id']
    for changed in ({**row, 'seed': 2}, {**row, 'slot_index': 5999}, {**row, 'slot_id': source['slot_id']}):
        with pytest.raises(PermissionError):
            scope.validate_mapping(changed, source, config, original)
    with pytest.raises(PermissionError):
        scope.validate_mapping(row, source, {**config, 'budget': 10_000_000}, original)
    assert original['slot_index'] == 5773


def test_selection_uses_only_exact_cash_cutoff_and_clean_terminal_originals(tmp_path):
    rows, allowed, generation, events = [], [], {}, [
        {'kind': 'provider_stopped', 'provider': 'DEEPSEEK', 'reason': 'cash_exhausted', 'unix': 100}]
    for index in range(44):
        row = source_row(index)
        quiet = write_new(tmp_path/f'q{index}.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
        result = write_new(tmp_path/f'r{index}.json', {'slot_id': row['slot_id'], 'configuration': row['configuration'],
            'error': {'type': 'InterruptedError', 'message': 'Capability coordinator requested owned-episode cancellation'},
            'quiescence': quiet, 'retained_objects': []})
        rows.append(row)
        allowed.append(row['slot_id'])
        generation[row['slot_id']] = {'status': 'technical_unknown', 'result': result}
        events.append({'kind': 'generation_finished', 'slot_id': row['slot_id'], 'unix': 101+index})
    summary = {'failure': None, 'provider_failures': {'DEEPSEEK': {'reason': 'api_monetary_budget_exhausted'}},
               'generation': generation}
    selected, cutoff = prepare.selected_budget_cutoffs(summary, {'allowed_generation_slot_ids': allowed}, rows, events)
    assert len(selected) == 44 and cutoff == 100
    events[1]['unix'] = 99
    with pytest.raises(ValueError, match='administrative-cutoff'):
        prepare.selected_budget_cutoffs(summary, {'allowed_generation_slot_ids': allowed}, rows, events)


def test_resource_plan_has_only_fresh_keys_and_no_model_or_control_scope():
    rows, resources = [], {}
    for i in range(44):
        row = {**source_row(i), 'arm': 'PROJECT' if i < 23 else 'REF'}
        for role, prefix in [('actor', 'actor'), ('controller', 'controller'), ('volume', 'volume'), ('score', 'score')]:
            resources[f'{prefix}-{i}'] = {'role': role, 'slot_id': row['slot_id']}
        if i < 23:
            resources[f'delivery-score-{i}'] = {'role': 'delivery_score', 'slot_id': row['slot_id']}
        rows.append(prepare.recovery_row(row, 6000+i, {'fresh': i}))
    planned = prepare.build_resources(rows, {'resources': resources})
    assert len(planned) == 199 and 'actor-6000' in planned and 'actor-0' not in planned
    assert all(v['role'] not in ('control', 'model') for v in planned.values())
    assert resources['actor-0']['slot_id'] != planned['actor-6000']['slot_id']


def physical():
    return {'memory_available_bytes': 1100*2**30, 'disk_free_bytes': 2000*2**30,
            'cpu_sample_fresh': True, 'host_cpu_utilization_percent': 10}


def test_real_private_claim_consumes_only_new_identity_and_keeps_global_lock(tmp_path, monkeypatch):
    root = tmp_path/'shared'
    root.mkdir()
    claims = root/'resource-claims'
    claims.mkdir()
    old = claims/'actor-5773.json'
    old.write_text('retained original')
    monkeypatch.setattr(bindings.original, 'BATCH_ROOT', root)
    monkeypatch.setattr(scope, 'PLAN_FILE', tmp_path/'plan.json')
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'auth.json')
    monkeypatch.setattr(scope, 'SOURCE_FILE', tmp_path/'sources.json')
    write_new(scope.AUTH_FILE, {'approved': True})
    write_new(scope.SOURCE_FILE, {'files': []})
    row = prepare.recovery_row(source_row(), 6000, {'new': True})
    write_new(scope.PLAN_FILE, {'resources': {'actor-6000': {'role': 'actor', 'slot_id': row['slot_id'],
        'instance_id': row['instance_id'], 'image_id': 'fixed'}}})
    policy = bindings.policy(lambda *a, **kw: None,
        watchdog_guard=lambda: {'fresh': True, 'admit': True}, capacity_probe=physical, qwen_target=0)
    claim = policy.claim_resource('actor-6000')
    value = json.loads(Path(claim['path']).read_bytes())
    assert value['version'] == bindings.VERSION and value['plan'] == reference(scope.PLAN_FILE)
    assert Path(value['lease']).parent == claims and old.read_text() == 'retained original'
    with pytest.raises(ValueError, match='Unplanned'):
        policy.claim_resource('actor-5773')
    with pytest.raises(ValueError, match='consumed'):
        policy.claim_resource('actor-6000')
    policy.release_resource(claim, quiescent=True)
    assert not Path(value['lease']).exists() and old.read_text() == 'retained original'


def test_episode_uses_exact_new_dispatch_and_keeps_IO_and_failure_fixes():
    policy = bindings.policy(lambda *a, **kw: None,
        watchdog_guard=lambda: {'fresh': True, 'admit': True}, capacity_probe=physical)
    episode = bindings.episode(policy)
    assert episode._run.__globals__['policy'] is policy
    assert episode._run.__globals__['DockerStdioChannel'] is io.DockerStdioChannel
    assert episode._run.__globals__['classify_failure_scope'] is failure.classify_failure_scope
    assert episode.OwnedActorPair.attach.__globals__['policy'] is policy
    assert episode.OwnedActorPair.start.__globals__['parent'] is scope.parent_module()


def test_scorer_and_grader_use_new_identity_not_original_authority(monkeypatch):
    monkeypatch.setattr(grading.original_scorer.original_scorer, 'installation_manifest',
                        lambda: {'unchanged_official_installation': True})
    dispatch = bindings.dispatch_view(lambda *a, **kw: None)
    scored = grading.scorer(dispatch)
    assert scored._planned.__globals__['policy'] is dispatch
    assert scored.validate_capacity_claim.__globals__['policy'] is dispatch
    assert scored.Containers.create.__globals__['policy'] is dispatch
    assert scored.ObservedContainer.start.__globals__['policy'] is dispatch
    assert scored.validate_candidate_request.__globals__['validate_qualification'] is grading.validate_qualification
    base = grading._base(dispatch, scored)
    assert base.run_request.__globals__['policy'] is dispatch
    assert base.delivery_disposition.__globals__['prepare_score'] is base.prepare_score
    manager = bindings.policy(lambda *a, **kw: None,
        watchdog_guard=lambda: {'fresh': True, 'admit': True}, capacity_probe=physical)
    assert grading.scorer(manager).installation_manifest() == scored.installation_manifest()


def test_new_owner_keeps_original_compute_bounds_and_no_GPU_operations():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert command[:2] == ['systemd-run', '--user']
    assert '--property=MemoryHigh=32G' in command and '--property=MemoryMax=64G' in command
    assert '--property=LimitNOFILE=16384' in command and '--property=CPUQuota=800%' in command
    assert spec['Qwen_lifecycle_operations'] == 0 and spec['root_operations'] == 0


def approval():
    return {'version': 'v089-explicit-budget-recovery-authorization-r1', 'status': 'approved',
        'explicit_user_reply': '启动44个独立恢复回合', 'authorized_generation_attempts': 44,
        'REF': 21, 'PROJECT': 23, 'per_attempt_input_plus_output_token_upper_bound': 5_000_000,
        'total_new_input_plus_output_token_upper_bound': 220_000_000, 'same_ledger_total_CNY': '1700.00',
        'same_task_seed_and_model_settings': True, 'old_results_and_fees_preserved': True,
        'new_attempts_are_not_exact_session_resumption': True, 'other_205_unknowns_after_this_phase': True,
        'existing_Qwen_operations_modified': False,
        'proposal': {'path': '/nonexistent/historical-review-document', 'sha256': 'a'*64, 'bytes': 12}}


def test_explicit_recovery_scope_requires_more_than_a_cash_topup_and_ignores_mutable_report(tmp_path, monkeypatch):
    path = tmp_path/'approval.json'
    monkeypatch.setattr(scope, 'USER_AUTH_FILE', path)
    path.write_text(json.dumps(approval()))
    assert scope.require_explicit_recovery_authorization() == reference(path)
    for change in ({'explicit_user_reply': '增补两百预算'}, {'REF': 22},
                   {'per_attempt_input_plus_output_token_upper_bound': 10_000_000},
                   {'same_ledger_total_CNY': '1900.00'}, {'old_results_and_fees_preserved': False},
                   {'new_attempts_are_not_exact_session_resumption': False}):
        path.write_text(json.dumps({**approval(), **change}))
        with pytest.raises(PermissionError, match='top-up alone'):
            scope.require_explicit_recovery_authorization()


def test_prepare_and_runtime_fail_before_inherited_authority_when_recovery_approval_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'USER_AUTH_FILE', tmp_path/'absent.json')

    def unexpected_ancestor(*args, **kwargs):
        raise AssertionError('Unapproved recovery must fail before inherited authority or runtime admission')

    monkeypatch.setattr(scope.original, 'require_v066_allowed', unexpected_ancestor)
    for operation in (prepare.prepare, scope.require_allowed):
        with pytest.raises(PermissionError, match='Explicit authorization'):
            operation()
