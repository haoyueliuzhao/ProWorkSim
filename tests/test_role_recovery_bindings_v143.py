"""Narrow recovery boundaries, CPU/local files only; no model or Docker calls."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v143 as scope
from proworksim import software_benchmark_episode_v143 as episode
from proworksim import software_benchmark_grading_v143 as grading
from proworksim.software_benchmark_alignment_contract_v141 import VERSION as ALIGNMENT
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def test_recovery_preserves_original120_and_adds_only_diagnostic5():
    original = scope.load(reference(scope.previous.PLAN_FILE))
    value = scope.recovery_plan()
    assert scope.validate_plan(value) == value
    assert value['rows'] == original['rows'] and value['environments'] == original['environments']
    assert value['panel'] == original['panel']
    assert scope.LEDGER_FILE == scope.previous.LEDGER_FILE
    assert scope.API_UNIT == scope.previous.API_UNIT
    assert [row['index'] for row in value['diagnostics']] == [5,2,3,4]
    assert set(value['resources'])-set(original['resources']) == {
        'diagnostic-5-actor','diagnostic-5-controller','diagnostic-5-volume'}
    assert value['constraints']['maximum_containers'] == 570
    changed = copy.deepcopy(value)
    changed['rows'][0]['seed'] += 1
    with pytest.raises(PermissionError, match='original120'):
        scope.validate_plan(changed)
    guard_calls = []
    dispatch = scope.dispatch_view(lambda *a, **k: guard_calls.append((a,k)))
    with pytest.raises(PermissionError, match='permanently closed'):
        dispatch.claim_resource('diagnostic-1-controller')
    assert guard_calls == []


def test_authority_uses_original_grant_and_standing_instruction_not_fictional_new_approval(tmp_path, monkeypatch):
    proposal = write_new(tmp_path/'proposal.json', {'synthetic_CPU_fixture':True})
    permission = write_new(tmp_path/'permission.json', {'record_kind':'standing_user_instruction',
        'experimental_docker_without_disruption':True,'shared_server_or_other_users_may_be_affected':False,
        'other_root_operations_authorized':False})
    monkeypatch.setattr(scope, 'PROPOSAL_FILE', tmp_path/'proposal.json')
    monkeypatch.setattr(scope, 'USER_GRANT_FILE', tmp_path/'grant.json')
    monkeypatch.setattr(scope, 'STANDING_PERMISSION_FILE', tmp_path/'permission.json')
    value = {'status':'authorized_by_existing_instructions','explicit_new_proposal_user_approval':False,
        'original_user_grant':reference(scope.previous.USER_GRANT_FILE),
        'standing_docker_permission':permission,'deployment_amendment':proposal,'additional_model_attempts':0}
    grant = write_new(tmp_path/'grant.json', value)
    auth = {'user_grant':grant,'previous_zero_model_cleanup':scope.prior_zero_model_cleanup()}
    assert scope.validate_authority_basis(auth) == value
    value['explicit_new_proposal_user_approval'] = True
    (tmp_path/'grant.json').write_text(json.dumps(value))
    auth['user_grant'] = reference(tmp_path/'grant.json')
    with pytest.raises(PermissionError, match='actual standing'):
        scope.validate_authority_basis(auth)


def test_real_new_episode_binds_bundle143_controller32g_and_pair_accepts_index5(tmp_path):
    plan = scope.recovery_plan()
    plan_ref = write_new(tmp_path/'plan.json', plan)
    private_scope = SimpleNamespace(**{**vars(scope), 'PLAN_FILE':tmp_path/'plan.json',
        'load':lambda ref: json.loads(open(ref['path']).read())})
    authority = {'status':'approved','execution_alignment_version':ALIGNMENT,
                 'source_index':{'CPU_only':True},'plan':plan_ref}
    binding = episode.build_episode(scope=private_scope, guard=lambda *a, **k: authority)
    assert binding.runtime.__name__.endswith('sdk_bundle_v143')
    assert binding.actual_role_limits['controller'][1] == 32*scope.GIB
    first = plan['diagnostics'][0]
    row = next(row for row in plan['rows'] if row['slot_id'] == first['slot_id'])
    pair = binding.OwnedActorPair(None, slot_index=row['slot_index'], slot_id=row['slot_id'],
        instance_id=row['instance_id'], diagnostic=True, diagnostic_index=5)
    assert pair._key('actor') == 'diagnostic-5-actor'
    assert binding._run.__globals__['validate_diagnostic_entry'](row,5) is None
    with pytest.raises(PermissionError):
        binding._run.__globals__['validate_diagnostic_entry'](row,1)
    with pytest.raises(PermissionError):
        binding.run_diagnostic(1)


def test_new_grading_never_uses_old_grant_or_scope_local_transport_import():
    scoring = grading.scorer(scope.dispatch_view(scope.require_grading_allowed), manifest_provider=lambda:{})
    ns = scoring.validate_request.__globals__
    assert ns['policy'].VERSION == scope.VERSION
    assert ns['environment'] is scoring.environment
    assert scope.GRADING_ROOT != scope.previous.GRADING_ROOT
    assert scoring._v143_reset_scorer._score.__globals__['policy'].VERSION == scope.VERSION
    assert grading.control_key('psf__requests-1921','gold') == 'control-v142-psf__requests-1921-gold'
