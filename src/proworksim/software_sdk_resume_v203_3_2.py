"""Explicit JSON checkpoints for the pinned two-member SDK and managed world.

No tool replay, pickle, provider request, world mutation or clock refill on load.
Logical prefix identities remain immutable; branch adapter IDs scope new calls.
"""
from __future__ import annotations
import copy,json,shutil,time,uuid
from pathlib import Path
from .storage import json_bytes,digest
from .software_branch_checkpoint_v203_3_1 import manifest

VERSION='v203.3.2-settled-team-SDK-resume-r2'
# The old factory returns an identical-behavior local class. SDK deserialization
# rejects <locals> types. Export that exact cached class at a stable module path;
# no condenser methods, prompt, thresholds, or saved events are replaced.
def register_persistence_types():
    # Initialize only after the batch has set its private SDK persistence path.
    from .software_benchmark_history_v110 import condenser_type
    cls=condenser_type();cls.__module__=__name__;cls.__qualname__='AlignedHistoryCondenser'
    globals()['AlignedHistoryCondenser']=cls
RUNTIME_FIELDS=('run_id','actions','opportunities','cursor','roles','policy_identities','waiting','stopped',
    'terminal_details','birth_records','work_ended','work_boundaries','_selected','organization_blocked')
WORKER_FIELDS=('_observation_texts','_assistant_messages','meter','_sdk_events','_done','_identity',
    '_identity_epoch','format_errors','_history_policy_v117','_v117_pending_finish_review')
PORT_FIELDS=('notes','todos','history','reads','latest','_requests')

def encode(x):
    if isinstance(x,set):return {'__set__':[encode(v) for v in sorted(x)]}
    if isinstance(x,tuple):return {'__tuple__':[encode(v) for v in x]}
    if isinstance(x,dict):return {'__dict__':[[encode(k),encode(v)] for k,v in x.items()]}
    if isinstance(x,list):return [encode(v) for v in x]
    if x is None or type(x) in (str,int,float,bool):return x
    raise TypeError(type(x).__name__)

def decode(x):
    if isinstance(x,dict):
        if '__set__' in x:return set(decode(v) for v in x['__set__'])
        if '__tuple__' in x:return tuple(decode(v) for v in x['__tuple__'])
        return {decode(k):decode(v) for k,v in x['__dict__']}
    if isinstance(x,list):return [decode(v) for v in x]
    return x

def fields(obj,names):return {k:copy.deepcopy(getattr(obj,k)) for k in names if hasattr(obj,k)}
def apply(obj,state):
    for key,value in state.items():setattr(obj,key,copy.deepcopy(value))
def json_attrs(obj):
    out={}
    for key,val in vars(obj).items():
        try:encode(val)
        except TypeError:continue
        out[key]=copy.deepcopy(val)
    return out

def save(prepared,runtime,path,*,control_state=None):
    register_persistence_types()
    path=Path(path);path.mkdir(parents=True,exist_ok=False)
    if runtime._in_step or runtime.owner.adapter.ledger.inflight is not None:
        raise ValueError('Save only between settled opportunities')
    if runtime.team_budget.snapshot()['held_tokens']:raise ValueError('Outstanding reservation')
    now=runtime.deadline.clock()
    state={'version':VERSION,'runtime':fields(runtime,RUNTIME_FIELDS),
        'schedule':fields(runtime.schedule,('position','executed','skipped')),
        'team_state':copy.deepcopy(runtime.team_budget._state),'workers':{},
        'clock':{'elapsed':now-runtime.deadline.started,'soft_remaining':runtime.deadline.soft_at-now,
                 'hard_remaining':runtime.deadline.hard_at-now,'pause_policy':'exclude checkpoint IO and process downtime; same remainder for each branch'},
        'control_state':control_state,'prefix_ledger':runtime.owner.adapter.ledger.snapshot(),
        'public_test_calls':prepared.source_provider.runner.calls,
        'test_budget':fields(prepared.world.test_budget,('limit','members','records')),
        'world_state_sha256':digest(json_bytes(prepared.world.store.load()))}
    runtime.owner.save()
    with prepared.world.store.lock():shutil.copytree(prepared.world.store.root,path/'world')
    for member,w in runtime.policies.items():
        trace=w._history_trace_v110
        if trace.pending or trace.failure or w._in_step:raise ValueError('Unsettled private summary')
        shutil.copytree(w.directory,path/'workers'/member)
        adapter=runtime.owner.adapters[member]
        state['workers'][member]={'worker':fields(w,WORKER_FIELDS),'config':w.config,
            'agent_tools':[t.model_dump(mode='json') for t in w.agent.tools],
            'condenser':w.agent.condenser.model_dump(mode='json',exclude={'llm'}),
            'system_prompt':w.agent.system_prompt,'conversation_id':str(w.conversation.id),
            'port':fields(runtime.ports[member],PORT_FIELDS),'accountant':json_attrs(w._accountant),
            'transport':fields(w.transport,('counter',)),
            'feedback':json_attrs(w.transport.feedback_ledger),
            'trace':fields(trace,('counter','derived_events','presented_event_ids','current_view_ids')),
            'adapter_ledger':json_attrs(adapter.ledger),'adapter_history':json_attrs(adapter.history),
            'review_policy':fields(runtime.finish_review_policies[member],('used','events','intent_ids'))}
    (path/'state.json').write_bytes(json_bytes(encode(state)))
    hashes=manifest(path)
    proof={'version':VERSION,'files':hashes,'identity':digest(json_bytes(hashes)),
        'world_state_sha256':state['world_state_sha256'],'prefix_tokens':state['prefix_ledger']['known_actual_tokens'],
        'summary_count':sum(v['trace']['counter'] for v in state['workers'].values()),'new_API_calls':0}
    (path/'manifest.json').write_bytes(json_bytes(proof));return proof

def read(path):
    path=Path(path);proof=json.loads((path/'manifest.json').read_text())
    if proof.get('version')!=VERSION:raise ValueError('Incomplete earlier checkpoints are not silently repaired')
    actual=manifest(path);actual.pop('manifest.json')
    if actual!=proof['files'] or digest(json_bytes(actual))!=proof['identity']:
        raise ValueError('Changed checkpoint')
    return decode(json.loads((path/'state.json').read_text())),proof

def restore_world(prepared,path):
    state,proof=read(path)
    shutil.copytree(Path(path)/'world',prepared.world.store.root,dirs_exist_ok=True)
    prepared.world.state=prepared.world.store.load()
    prepared.source_provider.runner.calls=state['public_test_calls']
    apply(prepared.world.test_budget,state['test_budget'])
    if digest(json_bytes(prepared.world.state))!=state['world_state_sha256']:raise ValueError('World mismatch')
    return state,proof

def reset_clock(runtime,prepared,clock):
    now=runtime.deadline.clock();d=runtime.deadline
    d.started=now-clock['elapsed'];d.soft_at=now+clock['soft_remaining'];d.hard_at=now+clock['hard_remaining']
    d.last_clock=now
    prepared.source_provider.runner.hard_at=d.hard_at
    for adapter in runtime.owner.adapters.values():adapter.soft_at,adapter.hard_at=d.soft_at,d.hard_at
    for p in runtime.finish_review_policies.values():p.started={'started':d.started,'soft_at':d.soft_at,'hard_at':d.hard_at}

def restore_runtime(prepared,runtime,path):
    register_persistence_types()
    from openhands.sdk import Conversation
    from openhands.sdk.tool import Tool
    from openhands.sdk.tool.registry import register_tool,resolve_tool
    from openhands.sdk.tool.schema import Action
    from .harness_sdk import _ManagedTool
    from typing import ClassVar
    path=Path(path);state,proof=read(path)
    if runtime.opportunities or runtime.owner.adapter.ledger.attempts:
        raise ValueError('Restore only into a fresh, never-dispatched branch')
    apply(runtime,state['runtime']);apply(runtime.schedule,state['schedule'])
    runtime.team_budget._state=copy.deepcopy(state['team_state'])
    for member,w in runtime.policies.items():
        saved=state['workers'][member]
        current=w.conversation
        originals=[Tool.model_validate(t) for t in saved['agent_tools']]
        for index,(old,new) in enumerate(zip(originals,w.agent.tools,strict=True)):
            instances=resolve_tool(new,current.state)
            if len(instances)!=1:raise ValueError('One managed tool per registration')
            if not old.name.startswith('pws_'):raise ValueError('Unrecognized saved tool registration')
            action=Action.from_mcp_schema('ManagedAction_'+old.name[4:],w.definitions[index]['parameters'])
            tool_type=type('ManagedTool_'+old.name[4:],(_ManagedTool,),
                {'name':instances[0].name,'__annotations__':{'name':ClassVar[str]}})
            values={k:getattr(instances[0],k) for k in type(instances[0]).model_fields if k!='kind'}
            values['action_type']=action
            register_tool(old.name,tool_type(**values))
        fresh_directory=w.directory/'conversations'/str(current.id).replace('-','')
        current.close()
        # A fresh constructor was only used to bind trusted executors; its empty
        # private session is not part of the restored conversation history.
        if fresh_directory.exists():shutil.rmtree(fresh_directory)
        shutil.copytree(path/'workers'/member,w.directory,dirs_exist_ok=True)
        for k,v in saved['condenser'].items():
            if k!='kind':setattr(w.agent.condenser,k,v)
        w.agent=w.agent.model_copy(update={'tools':originals,'system_prompt':saved['system_prompt']})
        w.agent._initialized=False;w.agent._tools={}
        w.conversation=Conversation(agent=w.agent,workspace=w.directory/'workspace',
            persistence_dir=w.directory/'conversations',conversation_id=uuid.UUID(saved['conversation_id']),
            callbacks=[w._on_sdk_event],plugins=[],max_iteration_per_run=current.max_iteration_per_run,
            stuck_detection=False,visualizer=None)
        # The SDK reloads the serialized persistence_dir even when its FileStore
        # already points to the new branch. Rebind this storage-only location so
        # future helpers cannot follow a stale parent directory.
        with w.conversation.state:
            w.conversation.state.persistence_dir=str((w.directory/'conversations'/uuid.UUID(saved['conversation_id']).hex).resolve())
        apply(w,saved['worker']);apply(w._accountant,saved['accountant'])
        apply(runtime.ports[member],saved['port']);apply(w.transport,saved['transport'])
        apply(w.transport.feedback_ledger,saved['feedback'])
        trace=w._history_trace_v110
        trace.counter=0;trace.event_provider=None;trace.bind_conversation(w.conversation)
        apply(trace,saved['trace'])
        # Rebind both real private adapters to the restored SDK context.
        for llm in (w.agent.llm,w.agent.condenser.llm):
            if llm.usage_id not in w.conversation.llm_registry.list_usage_ids():w.conversation.llm_registry.add(llm)
            w.conversation._bind_conversation_context(llm)
        apply(runtime.owner.adapters[member].ledger,saved['adapter_ledger'])
        apply(runtime.owner.adapters[member].history,saved['adapter_history'])
        apply(runtime.finish_review_policies[member],saved['review_policy'])
        trace.assert_bound_to(w.conversation)
    reset_clock(runtime,prepared,state['clock'])
    if runtime.team_budget.snapshot()['charged_tokens']!=state['prefix_ledger']['known_actual_tokens']:
        raise ValueError('Prefix budget charge changed')
    runtime.owner.save()
    return {'version':VERSION,'checkpoint_identity':proof['identity'],'prefix_tokens':proof['prefix_tokens'],
        'physical_branch_namespace':runtime.owner.window_id,'logical_prefix_preserved':True,
        'no_resume_message_added':True,'world_actions_replayed':0,'prefix_recharged':False,
        'remaining_time_at_resume':state['clock']}
