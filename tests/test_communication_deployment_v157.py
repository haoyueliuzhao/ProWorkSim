"""CPU-only checks of fresh conditions, unchanged roles and concrete runtime hooks."""
import copy
from pathlib import Path
import pytest
from proworksim import software_benchmark_alignment_contract_v157 as contract
from proworksim import software_benchmark_scope_v157 as scope
from proworksim import software_benchmark_episode_v157 as episode
from proworksim import software_benchmark_project_closure_v157 as closure
from proworksim.software_benchmark_candidates_v054 import reference

def row(group='C0'):
    value=contract.condition(group)
    return {'slot_id':f'v157:example__repo-1:REVIEW2_{group}:7','instance_id':'example__repo-1',
        'condition_id':value['condition_id'],'seed':7,'organization_id':'REVIEW2','group_id':group,
        'arm':'PROJECT','execution_arm':'PROJECT','fixed_members':['member_001','member_002'],'member_count':2}

def test_three_treatments_preserve_roles_and_resource_settings():
    values=[contract.condition(g) for g in contract.GROUP_IDS]
    assert len({v['condition_id'] for v in values})==3
    for key in ('fixed_organization','inference','episode_limits','execution_strategy'):
        assert values[0][key]==values[1][key]==values[2][key]
    for group in contract.GROUP_IDS:
        assert contract.validate_plan_identity(row(group))
        assert closure.validate_slot_identity(row(group)['slot_id'],'example__repo-1')==row(group)

def test_cross_condition_or_original_slot_rejected():
    value=row();value['group_id']='C1'
    with pytest.raises(ValueError):contract.validate_plan_identity(value)
    value=row();value['slot_id']='v156:example__repo-1:REVIEW2_C0:7'
    with pytest.raises(ValueError):contract.validate_plan_identity(value)

def test_actual_bounded_episode_uses_new_contract_and_closure():
    guard=lambda *a,**kw:{'status':'approved','execution_alignment_version':contract.VERSION,
        'source_index':{'path':'synthetic','sha256':'a'*64,'bytes':1},'plan':reference(scope.PLAN_FILE)}
    value=episode.build_episode(scope=scope,guard=guard)
    assert value.new_system_parent_slice is False
    assert value.actual_role_limits=={'actor':[4,16*1024**3,512],'controller':[2,32*1024**3,256]}
    assert value._run.__globals__['validate_condition'] is contract.validate_condition
    import types
    pending=[value._run.__code__]; names=set()
    while pending:
        code=pending.pop();names.update(code.co_names)
        pending.extend(c for c in code.co_consts if isinstance(c,types.CodeType))
    assert 'software_benchmark_project_closure_v157' in names

def test_panel_projection_cannot_replace_task_or_change_order():
    plan=scope.load(reference(scope.PLAN_FILE));assert scope.validate_plan(plan)
    changed=copy.deepcopy(plan);changed['rows'][0],changed['rows'][1]=changed['rows'][1],changed['rows'][0]
    with pytest.raises(PermissionError):scope.validate_plan(changed)

def test_condition_identity_changes_scorer_cache_namespace():
    plan=scope.load(reference(scope.PLAN_FILE))
    ids=[r['slot_index'] for r in plan['rows']]
    assert len(set(ids))==72 and min(ids)==15700 and max(ids)==15771
    assert len(set(f"score-{i}" for i in ids))==72
    assert scope.API_UNIT=='proworksim-v157-communication-pilot.service'
    assert scope.CONSTRAINTS['maximum_real_tls_sessions']==0

def test_actual_fifo_pump_and_container_bridge_support_all_new_routes():
    from proworksim import software_benchmark_model_fifo_v157 as fifo
    import types
    guard=lambda *a,**kw:{'status':'approved','execution_alignment_version':contract.VERSION,
        'source_index':{'path':'synthetic','sha256':'a'*64,'bytes':1},'plan':reference(scope.PLAN_FILE)}
    value=episode.build_episode(scope=scope,guard=guard)
    assert value._run.__globals__['serve_model_channel'] is fifo.serve_model_channel
    pending=[value._run.__code__];strings=[]
    while pending:
        code=pending.pop();strings.extend(c for c in code.co_consts if isinstance(c,str))
        pending.extend(c for c in code.co_consts if isinstance(c,types.CodeType))
    assert '/opt/pws-runtime/project/tools/bridge_communication_model_fifo_v157.py' in strings
    assert '/opt/pws-runtime/project/tools/bridge_ref_model_fifo_v064.py' not in strings
    assert {'/team-budget','/compressor-tokenize'}<=fifo.PATHS
    source=(scope.ROOT/'tools/run_communication_controller_v157.py').read_text()
    assert 'software_benchmark_model_fifo_v157 import FifoModelTransport' in source
    assert source.count('bind_shared_budget=not config["diagnostic"]')==2

def test_frozen_first_c1_admits_without_competing_c0_rotation(tmp_path):
    from proworksim.software_benchmark_group_admission_v157 import FairAdmission,DrainControl
    controls=DrainControl(tmp_path/'control.json',batch_root=tmp_path,groups=contract.GROUP_IDS,maximum=16)
    gate=FairAdmission(contract.GROUP_IDS,control=controls,maximum=16,maximum_startups=4)
    actual=[row(g) for g in ('C1','C0','C2')]
    for value in actual:
        gate.register_pending(value['group_id'],[value['slot_id']])
        gate.set_group_status(value['group_id'],healthy=False,can_dispatch=True)
    assert [gate.try_enter(value) for value in actual]==[True,True,True]
    assert len(gate.active)==3 and len(gate.starting)==3

def test_host_closure_counts_physical_retries_and_retains_auxiliary_unknown():
    from proworksim.software_benchmark_closed_usage_v157 import validate_usage
    limits={'all_model_attempts':512,'agent_decisions':512,'input_plus_output_tokens':5_000_000}
    physical={'calls':[{'call_id':'p1','prompt_tokens':10,'completion_tokens':2},
                       {'call_id':'p2','prompt_tokens':20,'completion_tokens':3}],
              'unresolved_calls':[],'usage_capture_complete':True}
    provider={'source':'one_shared_physical_provider_sqlite','attempts':2,'known_actual_tokens':35,
              'uncertain_reserved_tokens':0,'inflight_count':0,'available_tokens':4_999_965,
              'token_limit':5_000_000,'per_usage_id':{}}
    ledger={'attempts':2,'decisions':1,'known_actual_tokens':35,'complete_actual_tokens':35,
            'inflight':None,'uncertain_reserved_tokens':0,'token_limit':5_000_000,
            'all_model_attempt_limit':512,'agent_decision_limit':512,'calls':[{'logical_attempts':2}],
            'authoritative_provider_snapshot':provider}
    assert validate_usage(ledger,limits,physical) is ledger
    physical['unresolved_calls']=[{'call_id':'p3','purpose':'compressor','status':'uncertain','reserved_tokens':100}]
    physical['usage_capture_complete']=False
    provider.update(attempts=3,uncertain_reserved_tokens=100,available_tokens=4_999_865,
                    per_usage_id={'compressor':{'uncertain_reserved_tokens':100}})
    ledger.update(attempts=3,uncertain_reserved_tokens=100,complete_actual_tokens=None)
    assert validate_usage(ledger,limits,physical) is ledger
    physical['unresolved_calls'][0]['purpose']='agent'
    with pytest.raises(ValueError):validate_usage(ledger,limits,physical)
