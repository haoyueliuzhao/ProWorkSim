"""Conservative offline policy interface; no live tasks, roles or tools mutated."""
from __future__ import annotations
import copy

OPERATIONS={'Reassign','Split','Merge','AddHandoff','AddReviewer'}
STRONG={'Confirmed Structural','Confirmed Dynamic'}

def diagnose(state):
    findings=[];tasks=state['tasks'];members=state['members']
    def finding(kind,task,**extra):findings.append({'kind':kind,'task':task,'evidence':list(state['evidence']),**extra})
    for tid,t in tasks.items():
        if t.get('required') and not t.get('owner') and t.get('ownership_record_complete'):finding('ResponsibilityGap',tid,execution_verified=t.get('ready',False))
    for d in state['dependencies']:
        if not d.get('active') or d.get('status') not in STRONG or not d.get('evidence'):continue
        a,b=tasks[d['upstream']],tasks[d['downstream']]
        if a.get('owner') and b.get('owner') and a['owner']!=b['owner'] and [d['upstream'],d['downstream']] not in state['handoffs']:
            finding('DependencyMisalignment',d['downstream'],upstream=d['upstream'],execution_verified=d.get('blocked_due_to_missing_handoff') is True)
    for region in state['regions']:
        if region.get('exclusive') and len(region['owners'])>1 and region.get('ownership_evidence'):
            finding('OwnershipConflict',region['tasks'][0],region=region['id'],tasks=region['tasks'],execution_verified=region.get('observed_conflict') is True)
    for tid,t in tasks.items():
        downstream=[d for d in state['dependencies'] if d['active'] and d['upstream']==tid and d['status'] in STRONG and d.get('evidence')]
        if t.get('blocked_reason')=='ownership_capacity' and t.get('blocked_observations',0)>=2 and len(downstream)>=2 and t.get('available_alternative'):
            finding('CoordinationBottleneck',tid,execution_verified=True)
    return findings

def validate(candidate,state):
    errors=[];op=candidate['operation'];tasks=state['tasks'];members=state['members'];selected=candidate['tasks']
    if op not in OPERATIONS:errors.append('operation_not_enabled')
    if not selected or any(t not in tasks for t in selected):errors.append('unknown_task')
    if state.get('ongoing_critical_operation') and op in {'Reassign','Split','Merge'}:errors.append('would_interrupt_critical_operation')
    if op in {'Reassign','Merge','Split'}:
        plan=candidate.get('ownership_plan',{})
        if set(plan)!=set(selected):errors.append('incomplete_ownership_plan')
        for t,m in plan.items():
            target=members.get(m,{})
            if not target.get('live'):errors.append('target_not_live')
            if not set(tasks[t].get('required_tools',[]))<=set(target.get('tools',[])):errors.append('target_tool_gap')
            if state['step']-tasks[t].get('last_reassignment',-999)<state['policy']['hold_steps']:errors.append('minimum_hold_window')
            if tasks[t].get('recent_owner_switches',0)>=state['policy']['switch_limit']:errors.append('oscillation_guard')
        if candidate.get('cost_units',0)>state['policy']['max_proxy_cost_units']:errors.append('proxy_adjustment_cost_limit')
        if any(not t.get('owner') and t.get('required') for tid,t in tasks.items() if tid not in selected):errors.append('unaddressed_required_task_gap')
        for reviewer in state.get('independent_reviewers',[]):
            if reviewer['member']==plan.get(reviewer['task'],tasks[reviewer['task']].get('owner')):errors.append('would_remove_independent_review')
    if op=='AddHandoff' and not any(d['active'] and [d['upstream'],d['downstream']]==selected for d in state['dependencies']):errors.append('dependency_not_current')
    if op=='AddReviewer':
        if candidate.get('reviewer') not in members or candidate['reviewer']==state.get('artifact',{}).get('author'):errors.append('review_not_independent')
    return {'valid':not errors,'errors':sorted(set(errors)),'candidate_not_executed':True}

def propose(state,mode):
    if mode not in {'O0','O1','O2','O3','O4'}:raise ValueError('Unknown condition')
    candidates=[];tasks=state['tasks'];members=sorted(state['members'])
    def add(op,selected,reason,**extra):
        candidates.append({'operation':op,'tasks':selected,'reason':reason,'evidence':list(state['evidence']),'cost_units':1,**extra})
    if mode=='O1':
        # One-time topology-derived handoff map, never a ToCoMAS reproduction.
        initial=state.get('initial_dependencies',[])
        for dep in initial:
            if dep['status'] in STRONG and dep['owners_differ']:add('AddHandoff',[dep['upstream'],dep['downstream']],'initial_topology_only')
    elif mode=='O3':
        if state.get('blocked_event_count',0)>=3:
            tid=state.get('focus','T1');owner=tasks[tid].get('owner');target=next(m for m in members if m!=owner)
            add('Reassign',[tid],'three_blocked_events',ownership_plan={tid:target})
        if state.get('same_path_writers',0)>=2:
            tids=list(tasks)[:2];add('Merge',tids,'multiple_same_path_writers',ownership_plan={t:members[0] for t in tids},cost_units=state.get('merge_cost',1))
    elif mode=='O4':
        for f in diagnose(state):
            if not f['execution_verified']:continue
            tid=f['task'];kind=f['kind']
            if kind=='DependencyMisalignment':add('AddHandoff',[f['upstream'],tid],kind)
            elif kind in {'ResponsibilityGap','CoordinationBottleneck'}:
                current=tasks[tid].get('owner');targets=[m for m in members if m!=current and state['members'][m].get('available')]
                if targets:add('Reassign',[tid],kind,ownership_plan={tid:targets[0]},cost_units=state.get('transfer_cost',1))
            elif kind=='OwnershipConflict':
                tids=f['tasks'];add('Split',tids,kind,ownership_plan={t:members[i%len(members)] for i,t in enumerate(tids)},cost_units=state.get('split_cost',1))
        if state.get('merge_evidence') and state.get('regions_coupled') and state.get('observed_handoff_loop') and state.get('predicted_saved_steps',0)>state.get('merge_cost',1):
            tids=list(tasks)[:2];add('Merge',tids,'coupled_regions_and_observed_rework',ownership_plan={t:members[0] for t in tids},cost_units=state.get('merge_cost',1))
        art=state.get('artifact')
        if art and art.get('independent_review_required') and art.get('adopted') and not art.get('review_accepted') and art.get('source_bound'):
            reviewer=next(m for m in members if m!=art['author']);add('AddReviewer',[art['task']],'exact_artifact_requires_review',reviewer=reviewer)
    candidates=candidates[:state['policy']['candidate_limit']]
    for c in candidates:c['validation']=validate(c,state)
    return {'condition':mode,'mismatches':diagnose(state) if mode in {'O2','O4'} else [],'candidates':candidates,
        'evaluated_candidates':len(candidates),'world_actions':0,'proxy_cost_is_not_tokens_or_money':True}

class TransferEvidence:
    """Receipt-driven migration observer; all mutations remain in existing Harness."""
    def __init__(self,package):
        required={'task_id','task_revision','old_owner','new_owner','project_region','code_version','artifacts','test_evidence','required_facts','unresolved_issues','provenance','permissions'}
        if not required<=set(package):raise ValueError('Incomplete migration package')
        if not package['provenance'] or package['old_owner']==package['new_owner']:raise ValueError('Unbound migration')
        if any(f.get('access') not in {'published_artifact','explicit_public_task'} for f in package['required_facts']):raise ValueError('Private memory cannot be copied as authorized evidence')
        self.package=copy.deepcopy(package);self.state='PROPOSED';self.history=[];self.offer=None
    def advance(self,target,receipt):
        order=['PROPOSED','AUTHORIZED','ACCEPTED','CONTEXT_TRANSFERRED','RESUMED','VERIFIED']
        if order.index(target)!=order.index(self.state)+1:raise ValueError('Migration cannot skip evidence stages')
        if not receipt.get('ok') or not receipt.get('source'):raise ValueError('Successful source-bound receipt required')
        p=self.package;r=receipt['result'];actor=receipt['actor'];tool=receipt['tool']
        if target=='AUTHORIZED':
            if tool!='offer_transfer' or actor!=p['old_owner'] or any(r.get(k)!=v for k,v in {'task_id':p['task_id'],'task_revision':p['task_revision'],'recipient':p['new_owner'],'from_member':p['old_owner']}.items()):raise ValueError('Offer does not bind exact responsibility')
            self.offer=r['offer_id']
        elif target=='ACCEPTED':
            if tool!='accept_transfer' or actor!=p['new_owner'] or receipt['arguments'].get('offer_id')!=self.offer or r.get('owner')!=actor or r.get('revision')!=p['task_revision']:raise ValueError('Acceptance does not bind original offer')
        elif target=='CONTEXT_TRANSFERRED':
            if tool!='read_file' or actor!=p['new_owner'] or r.get('source_reference')!=p['code_version']:raise ValueError('Recipient needs permitted original source')
            if not all(f['value'] in r.get('text','') for f in p['required_facts']):raise ValueError('Required facts missing from actual source read')
        elif target=='RESUMED':
            if tool!='integrate_patch' or actor!=p['new_owner'] or r.get('patch_id') not in p['artifacts']:raise ValueError('Recipient must actually adopt authorized artifact')
            self.recipient_version=r['source_reference']
        elif target=='VERIFIED':
            if tool!='run_tests' or actor!=p['new_owner'] or r.get('executed') is not True or r.get('passed') is not True or r.get('source_reference')!=self.recipient_version:raise ValueError('Exact resumed version lacks passed public test')
        self.history.append({'from':self.state,'to':target,'receipt':copy.deepcopy(receipt)});self.state=target
