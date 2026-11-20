"""Reject reserved model arguments before execution, with budgeted feedback."""
import json
from functools import cache
from . import software_organization_runtime_v218 as prior
from . import software_organization_runtime_v216_2 as old
from .storage import digest,json_bytes
VERSION='v219-rejected-reserved-input-not-executor-corruption-r1'
CONTRACT=prior.CONTRACT+' Never send reserved request_key, action or security_risk fields in tool arguments. A rejected input executes nothing; correct it on a later normal budgeted opportunity.'
build_team_owner=prior.build_team_owner;close_runtime=prior.close_runtime;lock_fixed_candidates=prior.lock_fixed_candidates;set_native_limit=prior.set_native_limit;member_wire_tools=prior.member_wire_tools;enter_continuation=prior.enter_continuation

def rejection_proof(worker):
 if worker._executions or worker._pending is not None or worker._result is not None:return None
 body=worker._last_body;association=worker._association
 if not isinstance(body,dict) or not body.get('id') or not association.get('call_id'):return None
 try:
  message=body['choices'][0]['message'];calls=message['tool_calls']
  if message['role']!='assistant' or len(calls)!=1:return None
  call=calls[0]
  if call.get('type')!='function' or not isinstance(call.get('id'),str) or not call['id'] or call['id'] in worker._assistant_messages:return None
  if call['function']['name'] not in worker.schemas:return None
  args=json.loads(call['function']['arguments'])
  fields=sorted(set(args)&{'request_key','action','security_risk'}) if isinstance(args,dict) else []
  if not fields:return None
 except (ValueError,KeyError,TypeError,IndexError):return None
 return {'call':call,'message':message,'record':{'version':VERSION,'reserved_fields':fields,'original_response_sha256':digest(json_bytes(body)),'original_response_id':body['id'],'model_call_id':association['call_id'],'model_tool_call_id':call['id'],'world_action_executed':False,'arguments_stripped':False,'automatic_retry':False,'next_opportunity_charged':True}}
@cache
def worker_type():
 class Worker(old.worker_type()):
  def _fail(self,status,reason,**details):
   if status=='execution_integrity_error' and reason=='Reserved runtime or SDK fields are forbidden':
    proof=rejection_proof(self)
    if proof:
     self._assistant_messages[proof['call']['id']]=proof['message'].copy()
     self._emit('reserved_input_rejected_before_execution',proof['record'])
     return super()._fail('model_format_error','Reserved tool arguments rejected. No action executed. Use only declared public arguments on a new normal opportunity.',model_call_id=self._association['call_id'],preexecution_rejection=proof['record'])
   return super()._fail(status,reason,**details)
 return Worker

def build_runtime(owner,prepared,*args,**kwargs):
 if kwargs.get('worker_factory') is not None:raise ValueError('Explicit v219 worker binding required')
 kwargs['worker_factory']=worker_type()
 return prior.build_runtime(owner,prepared,*args,**kwargs)

def run_fragment(prepared,runtime,*,on_opportunity=None):
 result=prior.run_fragment(prepared,runtime,on_opportunity=on_opportunity)
 if result.get('termination_class')=='quiescent_without_delivery' and any('budget_exhausted' in str(v) for v in result.get('role_stops',{}).values()):
  result['termination_class']='budget_boundary_without_delivery'
  result['classification_note']='Member request reservation exhausted; preserve raw closure_reason and role_stops.'
 return result
