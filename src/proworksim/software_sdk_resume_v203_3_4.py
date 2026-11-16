"""Rebind the existing strict rejection hook to the restored private session.

No prompt, schema, rejection policy, model response, action or budget is changed.
The frozen v203.3.2 checkpoint serialization remains readable.
"""
import json
from types import FunctionType,MethodType
from . import software_sdk_resume_v203_3_2 as original
read=original.read
restore_world=original.restore_world
register_persistence_types=original.register_persistence_types
save=original.save
reset_clock=original.reset_clock
VERSION='v203.3.4-restored-project-rejection-binding-r1'
def cell(value):
 def capture():return value
 return capture.__closure__[0]
def rebind_rejection(worker):
 hook=worker._format_rejection;fn=hook.__func__
 cells=dict(zip(fn.__code__.co_freevars,fn.__closure__,strict=True))
 if fn.__module__!='proworksim.software_benchmark_rejected_history_v117' or set(cells)!={'adapter','conversation','folder','original','receipts'}:
  raise ValueError('Unrecognized strict rejection closure; do not change its semantics')
 if cells['adapter'].cell_contents is not worker.transport.owner.adapter:raise ValueError('Wrong private adapter')
 if cells['original'].cell_contents.__self__ is not worker:raise ValueError('Wrong bound worker')
 prior=cells['conversation'].cell_contents
 folder=cells['folder'].cell_contents
 records=[json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))]
 if any(r.get('worker_id')!=worker.role_id for r in records):raise ValueError('Foreign rejection receipts')
 receipts=cells['receipts'].cell_contents;receipts[:]=records
 values={key:c.cell_contents for key,c in cells.items()};values['conversation']=worker.conversation
 rebound=FunctionType(fn.__code__,fn.__globals__,fn.__name__,fn.__defaults__,tuple(cell(values[k]) for k in fn.__code__.co_freevars))
 rebound.__kwdefaults__=fn.__kwdefaults__
 worker._format_rejection=MethodType(rebound,worker)
 worker._rejected_history_v117['conversation']=worker.conversation
 worker._history_trace_v110.assert_bound_to(worker.conversation)
 return {'version':VERSION,'old_fresh_session_replaced':prior is not worker.conversation,
  'restored_conversation_id':str(worker.conversation.id),'prior_rejection_receipts_retained':len(records),
  'same_function_bytecode':rebound.__code__ is fn.__code__,'schema_or_feedback_policy_changed':False,'model_calls':0}
def restore_runtime(prepared,runtime,path):
 result=original.restore_runtime(prepared,runtime,path)
 result['restored_rejection_bindings']={m:rebind_rejection(w) for m,w in runtime.policies.items()}
 return result
