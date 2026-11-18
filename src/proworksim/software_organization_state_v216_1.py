"""Admit genuine imperfect organization states; unfinished setup is a policy input."""
from .software_organization_state_v216 import capture as prior
VERSION='v216.1-real-state-admission-r2'
def capture(prepared,runtime):
 v=prior(prepared,runtime);flags=v['reason_flags'];v['version']=VERSION
 v['eligible']=all(flags[k] for k in ('actual_code_progress','subsequent_executed_public_test','unmodified_remaining_work','nonterminal'))
 v['initial_remaining_setup_is_not_an_admission_gate']=True
 for tid,w in v['graph']['work'].items():w['dependency_revisions']=dict(prepared.world._task(tid)['dependency_revisions'])
 _,_,bundle=prepared.world._bundle('member_001');patches=prepared.world._software()['patches']
 v['pending_peer_patches']=sum(p['author']!='member_001' and p['patch_id'] not in bundle['included_patch_ids'] for p in patches.values())
 v['conflict_count']=len(prepared.world._conflicts('member_001'))
 from .software_organization_world_v216 import Port,PROJECT
 view=Port(prepared.world.session('member_001',PROJECT),'member_001').observe()
 v['visible_work_history']={k:view.get(k) for k in ('messages','handoffs','tasks')}
 v['private_notes_and_other_member_private_history_sent']=False
 return v
