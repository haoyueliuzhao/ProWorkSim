import pytest
from types import SimpleNamespace
from proworksim.software_organization_cn_v204 import *
from proworksim.software_organization_runtime_v204 import after_opportunity,FatalTransport
Q={z:1/3 for z in CANDIDATES}
def block(i):
 return {'state_id':i,'stage':'development','results':{z:{'environment_healthy':True,'official_code_pass':z=='ASSIST','legal_delivery':z=='ASSIST','score_same_delivery_version':True,'full_team_tokens':1000000} for z in CANDIDATES}}
def test_two_updates_new_evidence_and_zero_initial_novelty():
 a=update(Q,Q,[block('d1')],round_index=1)
 assert not a['novelty_active'] and a['q_after']['ASSIST']>Q['ASSIST']
 assert abs(sum(Q[z]*a['contribution'][z] for z in Q))<1e-12
 b=update(a['q_after'],Q,[block('d2')],round_index=2,previous_state_ids=['d1'])
 assert b['novelty_active'] and sum(b['q_after'].values())==pytest.approx(1)
 assert select({'KEEP':.05,'ASSIST':.9,'TRANSFER':.05},.4)=='ASSIST'
def test_contamination_missing_pair_and_confirmation_rejected():
 b=block('d');b['results']['TRANSFER']['environment_healthy']=False
 with pytest.raises(ValueError):update(Q,Q,[b],round_index=1)
 b=block('d');b['stage']='confirmation'
 with pytest.raises(ValueError):update(Q,Q,[b],round_index=1)
 with pytest.raises(ValueError):update(Q,Q,[block('d')],round_index=2,previous_state_ids=['d'])
def test_candidate_once_no_forced_action_and_fatal_halts(tmp_path):
 s={'diagnosis':'unfinished','environment_healthy':True,'final_review_active':False,'already_triggered':False}
 assert intervention('KEEP',s)is None
 assert 'leave diagnostic ownership' in intervention('ASSIST',s)
 with pytest.raises(ValueError):intervention('TRANSFER',{**s,'already_triggered':True})
 with pytest.raises(FatalTransport):after_opportunity(SimpleNamespace(rpc=SimpleNamespace(failed=True,closed=False)),tmp_path/'pause.json')
 assert (tmp_path/'pause.json').exists()

def test_phase_exit_counts_four_opportunities_after_acceptance():
 from proworksim.software_organization_cn_v204 import PolicyLifecycle
 phase=PolicyLifecycle('TRANSFER');events=[{'kind':'transfer_accepted','task_id':'diagnose'}]
 assert phase.observe(events,{'worker_id':'member_002'}) is None
 for _ in range(3):assert phase.observe(events,{'worker_id':'member_002'}) is None
 assert phase.observe(events,{'worker_id':'member_002'}) is not None
 assert phase.observe(events,{'worker_id':'member_002'}) is None

def test_callback_deadline_mismatch_marks_global_pause_before_rpc(tmp_path):
 from proworksim.software_organization_runtime_v204 import Actor
 actor=Actor.__new__(Actor);actor.rpc=SimpleNamespace(failed=False,closed=False);actor.task_deadline=3.
 with pytest.raises(FatalTransport):actor.test(files={},entry_metadata={},request={'hard_deadline_monotonic':2.})
 assert actor.fatal_transport['message']=='Callback/RPC deadline mismatch'
 with pytest.raises(FatalTransport):after_opportunity(actor,tmp_path/'pause.json')
 assert (tmp_path/'pause.json').exists()
