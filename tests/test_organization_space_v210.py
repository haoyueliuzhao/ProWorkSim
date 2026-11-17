import copy,pytest
from proworksim.software_organization_space_v210 import *
def state():
 return {'members':{'a':{'status':'live'},'b':{'status':'live'}},'delivery_member':'a','requirements':['parser','serializer'],'roles':{'a':['implement'],'b':['review']},'work':{'root':{'scope':['parser','serializer'],'owner':'a','contributors':[],'authors':[],'status':'open'}},'dependencies':[],'collaboration':[['a','b'],['b','a']],'execution_order':['root'],'verification':{},'subteams':{}}
def op(kind,actor='a',**args):return {'op':kind,'actor':actor,'args':args}
def test_composition_preserves_source_and_is_never_live_execution():
 s=state();before=copy.deepcopy(s)
 x=proposal(s,[op('SPLIT_WORK',task='root',children={'parse':{'scope':['parser']},'serialize':{'scope':['serializer']}}),op('ASSIGN_WORK',task='parse',member='a'),op('ASSIGN_WORK',actor='b',task='serialize',member='b')])
 assert s==before and not x['live_execution']
 assert len(x['target']['work'])==2 and x['runtime_admission'].startswith('blocked')
def test_owned_assignment_requires_transfer():
 with pytest.raises(InvalidOrganization):proposal(state(),[op('ASSIGN_WORK',task='root',member='b')])
 p=proposal(state(),[op('TRANSFER_OWNERSHIP',task='root',member='b')]);assert p['target']['work']['root']['owner']=='b'
 assert p['trace'][0]['capability']['status']=='explicit_consent_required'
def test_split_cannot_drop_acceptance_and_cannot_fake_completion():
 with pytest.raises(InvalidOrganization):proposal(state(),[op('SPLIT_WORK',task='root',children={'x':{'scope':['parser']},'y':{'scope':['parser']}})])
 s=state();s['work']['root']['status']='done'
 with pytest.raises(InvalidOrganization):validate(s)
def test_no_self_review_even_after_role_rename():
 s=state();s['work']['root']['authors']=['a']
 with pytest.raises(InvalidOrganization):proposal(s,[op('CREATE_ROLE',member='a',roles=['review']),op('ASSIGN_VERIFICATION',task='root',member='a')])
def test_dependencies_cannot_cycle():
 s=proposal(state(),[op('SPLIT_WORK',task='root',children={'x':{'scope':['parser']},'y':{'scope':['serializer']}})])['target']
 s['work']['x']['owner']='a';s['work']['y']['owner']='a'
 with pytest.raises(InvalidOrganization):proposal(s,[op('CHANGE_DEPENDENCY',task='x',depends_on='y',operation='add'),op('CHANGE_DEPENDENCY',task='y',depends_on='x',operation='add')])
def test_no_member_birth_or_unbacked_operator():
 with pytest.raises(InvalidOrganization):proposal(state(),[op('CREATE_SUBTEAM',id='t',members=['a','new'])])
 with pytest.raises(InvalidOrganization):proposal(state(),[op('SPAWN',member='new')])
 assert CAPABILITIES['MERGE_WORK']['status'].startswith('not_supported')
def test_exact_target_dedup_and_unordered_graph_fields():
 a=proposal(state(),[]);s=state();s['collaboration'].reverse();s['requirements']=list(s['requirements'])
 b=proposal(s,[]);assert len(deduplicate([a,b]))==1
 a['coverage_family']='baseline';b['coverage_family']='different_trace'
 with pytest.raises(ValueError):structured_reference([a,b],{'baseline':1,'different_trace':1})
def test_reference_is_family_balanced_not_uniform_over_candidates():
 r=structured_reference([{'target_state_hash':'x','coverage_family':'A'},{'target_state_hash':'y','coverage_family':'A'},{'target_state_hash':'z','coverage_family':'B'}],{'A':1,'B':1})
 assert r=={'x':.25,'y':.25,'z':.5}
def test_new_formula_and_support_scales_above_twenty_candidates():
 q={str(i):1/30 for i in range(30)};r=dict(q);u={str(i):float(i==0) for i in range(30)}
 x=update_bank(q,r,u)
 assert sum(x['q_after'].values())==pytest.approx(1)
 assert all(v>=.05*r[k] for k,v in x['q_after'].items())
 assert x['q_after']['0']>x['q_after']['1']
 assert all(v==0 for v in x['undercoverage_novelty'].values())
 assert all(v==.05 for v in x['positive_N'].values())
def test_support_mismatch_unknown_cost_or_invalid_temperature_rejected():
 with pytest.raises(ValueError):update_bank({'x':1},{'y':1},{'x':1})
 with pytest.raises(ValueError):update_bank({'x':1},{'x':1},{'x':float('nan')})
 with pytest.raises(ValueError):update_bank({'x':1},{'x':1},{'x':1},t_c=0)
