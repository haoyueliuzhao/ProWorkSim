from types import SimpleNamespace as S
from proworksim.software_organization_runtime_v218 import enter_continuation,correct_quiescence
class Recorder:
 def record(self,*a,**kw):pass
def fixture():
 messages={m:[] for m in ('member_001','member_002')};state={'v':1};terminal=[None]
 rt=S(labels=list(messages),policies={m:S(conversation=S(send_message=messages[m].append)) for m in messages},recorder=Recorder(),waiting=dict.fromkeys(messages,'waiting'),work_ended=dict.fromkeys(messages),stopped={})
 p=S(world=S(protocol=lambda:{'terminal':terminal[0]},dynamic=lambda:state))
 return p,rt,messages,state,terminal
def test_bounded_notice_no_world_or_budget_mutation():
 p,r,msg,state,term=fixture();assert not correct_quiescence(p,r)
 enter_continuation(r);assert correct_quiescence(p,r);assert not r.waiting and state=={'v':1}
 r.waiting=dict.fromkeys(msg);assert not correct_quiescence(p,r)
 state['v']=2;assert correct_quiescence(p,r)
 state['v']=3;r.waiting=dict.fromkeys(msg);assert not correct_quiescence(p,r)
 assert all(len(m)==3 for m in msg.values())
def test_terminal_and_stopped_not_revived():
 p,r,msg,state,term=fixture();enter_continuation(r);r.stopped=dict.fromkeys(msg,'technical_error');assert not correct_quiescence(p,r)
 r.stopped={};term[0]='DELIVERED';assert not correct_quiescence(p,r)
 assert all(len(m)==1 for m in msg.values())
