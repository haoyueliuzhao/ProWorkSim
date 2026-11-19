"""Explicit continuation stage and bounded quiescence correction; no world actions."""
import inspect,json
from types import SimpleNamespace
from . import software_organization_runtime_v216_2 as prior
from .software_fixed_organization_clone_v131 import clone_function
from .storage import digest,json_bytes
VERSION='v218-stage-boundary-bounded-wait-r1'
STAGE_MESSAGE=('CONTINUATION STAGE: the common-prefix preparation phase is OVER. Any earlier instruction to reach a prefix checkpoint, pause after the first test, or await a continuation instruction has expired. This message IS the continuation instruction. Finish the original task under the assigned organization and remaining shared budget. A passing local test or completed prefix is not task completion. Inspect dynamic_status, your work_readiness and delivery_readiness; carry out your own pending legal obligations and coordinate with the other actual member. Only an accepted submit_integration completes delivery; an explicit abort is distinct. Do not wait merely because prefix objectives were met. Never fabricate acceptance, evidence, tool results, or another member action.')
CONTRACT=prior.CONTRACT
build_team_owner=prior.build_team_owner;build_runtime=prior.build_runtime;close_runtime=prior.close_runtime;lock_fixed_candidates=prior.lock_fixed_candidates;set_native_limit=prior.set_native_limit;member_wire_tools=prior.member_wire_tools

def enter_continuation(runtime):
 runtime.run_stage='continuation';runtime.stage_wait_guard={'notifications':0,'seen':set(),'events':[]}
 for policy in runtime.policies.values():policy.conversation.send_message(STAGE_MESSAGE)
 runtime.recorder.record('continuation_stage_entered',{'version':VERSION,'prior_prefix_goal_expired':True,'world_actions':0})

def correct_quiescence(prepared,runtime):
 if getattr(runtime,'run_stage',None)!='continuation' or prepared.world.protocol()['terminal'] is not None:return False
 guard=runtime.stage_wait_guard
 if guard['notifications']>=2:return False
 # Never revive a fatal/stopped member or bypass cash, time or token checks.
 members=[m for m in runtime.labels if m in runtime.waiting and m not in runtime.stopped]
 if not members:return False
 state_id=digest(json_bytes(prepared.world.dynamic()))
 if state_id in guard['seen']:return False
 # Send no private state or peer notes: members obtain their own authorized tools.
 text=STAGE_MESSAGE+' The scheduler observed that no member is runnable while no terminal delivery/abort exists. Re-check whether you can legally advance your own unfinished work. If genuinely blocked, state the concrete dependency and wait; no automatic submission or responsibility transfer occurs.'
 for m in members:
  runtime.policies[m].conversation.send_message(text)
  runtime.waiting.pop(m,None);runtime.work_ended.pop(m,None)
 guard['notifications']+=1;guard['seen'].add(state_id)
 event={'notification':guard['notifications'],'state_id':state_id,'members':members,'world_actions':0,'cost_charged_on_next_request':True}
 guard['events'].append(event);runtime.recorder.record('bounded_quiescence_notice',event)
 return True

# Clone the already validated terminal-aware loop; existing runtimes unchanged.
_base=prior.run_fragment.__globals__['base']
source=prior._terminal_source
needle='        if selection is None:\n'
assert source.count(needle)==1
source=source.replace(needle,needle+'            if correct_quiescence(prepared, runtime):\n                continue\n',1)
ns={**_base.run_fragment.__globals__,'correct_quiescence':correct_quiescence}
exec(compile(source,__file__+':bounded-loop','exec'),ns)
new_base=SimpleNamespace(**{**vars(_base),'run_fragment':ns['run_fragment']})
_run=clone_function(prior.run_fragment,{**prior.run_fragment.__globals__,'base':new_base})
def run_fragment(prepared,runtime,*,on_opportunity=None):
 result=_run(prepared,runtime,on_opportunity=on_opportunity)
 guard=getattr(runtime,'stage_wait_guard',None)
 result['stage_revision']=VERSION
 result['stage_wait_corrections']=guard['events'] if guard else []
 if result['closure_reason']=='all_members_stopped_or_no_reachable_event' and prepared.world.protocol()['terminal'] is None:
  result['termination_class']='quiescent_without_delivery'
 else:result['termination_class']=result['closure_reason']
 return result
