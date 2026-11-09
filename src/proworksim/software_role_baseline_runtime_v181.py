"""S1's actual SDK/runtime, extended only with frozen private context policies."""
import copy
import inspect
from pathlib import Path
from . import software_role_baseline_runtime_v156 as observed
from .software_collaboration_runtime_observer_v172 import RuntimeObservationBridge
from .software_context_sources_v181 import SDKRequestCapture
from types import FunctionType

from . import software_role_baseline_runtime_v141 as previous
from .software_context_runtime_v181 import CONTEXT_TOOL,bind_worker,bind_private_reader
from .software_benchmark_alignment_contract_v181 import GROUP_IDS,condition,shared_strategy

VERSION=REPAIR_REVISION='v181-real-S1-context-policy-runtime-r1'
prepare_case=previous.prepare_case
close_runtime=observed.close_runtime
lock_fixed_candidates=observed.lock_fixed_candidates
worker_config=previous.worker_config


def member_wire_tools(group,member):
    tools=previous.member_wire_tools('S1',member)
    return tools[:-len(previous.CONTROL_TOOLS)]+[copy.deepcopy(CONTEXT_TOOL)]+tools[-len(previous.CONTROL_TOOLS):]


def prepare_schema_inventory():
    return {'version':VERSION,'schemas':{g:{'member_001':member_wire_tools('S1','member_001')} for g in GROUP_IDS},
        'generation_calls':0,'common_private_reader':True,'world_permissions_unchanged':True}


def worker_type(context_condition='M0',content_counter=None):
    class ContextWorker(observed.worker_type()):
        def __init__(self,role_id,tools,config,**kwargs):
            super().__init__(role_id,[*tools,copy.deepcopy(CONTEXT_TOOL['function'])],config,**kwargs)
            if content_counter is None:raise ValueError('Use the frozen actual content tokenizer')
            bind_worker(self,context_condition,content_counter)

        def _complete(self,messages,tools):
            self.context_state.update_epoch()
            value=super()._complete(messages,tools)
            self.context_state.presented()
            return value

        def snapshot(self):
            value=super().snapshot()
            if hasattr(self,'context_state'):value['context_management']=self.context_state.snapshot()
            return value
    return ContextWorker


_owner_builder=FunctionType(observed.build_team_owner.__code__,
    {**observed.build_team_owner.__globals__,'member_wire_tools':member_wire_tools,
     'RuntimeObservationBridge':RuntimeObservationBridge})
_owner_builder.__kwdefaults__=observed.build_team_owner.__kwdefaults__


def build_team_owner(post,*,context_condition,**kwargs):
    if kwargs.get('organization_id')!='S1' or context_condition not in GROUP_IDS:raise ValueError('Only a frozen S1 condition may enter')
    capture=SDKRequestCapture(Path(kwargs['folder'])/'request-capture-v181')
    owner=_owner_builder(post,request_capture=capture.request,response_callback=capture.response,**kwargs)
    owner.context_condition=context_condition;owner.context_counter=kwargs.get('observation_token_counter')
    owner.source_capture_v181=capture
    return owner


_build_source=inspect.getsource(previous.build_runtime).replace(
    'from .software_benchmark_history_v117 import AlignedManagedTeamBudget, SummarizingManagedContextTransport',
    'from .software_benchmark_history_v117 import AlignedManagedTeamBudget\n    from .software_context_runtime_v181 import ContextTransport as SummarizingManagedContextTransport')
_build_source=_build_source.replace("shared_strategy(owner.spec['id'])","shared_strategy(owner.context_condition)")
_build_namespace={**previous.build_runtime.__globals__,'member_wire_tools':member_wire_tools,'shared_strategy':shared_strategy}
exec(compile(_build_source,__file__+':same-S1-SDK-construction','exec'),_build_namespace)
_build=_build_namespace['build_runtime']


def build_runtime(owner,*args,**kwargs):
    factory=worker_type(owner.context_condition,owner.context_counter)
    def tracked(member,*args,**kw):
        worker=factory(member,*args,**kw);owner._v156_workers[member]=worker;return worker
    kwargs['worker_factory']=tracked
    runtime,captured,interfaces=_build(owner,*args,**kwargs)
    bind_private_reader(runtime)
    return runtime,captured,interfaces


run_fragment=observed.run_fragment
