"""Actual managed OpenHands context policies with one common private reader."""
from __future__ import annotations
import copy
from functools import cache
import inspect
import json
from pathlib import Path
import time
from types import FunctionType,MethodType

from . import software_benchmark_history_v117 as history
from . import software_benchmark_history_v110 as shared_history
from .software_context_compression_v175 import is_observation,canonical,digest,CONTEXT_READ_TOOL
from .software_context_reader_v179 import SourceLabeledHistoryReader
from .storage import atomic_write,json_bytes

VERSION='v181-live-sdk-private-context-policies-r1'
CONTEXT_TOOL=copy.deepcopy(CONTEXT_READ_TOOL)
CONTEXT_TOOL['function']['parameters']['properties']['reference']['pattern']='^ctx:[0-9a-f]{24}$'
CONTEXT_TOOL['function']['description']+=(' Reading a history archive at start=0 returns message_offsets for targeted '
    'reads. Copy exact citable_messages identities; source_identity distinguishes report schema and workspace versions. '
    'Old evidence is not current-version testing or permission.')


class ContextState:
    def __init__(self,worker,condition,*,count):
        self.worker,self.condition,self.count=worker,condition,count
        self.root=worker.directory/'context-management';self.root.mkdir(parents=True,exist_ok=True)
        self.store=SourceLabeledHistoryReader('whole-episode',worker.transport.owner.window_id,worker.role_id)
        self.saved=set();self.summary_records=[];self.failed_sources=set()
        self.latest_test=None;self.latest_delivery=None;self.epoch=None;self.change_turn=0
        self.last_summary_epoch=None;self.last_summary_end=0
        self.completed_cycles=0;self.actual_presentations=0;self.valid_reuses=0;self.historical_reuses=0

    def event(self,kind,**fields):
        value={'version':VERSION,'kind':kind,'unix':time.time(),**fields}
        with (self.root/'events.jsonl').open('a') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')

    def persist(self):
        folder=self.root/'evidence';folder.mkdir(exist_ok=True)
        for ref in self.store.entries.keys()-self.saved:
            path=folder/(ref.split(':')[1]+'.json')
            atomic_write(path,json_bytes({'reference':ref,'entry':self.store.entries[ref]}));self.saved.add(ref)
        atomic_write(self.root/'index.json',json_bytes({'episode_id':self.store.slot_id,'member_id':self.store.member_id,
            'references':sorted(self.saved),'condition':self.condition}))

    def update_epoch(self):
        source={}
        if self.worker._observation_texts:
            try:source=json.loads(self.worker._observation_texts[-1]).get('observation',{})
            except (ValueError,TypeError):pass
        value=digest({'workspace_source_reference':source.get('workspace_reference'),
            'public_test_evidence':self.latest_test,'publication_delivery':self.latest_delivery})
        if self.epoch is not None and self.epoch!=value:
            self.change_turn=self.completed_cycles
            self.event('critical_state_changed',previous_epoch=self.epoch,current_epoch=value,turn=self.completed_cycles)
        self.epoch=value;return value

    def note_action(self,name,response):
        if name=='run_tests':self.latest_test=digest(response)
        if name in {'fix_patch','submit_integration','staff_done'}:self.latest_delivery=digest({'tool':name,'response':response})

    def projection(self,request,*,original):
        selected=copy.deepcopy(request)
        if self.condition not in {'M1-5','M1-10'}:return selected,{'masked':[],'condition':self.condition}
        keep=5 if self.condition=='M1-5' else 10
        tools=[i for i,m in enumerate(selected['messages']) if m.get('role')=='tool']
        observations=[i for i,m in enumerate(selected['messages']) if is_observation(m)]
        if len(tools)<=keep:return selected,{'masked':[],'condition':self.condition}
        cutoff=tools[-keep];masked=[]
        for i in observations:
            if i>=cutoff or i==observations[0] or i==len(selected['messages'])-1:continue
            mapping=getattr(self,'selected_indices',None) or list(range(len(original['messages'])))
            source=original['messages'][mapping[i]]
            ref=self.store.put(source,mapping[i])
            marker='[Earlier private observation retained at '+ref+'. Use context_read for the exact original; it is historical evidence.]'
            if self.count(marker)>=self.count(selected['messages'][i]['content']):continue
            selected['messages'][i]['content']=marker
            masked.append({'index':i,'reference':ref,'source_sha256':digest(source)})
        self.persist()
        return selected,{'masked':masked,'condition':self.condition,'keep_complete_tool_cycles':keep,
            'original_actions_unchanged':True,'latest_observation_unchanged':True,'ordinary_summary_disabled':True}

    def archive_events(self,events):
        from openhands.sdk.event.base import LLMConvertibleEvent
        messages=shared_history._project_messages(LLMConvertibleEvent.events_to_messages(list(events)),self.worker)
        ref=self.store.put_history(messages,0,len(messages));self.persist()
        return ref,messages

    def summary_adopted(self,events,summary,archive_ref,body_id):
        from openhands.sdk.event import ObservationEvent
        self.last_summary_end+=sum(isinstance(e,ObservationEvent) for e in events)
        self.last_summary_epoch=self.epoch
        record={'summary_id':body_id,'archive_reference':archive_ref,'event_ids':[e.id for e in events],
            'covered_cycle_end':self.last_summary_end,'epoch_at_generation':self.epoch,
            'summary_sha256':digest(summary),'generated_at':time.time()}
        self.summary_records.append(record);self.event('summary_adopted',**record)

    def presented(self):
        self.actual_presentations+=1
        if self.summary_records:
            valid=self.last_summary_epoch==self.epoch
            self.valid_reuses+=bool(valid);self.historical_reuses+=not valid
            self.event('summary_presented',summary_id=self.summary_records[-1]['summary_id'],
                epoch_validity_proxy=valid,semantic_use_proven=False)

    def read(self,arguments):
        started=time.monotonic()
        try:
            value=self.store.read(arguments,point_id=self.store.point_id,slot_id=self.store.slot_id,member_id=self.store.member_id)
            response={'ok':True,'result':value,'world_effect':False,'new_world_read':False}
        except (ValueError,TypeError,PermissionError) as error:
            response={'ok':False,'error':{'code':'harness_tool_rejected','type':type(error).__name__,'message':str(error)},'world_effect':False}
        self.event('context_read',arguments=arguments,ok=response['ok'],wall_seconds=time.monotonic()-started,
            returned_characters=len(response.get('result',{}).get('text','')))
        return response

    def snapshot(self):
        return {'version':VERSION,'condition':self.condition,'archives':len(self.saved),
            'generated_adopted_summaries':len(self.summary_records),'actual_agent_presentations':self.actual_presentations,
            'epoch_validity_proxy_presentations':self.valid_reuses,'historical_only_presentations':self.historical_reuses,
            'effective_semantic_use_claimed':False,'completed_cycles':self.completed_cycles}


class ContextTransport(history.SummarizingManagedContextTransport):
    def select_for_member(self,request,member):
        worker=self._observation_sources_v117[member]
        selected,feedback,projection=history._select(request,self.feedback_ledger,member,worker._observation_texts)
        if not hasattr(worker,'context_state'):return selected,feedback,projection
        worker.context_state.selected_indices=feedback.get('selected_indices')
        value,extra=worker.context_state.projection(selected,original=request)
        projection={**projection,'context_treatment':extra,'context_method':worker.context_state.condition}
        return value,feedback,projection

    def prepare_for_budget(self,request):
        value=super().prepare_for_budget(request)
        worker=self._observation_sources_v117[self._turn['member_id']]
        value.update(context_policy_version=VERSION,context_condition=worker.context_state.condition,
            observation_projection_lossless=worker.context_state.condition=='M0')
        value.pop('preparation_sha256',None);value['preparation_sha256']=digest(json_bytes(value))
        self._prepared['measurement']=copy.deepcopy(value)
        return value


@cache
def condenser_type():
    from pydantic import PrivateAttr
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    from openhands.sdk.context.condenser.llm_summarizing_condenser import Reason
    from openhands.sdk.context.condenser.base import NoCondensationAvailableException
    from openhands.sdk.event import ActionEvent,ObservationEvent

    class RecoverableCondenser(shared_history.condenser_type()):
        _manager:object=PrivateAttr(default=None)

        def get_condensation_reasons(self,view,agent_llm=None):
            cycles=sum(isinstance(e,ObservationEvent) for e in view.events)
            self._manager.completed_cycles=self._manager.last_summary_end+cycles
            self._manager.update_epoch()
            reasons=super().get_condensation_reasons(view,agent_llm)
            if self._manager.condition=='M0':return reasons
            reasons.discard(Reason.EVENTS)
            if cycles>=31 or (self._manager.change_turn>self._manager.last_summary_end
                and self._manager.change_turn<=self._manager.completed_cycles-10):reasons.add(Reason.EVENTS)
            return reasons

        def _get_forgotten_events(self,view,agent_llm=None):
            if self._manager.condition=='M0':return super()._get_forgotten_events(view,agent_llm)
            observations=[(i,e) for i,e in enumerate(view.events) if isinstance(e,ObservationEvent)]
            if len(observations)<=10:raise NoCondensationAvailableException('The protected10 complete cycles cannot be summarized')
            index,event=observations[-10]
            matches=[i for i,e in enumerate(view.events[:index]) if isinstance(e,ActionEvent) and e.tool_call_id==event.tool_call_id]
            end=matches[-1] if matches else index
            floor=shared_history._protected_floor(view,self._trace,self.keep_first)
            end=min(end,floor);start=view.manipulation_indices.find_next(self.keep_first)
            ends=[i for i in view.manipulation_indices if start<i<=end]
            if not ends:raise NoCondensationAvailableException('No closed unprotected source prefix')
            end=max(ends)
            # Fit complete original events to the same model input bound. This
            # is prefix chunking, never character truncation of source evidence.
            from openhands.sdk.context.condenser import llm_summarizing_condenser as sdk
            def fits(stop):
                prompt=sdk.render_template(str(Path(sdk.__file__).parent/'prompts'),
                    'summarizing_prompt.j2',events=[str(e) for e in view.events[start:stop]])
                adapter=self._manager.worker.transport.owner.adapter
                wire=adapter.request([{'role':'user','content':prompt}],None)
                return adapter.count(wire)['prompt_tokens']<=98304
            if not fits(end):
                candidates=sorted(i for i in ends if i<end);low,high=0,len(candidates)-1;best=None
                while low<=high:
                    middle=(low+high)//2
                    if fits(candidates[middle]):best=candidates[middle];low=middle+1
                    else:high=middle-1
                if best is None:raise NoCondensationAvailableException('No complete original prefix fits the summary input limit')
                end=best
            return view.events[start:end],start

        def _generate_condensation(self,forgotten_events,summary_offset,max_event_str_length=None):
            if max_event_str_length is not None:raise ValueError('Never truncate source events to force summary fit')
            manager=self._manager;manager.update_epoch();source_key=digest([e.id for e in forgotten_events])
            if source_key in manager.failed_sources:raise NoCondensationAvailableException('This unchanged prefix already produced no useful summary')
            archive,messages=manager.archive_events(forgotten_events)
            self._trace.begin(forgotten_events)
            try:
                result=LLMSummarizingCondenser._generate_condensation(self,forgotten_events,summary_offset,None)
                if not isinstance(result.summary,str) or not result.summary.strip():raise ValueError('Summary is empty')
                header=(shared_history.SUMMARY_LABEL+'Original private actions and observations are available at '+archive+
                    '. Use context_read; keep report schema versions separate from workspace source versions. '
                    'Later complete observations supersede this historical summary.\n')
                result=result.model_copy(update={'summary':header+result.summary})
                self._trace.finish(result)
                if manager.condition=='M3-R' and manager.count(result.summary)>=manager.count(canonical(messages)):
                    manager.failed_sources.add(source_key);manager.event('summary_not_adopted',archive_reference=archive,reason='not_shorter')
                    raise NoCondensationAvailableException('Summary and fixed reference were not shorter')
                manager.summary_adopted(forgotten_events,result.summary,archive,result.llm_response_id)
                return result
            except NoCondensationAvailableException:raise
            except BaseException as error:
                self._trace.fail(error);raise

        def hard_context_reset(self,view,agent_llm=None):
            if self._manager.condition=='M0':return super().hard_context_reset(view,agent_llm)
            events,start=self._get_forgotten_events(view,agent_llm)
            return self._generate_condensation(events,start)
    return RecoverableCondenser


def bind_worker(worker,condition,count):
    from openhands.sdk.context.condenser import NoOpCondenser
    from pydantic import PrivateAttr
    original=worker.agent.condenser
    worker.context_state=ContextState(worker,condition,count=count)
    if condition in {'M1-5','M1-10'}:
        class TracedNoOp(NoOpCondenser):
            _trace:object=PrivateAttr(default=None)
            _manager:object=PrivateAttr(default=None)
            def condense(self,view,agent_llm=None):
                from openhands.sdk.event import ObservationEvent
                self._manager.completed_cycles=sum(isinstance(e,ObservationEvent) for e in view.events)
                self._trace.note_view(view)
                return view
        chosen=TracedNoOp();chosen._trace=worker._history_trace_v110;chosen._manager=worker.context_state
    else:
        values=original.model_dump(exclude={'kind','llm'})
        chosen=condenser_type()(llm=original.llm,**values)
        chosen._trace=worker._history_trace_v110;chosen._manager=worker.context_state
        if condition=='M3-R':chosen.keep_first=2
    with worker.conversation.state:
        agent=worker.agent.model_copy(update={'condenser':chosen})
        worker.agent=agent;worker.conversation.agent=agent;worker.conversation.state.agent=agent
    worker._history_policy_v117.update(context_policy=condition,context_runtime=VERSION,
        ordinary_periodic_summary_disabled=condition in {'M1-5','M1-10'},common_private_context_read=True)


def bind_private_reader(runtime):
    original=runtime.execute
    def execute(self,label,name,arguments,association):
        worker=self.policies[label]
        if name!='context_read':
            response=original(label,name,arguments,association)
            worker.context_state.note_action(name,response)
            return response
        self.deadline.check_hard('private_context_read');self._check_active(label,association)
        if self._active['executed']:raise ValueError('Only one scheduled private read per opportunity')
        self._active['executed']=True;self.actions+=1;self.roles[label]['actions']+=1
        decision={'kind':'act','action':name,'arguments':copy.deepcopy(arguments),**self._association(association)}
        response=worker.context_state.read(arguments)
        self.recorder.record('policy_decision',{'decision':decision,'harness':VERSION},worker_id=label)
        self.record_harness_call(label,{'action':name,'arguments':arguments,'response':response,'request_key':None},association)
        self.roles[label]['last_action']={'action':name,'arguments':copy.deepcopy(arguments)}
        self.roles[label]['last_result']=copy.deepcopy(response)
        self._active.update(decision=decision,response=copy.deepcopy(response))
        return response
    runtime.execute=MethodType(execute,runtime)
