"""Minimum deadline/fatal transport repair, no weakened validation or cash reset."""
import json,time
from pathlib import Path
from .software_delegation_actor_v203_3_3_r2 import Actor as PreviousActor
from .storage import json_bytes
class FatalTransport(RuntimeError):pass
class Actor(PreviousActor):
 def bind_deadline(self,deadline):
  hard=deadline.hard_at
  if not time.monotonic()<hard<=self.hard_at:raise ValueError('Restored task deadline exceeds actor lifecycle')
  if self.rpc.failed or self.rpc.closed:raise FatalTransport('Cannot bind a failed transport')
  self.task_deadline=hard;self.rpc.hard_at=hard
  self.rpc.receive=lambda:json.loads(self.channel.readline(self.rpc.hard_at))
 def test(self,*,files,entry_metadata,request):
  try:
   if self.rpc.failed or self.rpc.closed:raise FatalTransport('Known failed actor transport')
   if request['hard_deadline_monotonic']!=getattr(self,'task_deadline',None):raise FatalTransport('Callback/RPC deadline mismatch')
   return super().test(files=files,entry_metadata=entry_metadata,request=request)
  except Exception as e:
   self.fatal_transport={'type':type(e).__name__,'message':str(e)}
   raise FatalTransport(str(e)) from e

def after_opportunity(actor,batch_pause_file):
 if getattr(actor,'fatal_transport',None) or actor.rpc.failed or actor.rpc.closed:
  p=Path(batch_pause_file);p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(json_bytes({'status':'paused_systemic_transport_fault','reason':getattr(actor,'fatal_transport',None),'new_admission':False}))
  raise FatalTransport('Stop this episode and subsequent admissions before another model request')

def public_context(config,public):
 from .software_benchmark_runtime_inputs_v203_2_3_r3 import public_test_guidance
 return 'Public repository interpreter: '+public['public_python']+'.\n'+public_test_guidance('PROJECT',config['public_test_entry'])
