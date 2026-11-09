"""Persistent summary planning and conservative validity accounting, no model I/O.

Actual SDK routing and original-prefix binding are separate deployment gates.
An epoch-valid reuse is an operational proxy, not proof of semantic use.
"""
import copy
import json
from pathlib import Path

from .software_context_compression_v175 import canonical,digest
from .storage import atomic_write,json_bytes

VERSION='v180-persistent-summary-lifecycle-core-r1'
EPOCH_FIELDS=('workspace_tree_sha256','public_test_evidence_id','delivery_version_id')


class SummaryLifecycle:
    def __init__(self,path,*,episode_id,member_id,new_turns=21,recent_turns=10):
        self.path=Path(path)
        identity={'episode_id':episode_id,'member_id':member_id,'new_turns':new_turns,'recent_turns':recent_turns}
        if self.path.exists():
            self.state=json.loads(self.path.read_bytes())
            if self.state['identity']!=identity:raise ValueError('Summary lifecycle belongs to another private episode')
        else:self.state={'version':VERSION,'identity':identity,'current_epoch':None,'critical_changes':[],
            'summaries':[],'active_summary':None,'request_records':{},'last_observed_turn':0}

    def save(self):atomic_write(self.path,json_bytes(self.state))

    def observe(self,completed_turns,state_identity):
        if completed_turns<self.state['last_observed_turn']:raise ValueError('History cannot move backwards')
        if set(state_identity)!=set(EPOCH_FIELDS):raise ValueError('Use only the declared critical state fields')
        epoch=digest(state_identity);old=self.state['current_epoch']
        if old is not None and old!=epoch:self.state['critical_changes'].append({'turn':completed_turns,'from':old,'to':epoch})
        self.state.update(current_epoch=epoch,last_observed_turn=completed_turns);self.save()
        return {'epoch':epoch,'changed':old is not None and old!=epoch}

    def plan(self,*,actual_input_tokens):
        current=self.state['active_summary'];covered=current['covered_through_turn'] if current else 0
        total=self.state['last_observed_turn'];keep=self.state['identity']['recent_turns'];end=total-keep
        changed_leaving_tail=any(covered<c['turn']<=end for c in self.state['critical_changes'])
        reason=('turn_threshold' if total-covered>=self.state['identity']['new_turns']+keep else
            'critical_change_leaving_recent_tail' if changed_leaving_tail else
            'context_pressure' if actual_input_tokens>98304 else None)
        if reason and end>covered:
            return {'action':'summarize','reason':reason,'new_source_turn_range':[covered+1,end],
                'keep_recent_turns':keep,'previous_summary_id':current['summary_id'] if current else None}
        return {'action':'reuse' if current else 'keep_original','reason':None,
            'working_state_validity_proxy':bool(current and current['source_epoch']==self.state['current_epoch']),
            'summary_is_historical_when_epoch_changed':bool(current and current['source_epoch']!=self.state['current_epoch'])}

    def install(self,*,text,covered_through_turn,source_epoch,source_sha256,archive_reference,request_id,usage,created_at):
        old=self.state['active_summary'];prior=old['covered_through_turn'] if old else 0
        if not prior<covered_through_turn<=self.state['last_observed_turn']-self.state['identity']['recent_turns']:
            raise ValueError('Preserve the entire recent tail and advance the covered source')
        if not text or not archive_reference.startswith('ctx:') or len(source_sha256)!=64:
            raise ValueError('Persistent summaries need text and an original source binding')
        if usage['input_tokens']+usage['output_tokens']!=usage['total_tokens']:
            raise ValueError('Summary usage must reconcile without double counting')
        item={'summary_id':'summary-'+str(len(self.state['summaries'])+1),'text':text,
            'covered_through_turn':covered_through_turn,'source_epoch':source_epoch,
            'source_sha256':source_sha256,'archive_reference':archive_reference,'request_id':request_id,
            'usage':copy.deepcopy(usage),'created_at':created_at,'supersedes':old['summary_id'] if old else None}
        self.state['summaries'].append(item);self.state['active_summary']=item;self.save();return item

    def note_settled_request(self,*,request_id,logical_decision_id,summary_id,usage):
        active=self.state['active_summary']
        if not active or active['summary_id']!=summary_id:raise ValueError('Bind the actual presented summary version')
        record={'logical_decision_id':logical_decision_id,'summary_id':summary_id,'usage':copy.deepcopy(usage),
            'source_epoch':active['source_epoch'],'current_epoch':self.state['current_epoch'],
            'epoch_validity_proxy':active['source_epoch']==self.state['current_epoch']}
        previous=self.state['request_records'].get(request_id)
        if previous is not None and previous!=record:raise ValueError('A settled request changed')
        self.state['request_records'][request_id]=record;self.save()

    def metrics(self):
        records=list(self.state['request_records'].values())
        valid={(r['summary_id'],r['logical_decision_id']) for r in records if r['epoch_validity_proxy']}
        return {'generated_summaries':len(self.state['summaries']),'physical_presentations':len(records),
            'epoch_valid_distinct_decision_reuses':len(valid),
            'historical_only_presentations':sum(not r['epoch_validity_proxy'] for r in records),
            'summary_input_tokens':sum(r['usage']['input_tokens'] for r in self.state['summaries']),
            'summary_output_tokens':sum(r['usage']['output_tokens'] for r in self.state['summaries']),
            'critical_state_changes':len(self.state['critical_changes']),
            'is_semantic_use_certification':False}
