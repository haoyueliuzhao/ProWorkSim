"""Candidate-custody controls; no archives are reexported or models invoked."""
from copy import deepcopy
import pytest
from proworksim import software_benchmark_scope_v163 as scope
from proworksim import software_benchmark_grading_v163 as grading
from proworksim.software_benchmark_candidates_v054 import reference


def config():
 return scope.load(scope.load(reference(grading.RESULT_FILE))['configuration'])


def test_exact_administrative_record_preserves_raw_unknown_and_partial_observer_coverage():
 result,code,delivery,proof=grading.audit_original(config())
 assert proof['original_generation_status']=='technical_unknown'
 assert proof['missing_controller_result_preserved']
 assert result['controller_result_reconstructed'] is False and 'controller_result' not in result
 assert proof['observer_coverage_preserved']['presentations'] is True
 assert proof['observer_coverage_preserved']['actions'] is False
 assert code['tree_sha256']==delivery['tree_sha256']==grading.EXPECTED_TREE
 assert code['patch_receipt']['patch']['sha256']==grading.EXPECTED_PATCH
 assert proof['original_settled_requests']==53 and proof['original_actual_tokens']==2819481


@pytest.mark.parametrize('field,value',[('seed',0),('slot_id','another-slot'),('group_id','C2')])
def test_no_other_slot_seed_or_condition_may_borrow_the_relocated_lock(field,value):
 altered=deepcopy(config());altered[field]=value
 with pytest.raises(ValueError,match='closure/lock/audit'):
  grading.audit_original(altered)


def test_same_tree_delivery_cannot_create_an_unnecessary_second_grader():
 assert scope.cpu_set('grader',0)==','.join(map(str,scope.host_cpu_pool()[116:120]))
 with pytest.raises(ValueError):scope.cpu_set('grader',1)
 policy=scope.dispatch_view()
 with pytest.raises(PermissionError,match='same-tree delivery'):
  policy.claim_resource(scope.DELIVERY_KEY)
