"""New team host binding and group receipts without external operations."""
from types import SimpleNamespace

from proworksim import software_benchmark_scope_v131 as scope
from proworksim import software_benchmark_episode_v131 as episode
from proworksim import software_benchmark_sdk_bundle_v131 as bundle
from proworksim import software_benchmark_alignment_contract_v131 as contract
from proworksim.software_benchmark_candidates_v054 import reference


def test_actual_builder_binds_team_contract_group_receipt_and_parent():
    plan = scope.load(reference(scope.PLAN_FILE))
    calls=[]
    authority={'status':'approved','execution_alignment_version':contract.VERSION,
               'source_index':{'fixture_only':True},'plan':reference(scope.PLAN_FILE)}
    def guard(operation, **identity):
        calls.append((operation,identity))
        return authority
    injected=SimpleNamespace(ROOT=scope.ROOT,BATCH_ROOT=scope.BATCH_ROOT,
        load=scope.load,dispatch_view=lambda supplied:scope.dispatch_view(supplied))
    value=episode.build_episode(scope=injected,guard=guard)
    assert value.runtime is bundle
    assert value._run.__globals__['OwnedActorPair'] is value.OwnedActorPair
    assert value.OwnedActorPair.__name__ == 'BoundedTeamPair'
    assert value.run_episode.__globals__['_run'] is value._run
    assert value.integration_points == {key:1 for key in ('closure','actor_binding','actor_upload',
        'ready','controller_inputs','controller_result','effective_deadline','group_receipt')}
    for group in contract.GROUP_IDS:
        row=next(r for r in plan['rows'] if r['organization_id']==group)
        config,condition,limits=value._row_and_config(row,False)
        assert config['organization_id']==condition['organization_id']==group
        assert limits['input_plus_output_tokens']==5_000_000
    assert len(calls)==6
    assert all(op=='v066.run' for op,_ in calls)
    assert not scope.AUTH_FILE.exists(), 'The synthetic guard must not materialize a live runtime grant'


def test_single_agent_relabel_cannot_be_a_team_result(monkeypatch):
    import pytest
    row=next(r for r in scope.load(reference(scope.PLAN_FILE))['rows'] if r['organization_id']=='CHIEF')
    child={'execution_alignment':contract.shared_strategy('CHIEF'),'organization_id':'CHIEF',
           'group_id':'CHIEF','fixed_members':row['fixed_members'],
           'actual_member_registry':['member_001'],'private_sessions':{'member_001':'session1'}}
    with pytest.raises(ValueError,match='actual fixed registry'):
        episode.validate_controller_result(child,None,row,None,None)
    child.update(actual_member_registry={m:{'status':'live'} for m in row['fixed_members']},
                 private_sessions={member:'same-session' for member in row['fixed_members']})
    with pytest.raises(ValueError,match='actual fixed registry'):
        episode.validate_controller_result(child,None,row,None,None)
    child['private_sessions']={member:member+'-private' for member in row['fixed_members']}
    monkeypatch.setattr(episode.preflight,'validate_preflight_receipt',lambda *_a:{'passed':True})
    assert episode.validate_controller_result(child,None,row,None,None)=={'passed':True}
