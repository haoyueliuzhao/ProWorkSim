"""Outcome-blind identity sampling and source-bounded reviewer packets."""
import collections,copy,json,sys
from pathlib import Path
from inventory_multimember_v203 import ROOT,BATCH,read,ref,save,sha
ART=ROOT/'artifacts/software-benchmark-v203-1'
RUN=ROOT/'runs/software-benchmark-v203-1'
SEED='v203.1-20261112-no-handoff-selection'
def rank(value):return sha((SEED+value).encode())
def balanced(ids,repo,n):
    groups={r:sorted([x for x in ids if repo[x]==r],key=rank) for r in set(repo[x] for x in ids)};out=[]
    while len(out)<n:
        changed=False
        for r in sorted(groups,key=rank):
            if groups[r]:out.append(groups[r].pop(0));changed=True
            if len(out)==n:break
        if not changed:break
    return out
def clip(v,limit=1600):
    if isinstance(v,str):return v if len(v)<=limit else v[:limit]+f' [excerpt; {len(v)} original characters; full prefix available]'
    if isinstance(v,list):return [clip(x,limit) for x in v]
    if isinstance(v,dict):return {k:clip(x,512 if k in {'text','body','message','description'} else limit) for k,x in v.items()}
    return v
def main():
    plan=read(BATCH/'execution-plan.json')['rows'];old={r['instance_id'] for r in read(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/selection.json')}
    available=collections.defaultdict(list);repo={}
    for r in plan:
        repo[r['instance_id']]=r['repo'];p=BATCH/f'episodes/{r["slot_index"]}/controller-output/controller-result.json'
        if p.exists():available[r['instance_id']].append((r,p))
    validation=balanced(set(available)-old,repo,12);development=balanced(set(available)-set(validation),repo,24)
    assert len(validation)==12 and len(development)==24 and not set(validation)&old
    chosen=[];mode_counts=collections.Counter()
    for split,ids in [('development',development),('validation',validation)]:
        for iid in ids:
            r,p=min(available[iid],key=lambda rp:(mode_counts[rp[0]['organization_id']],rank(rp[0]['slot_id'])))
            mode_counts[r['organization_id']]+=1;chosen.append({'split':split,**{k:r[k] for k in ['instance_id','repo','organization_id','slot_id','slot_index','fixed_members']},'controller':str(p)})
    # Freeze identities and rules before any collaboration outcomes are inspected.
    save(ART/'panel-r1/plan.json',{'seed':SEED,'rows':chosen,'source_plan':ref(BATCH/'execution-plan.json'),
        'eligibility':'controller file existence only; no action, task-board, handoff, test, cash or score prerequisite',
        'validation_excludes_v203_twelve_tasks':True,'development_tasks':24,'validation_tasks':12,'warehouses_unseen_over_research_history':False,
        'source_scope':'original50 panel,46 with at least one controller; one attempt per task, no score-based retry selection',
        'prefix':'first40 dispatched tool actions, or all available when shorter; no future or terminal official score supplied',
        'review':'two independent AI reviewers; disagreements arbitrated; no human-gold claim; outputs blind to O4 and split',
        'source':ref(Path(__file__)),'new_model_API':0})
    inventory=read(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/inventory.json');lookup={x['slot_index']:x for x in inventory};diagnostics=[];index=[]
    for no,row in enumerate(sorted(chosen,key=lambda r:rank(r['slot_id']))):
        case=f'OBS{no+1:03}';p=Path(row['controller']);d=read(p);controller_ref=ref(p);full=[]
        for i,o in enumerate(d.get('managed_boundary',{}).get('outcomes',[])):
            dec=o.get('decision',{});resp=o.get('response',{})
            if not dec.get('action') or not o.get('action_performed'):continue
            full.append({'event_id':f'{case}:E{len(full)+1:03}','outcome_index':i,'actor':o['worker_id'],'action':dec['action'],'arguments':dec.get('arguments',{}),
                'ok':resp.get('ok'),'result':resp.get('result'),'error':resp.get('error'),'logical_time':resp.get('logical_time'),'command_id':resp.get('command_id'),
                'source':{'controller':controller_ref,'pointer':f'/managed_boundary/outcomes/{i}'}})
            if len(full)==40:break
        root_manifest=p.parent/'source-snapshot/source-manifest.json';goal=read(root_manifest)['tasks'][0]['problem_statement'] if root_manifest.exists() else None
        packet={'case_id':case,'instance_id':row['instance_id'],'repo':row['repo'],'organization':row['organization_id'],'members':row['fixed_members'],
            'issue':goal,'source_controller':ref(p),'private_sessions':d.get('private_sessions'),
            'organization_contract':d.get('execution_alignment',{}).get('organization'),
            'events':full,'prefix_complete_for_dispatched_actions':True,'cut_action_count':len(full),'future_actions_and_terminal_scores_omitted':True,
            'interpretation':'No task board alone is not an ownership gap; a fixed published patch may be directly adopted without handoff. Missing evidence must not be called no collaboration. Public test failure alone does not identify an organizational cause.'}
        save(RUN/f'review-packets-r1/{case}.json',packet)
        brief={**packet,'issue':clip(goal,1400),'events':clip(full)};save(RUN/f'review-briefs-r1/{case}.json',brief)
        r=lookup[row['slot_index']];adopt=r.get('source_bound_adoptions',[]);handoff=r.get('source_bound_handoffs',[])
        diagnostics.append({'case_id':case,'split':row['split'],'instance_id':row['instance_id'],'repo':row['repo'],'mode':row['organization_id'],
            'controller':ref(p),'prefix_actions':len(full),'has_successful_handoff_full_attempt':any(x['source_bound'] for x in handoff),
            'has_successful_adoption_full_attempt':any(x['source_bound'] for x in adopt),'explicit_owned_task_full_attempt':r.get('criteria',{}).get('explicit_owned_task'),
            'actual_executed_members':len(r.get('actual_active_members',[])),'raw_model_requests_available':r.get('raw_member_requests_available'),
            'prior_v203_main_eligible':r.get('admitted'),'evaluation_use':'sampling diagnostics only; excluded from reviewer prefix and predictive features'})
        index.append({'case_id':case,'packet':ref(RUN/f'review-packets-r1/{case}.json'),'brief':ref(RUN/f'review-briefs-r1/{case}.json')})
    save(ART/'panel-r1/reviewer-index.json',index);save(ART/'panel-r1/selection-diagnostics.json',diagnostics)
    save(ART/'panel-r1/summary.json',{'distinct_tasks':36,'by_split':dict(collections.Counter(r['split'] for r in chosen)),
        'modes':dict(mode_counts),'repos':len(set(r['repo'] for r in chosen)),'prefixes_without_successful_handoff_requirement':True,
        'full_attempt_no_handoff':sum(not r['has_successful_handoff_full_attempt'] for r in diagnostics),
        'direct_adoption_without_handoff':sum(r['has_successful_adoption_full_attempt'] and not r['has_successful_handoff_full_attempt'] for r in diagnostics),
        'not_eligible_under_old_v203_successful_chain_rule':sum(not r['prior_v203_main_eligible'] for r in diagnostics),
        'validation_unseen_repos_relative_to_v203':sorted(set(r['repo'] for r in chosen if r['split']=='validation')-{repo[x] for x in old}),
        'validation_repo_isolation':'not guaranteed; all source-panel repositories have prior research exposure; report exact overlap separately'})
    print('Prepared36 prefixes, task-disjoint24/12; no success-chain filter.')
if __name__=='__main__':main()
