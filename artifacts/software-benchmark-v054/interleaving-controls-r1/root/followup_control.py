"""Only the two changed PROJECT fault branches; prior 49 controls are not rerun."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path

prior=Path('/tmp/v054-interleave-root-r1/control/control.py')
# Reuse only imports and fixture definitions preceding the old case loop.
# This does not execute any earlier case or alter its receipt.
prefix=prior.read_text().split("for mode in ('queue_cancel'",1)[0]
ns={'__name__':'v054_root_followup_fixture'}
exec(compile(prefix,str(prior),'exec'),ns)
root=Path('/tmp/v054-interleave-root-r1/control/followup-r1')
root.mkdir(exist_ok=False)
ns['OUTPUT']=root
captured=[]
real_budget=ns['SingleMemberBudget']
def budget_factory(**kwargs):
    result=real_budget(**kwargs)
    captured.append(result)
    return result
ns['SingleMemberBudget']=budget_factory
late=ns['project_case']('late_cancel')
assert late['host_guard']=={'stop_requested':True,'request_deadline':None}
assert late['budget']['attempts']==1 and late['budget']['charged_tokens']==2100
assert late['budget']['records']['call-late_cancel']['charge']['usage_status']=='uncertain_attempt_charged_reservation'

original_client=ns['ProgrammedClient']
class InvalidProofClient(original_client):
    @contextmanager
    def turn(self,operation,**arguments):
        self.turn_entered=True
        self.events.append('queued')
        error=self.cancellation(operation)
        error.receipt['session_claim']='different-untrusted-claim'
        raise error
        yield
ns['ProgrammedClient']=InvalidProofClient
invalid=ns['project_case']('invalid_proof')
assert invalid['raised']=='ValueError' and 'No exact server proof' in invalid['message']
assert invalid['host_guard']=={'stop_requested':True,'request_deadline':None}
assert invalid['budget']['attempts']==1 and invalid['budget']['held_tokens']==2100 and invalid['budget']['charged_tokens']==0
assert invalid['deadline']['cancelled_before_dispatch']==[] and invalid['deadline']['dispatches']=={}
captured[-1].cleanup('member_001','call-invalid_proof')
after=captured[-1].snapshot()
assert after['attempts']==1 and after['charged_tokens']==2100 and after['held_tokens']==0
assert after['records']['call-invalid_proof']['charge']['usage_status']=='uncertain_attempt_charged_reservation'
invalid['original_cleanup_budget']=after
reference=ns['reference']
transport_ref=reference(Path(ns['transport'].__file__))
prior_receipt=reference(prior.parent/'receipt.json')
report={'version':'v054-interleave-root-fault-followup-r1','passed':True,
 'prior_unchanged_control':prior_receipt,'prior_checks_rerun':False,
 'changed_source':transport_ref,'checks':{
  'late_commit_host_stop_true':True,'late_commit_original_uncertain_attempt_not_zeroed':True,
  'invalid_proof_host_stop_true':True,'invalid_proof_not_reclassified_as_zero_usage':True,
  'invalid_proof_original_cleanup_preserves_charge':True},
 'cases':{'late_commit':late,'invalid_proof':invalid},'model_calls':0,'GPU_queries':0,
 'GPU_loads':0,'SDK_conversations_created':0,'formal_slots_claimed':0}
ns['atomic_write'](root/'receipt.json',ns['json_bytes'](report))
print(json.dumps({'passed':True,'checks':report['checks'],'changed_source':transport_ref,
 'receipt':reference(root/'receipt.json')},ensure_ascii=False,indent=2))
