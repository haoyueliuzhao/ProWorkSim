"""Frozen v181 baselines plus deterministic source-bound M1-5K projection."""
from . import software_context_runtime_v181 as original
from .software_context_critical_v191 import project,VERSION as CRITICAL_VERSION

VERSION='v193-live-critical-event-context-runtime-r1'
CONTEXT_TOOL=original.CONTEXT_TOOL
ContextTransport=original.ContextTransport
bind_private_reader=original.bind_private_reader


class CriticalState(original.ContextState):
    def projection(self,request,*,original):
        if self.condition!='M1-5K':return super().projection(request,original=original)
        value,proof=project(request,self.condition,self.store,count=self.count,
            original=original,selected_indices=getattr(self,'selected_indices',None))
        self.persist()
        return value,proof


def bind_worker(worker,condition,count):
    original.bind_worker(worker,'M1-5' if condition=='M1-5K' else condition,count)
    if condition=='M1-5K':
        worker.context_state=CriticalState(worker,condition,count=count)
        worker.agent.condenser._manager=worker.context_state
        worker._history_policy_v117.update(context_policy=condition,context_runtime=VERSION,
            critical_event_rule_version=CRITICAL_VERSION,ordinary_periodic_summary_disabled=True)
