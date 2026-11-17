import pytest
from proworksim.software_organization_design_v210 import *
U={z:1/3 for z in ARMS}
def test_cdf_coupling_is_not_tv():
 q=dict(zip(ARMS,(.3223176052771373,.3198205949067893,.3578617998160733)))
 d=coupling(U,q)
 assert d['TV']==pytest.approx(.024528466482740)
 assert d['common_inverse_cdf_disagreement']==pytest.approx(.035544194538936)
 assert d['independent_draw_disagreement']==pytest.approx(2/3)
def test_quota_conserves_count_and_randomized_marginals():
 q=dict(zip(ARMS,(.3223176052771373,.3198205949067893,.3578617998160733)))
 for n in (12,30):
  allocations=[apportioned(q,n,seed) for seed in range(500)]
  assert all(sum(a['counts'].values())==n for a in allocations)
  for z in ARMS:
   assert all(a['counts'][z] in (math.floor(n*q[z]),math.ceil(n*q[z])) for a in allocations)
   assert sum(a['counts'][z] for a in allocations)/len(allocations)==pytest.approx(n*q[z],abs=.07)
def rows(n=8):
 return [{'state_id':str(i),'repo':'r'+str(i%4),'stage':'development','results':{z:{'y':z=='TRANSFER','tokens':1000000} for z in ARMS}} for i in range(n)]
def test_guard_preserves_floor_and_clips_drift():
 x=guarded_update(U,U,rows());assert x['step_mixing_weight']<1
 assert sum(x['q_after'].values())==pytest.approx(1)
 assert min(x['q_after'].values())>=.05
 assert x['distance_from_previous']['TV']==pytest.approx(.05)
def test_no_partial_or_confirmation_update():
 with pytest.raises(ValueError):guarded_update(U,U,rows(2))
 r=rows();r[0]['stage']='confirmation'
 with pytest.raises(ValueError):guarded_update(U,U,r)
def test_cluster_uncertainty_and_cost_quality_separate():
 x=contribution(U,rows());assert x['mean_quality']['TRANSFER']==1
 assert x['mean_cost']['TRANSFER']==0
 assert x['uncertainty']['TRANSFER']['cluster_SE']==pytest.approx(0)
 assert x['uncertainty']['TRANSFER']['small_cluster_warning']
def event(seq,kind,**kw):return dict(sequence=seq,kind=kind,task_id='diagnose',**kw)
def test_return_to_unassigned_is_not_legal_return():
 e=[event(1,'transfer_offered',offer_id='a',from_member='member_001',recipient='member_002'),event(2,'transfer_accepted',offer_id='a',actor_id='member_002',previous_owner='member_001',owner='member_002'),event(3,'read',actor_id='member_002'),event(4,'task_returned',actor_id='member_002')]
 x=action_chain('TRANSFER',e,presented=True);assert x['organization_changed'] and x['recipient_work_observed'];assert not x['legal_return_offer_accept'];assert x['release_to_unassigned_not_legal_return']
 e=e[:3]+[event(5,'transfer_offered',offer_id='b',from_member='member_002',recipient='member_001'),event(6,'transfer_accepted',offer_id='b',actor_id='member_001',previous_owner='member_002',owner='member_001')]
 assert action_chain('TRANSFER',e,presented=True)['legal_return_offer_accept']
def test_wrong_task_and_orphan_accept_do_not_count():
 e=[event(1,'transfer_accepted',offer_id='missing',actor_id='member_002',previous_owner='member_001',owner='member_002')]
 assert not action_chain('TRANSFER',e,presented=True)['organization_changed']
 e=[event(1,'work_message',actor_id='member_001',recipient='member_002')];e[0]['task_id']='root_goal'
 assert not action_chain('ASSIST',e,presented=True)['committed_initiation']
