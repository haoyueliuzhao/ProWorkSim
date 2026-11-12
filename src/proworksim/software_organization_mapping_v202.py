"""Project-to-Organization proposals, not live harness mutations or messages."""
from __future__ import annotations
import copy
from collections import defaultdict
from .software_syntax_facts_v202 import sha,SourceConflict

class OrganizationMapping:
    def __init__(self,*,members,regions,owners,handoffs=()):
        self.members=copy.deepcopy(members);self.regions=copy.deepcopy(regions);self.owners=dict(owners)
        self.handoffs=set(tuple(x) for x in handoffs);self.history=[]
        for task,owner in self.owners.items():
            if owner not in self.members or not self.members[owner].get('live'):raise SourceConflict('Unowned task or inactive owner')

    def snapshot(self):
        return {'members':copy.deepcopy(self.members),'regions':copy.deepcopy(self.regions),'owners':dict(self.owners),'handoffs':sorted(self.handoffs)}

    def proposals(self,project):
        candidates=[];tasks=project.state['tasks']
        def propose(operation,task_ids,reason,evidence,**fields):
            row={'operation':operation,'task_ids':sorted(task_ids),'reason':reason,'evidence_ids':sorted(set(evidence)),
                'status':'proposal_only','not_executed':True,**fields}
            row['candidate_id']='org:'+sha(row)[:24];candidates.append(row)
        for dependency in project.state['task_dependencies'].values():
            up,down=dependency['upstream'],dependency['downstream'];a,b=self.owners.get(up),self.owners.get(down)
            if a and b and a!=b and (up,down) not in self.handoffs:
                propose('AddHandoff',[up,down],'cross_owner_explicit_task_dependency_without_contract',dependency['source_ids'],sender=a,recipient=b)
        # Interpret these as heuristics over authoritative events, not measured optimality.
        writes=defaultdict(list)
        for e in project.events[-8:]:
            if e['kind']=='file_written':writes[e['data']['document']['path']].append(e)
        for path,events in writes.items():
            if len(events)>=3 and len({e['actor'] for e in events})>1:
                affected=[t for t,v in tasks.items() if path in v.get('targets',[])]
                if len(affected)>1:propose('Merge',affected,'repeated_cross_member_edits_in_same_path',[e['event_id'] for e in events],path=path)
        blocked=defaultdict(list);conflicts=defaultdict(list)
        for e in project.events:
            if e['kind']=='task' and e['data'].get('status')=='blocked':blocked[e['data']['id']].append(e)
            if e['kind']=='rejected_operation' and e['data'].get('reason') in {'version_conflict','interface_conflict'}:
                for task in e['data'].get('tasks',[]):conflicts[task].append(e)
        for task,events in blocked.items():
            downstream=[d['downstream'] for d in project.state['task_dependencies'].values() if d['upstream']==task]
            if len(events)>=3 and len(downstream)>=2 and tasks[task].get('status')=='blocked':
                old=self.owners.get(task);alternatives=[m for m,v in self.members.items() if v.get('live') and m!=old]
                if alternatives:propose('Reassign',[task],'three_recorded_blocks_with_multiple_dependents',[e['event_id'] for e in events[-3:]],old_owner=old,new_owner=sorted(alternatives)[0])
        for task,events in conflicts.items():
            if len(events)>=2:propose('AddReviewer',[task],'repeated_observed_handoff_conflicts',[e['event_id'] for e in events[-2:]])
        return [{**c,'validation':self.validate(c,tasks)} for c in candidates]

    def validate(self,candidate,tasks):
        errors=[];operation=candidate['operation'];selected=candidate['task_ids']
        if operation not in {'Reassign','Merge','Split','AddReviewer','AddHandoff','RemoveHandoff','ReassignIntegration'}:errors.append('unsupported_operation')
        if any(t not in tasks or t not in self.owners for t in selected):errors.append('missing_task_or_existing_owner')
        if operation in {'Reassign','ReassignIntegration'}:
            target=self.members.get(candidate.get('new_owner'),{})
            if not target.get('live'):errors.append('target_not_live')
            required={tool for task in selected for tool in tasks.get(task,{}).get('requires_tools',[])}
            if operation=='ReassignIntegration':required.add('submit_integration')
            if not required<=set(target.get('tools',[])):errors.append('target_lacks_required_managed_tools')
        if operation in {'Merge','Split'}:
            plan=candidate.get('ownership_plan',{})
            if set(plan)!=set(selected):errors.append('explicit_total_ownership_plan_required')
            for task,target_id in plan.items():
                target=self.members.get(target_id,{})
                if not target.get('live') or not set(tasks.get(task,{}).get('requires_tools',[]))<=set(target.get('tools',[])):errors.append('unsafe_owner_in_plan')
        if operation=='AddHandoff':
            sender,recipient=candidate.get('sender'),candidate.get('recipient')
            if sender==recipient or not all(self.members.get(m,{}).get('live') for m in [sender,recipient]):errors.append('invalid_participants')
            if not {sender,recipient}<={self.owners.get(t) for t in selected}:errors.append('participants_not_task_owners')
        if operation=='RemoveHandoff':
            # Removal needs a separate no-longer-required proof, never absence of an LLM mention.
            if candidate.get('dependency_removed_receipt') is None:errors.append('no_explicit_dependency_removal_evidence')
        return {'valid':not errors,'errors':errors,'live_mutation_authorized':False,
            'required_harness_steps':['offer_transfer','accept_transfer','scoped_evidence_handoff'] if operation in {'Reassign','ReassignIntegration','Merge','Split'} else ['scoped_handoff_or_review_receipt'],
            'unfinished_tasks_retain_existing_owners':True,'artifact_authorship_unchanged':True,'proposal_is_not_a_handoff_success':True}

    def synchronization_plan(self,project,impact,facts):
        affected={k.split('\0',1)[-1] for k in impact.get('potentially_affected',[])};receivers=set()
        for task,t in project.state['tasks'].items():
            if set(t.get('targets',[]))&affected and task in self.owners:receivers.add(self.owners[task])
        plans=[]
        for recipient in sorted(receivers):
            visible=[];withheld=0
            for fact in facts:
                allowed=fact.get('owner')==recipient or (recipient in fact.get('published_to',[]) and bool(fact.get('publication_receipt')))
                if allowed:
                    visible.append({'fact_id':fact['fact_id'],'source_ids':fact['source_ids'],'version':fact['version'],
                        'delivery_mode':'existing_private_source' if fact.get('owner')==recipient else 'published_artifact_copy_with_provenance',
                        'publication_receipt':fact.get('publication_receipt')})
                else:withheld+=1
            plans.append({'recipient':recipient,'facts':visible,'withheld_count':withheld,'sent':False,'presented':False,'read':False,'used':False,
                'source_versions_are_not_current_validation':True})
        return {'routes':plans,'transport_calls':0,'state':'plan_only','private_history_references_not_reused_across_members':True}
