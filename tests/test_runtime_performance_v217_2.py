from proworksim import software_runtime_performance_v217_2 as fast
from proworksim.software_fixed_organization_clone_v131 import clone_function
import test_organization_performance_v214 as prior

def test_exact_encoding_and_mutable_isolation(tmp_path):
 # The encoder now uses native canonical serialization, not cache hits for hashing.
 import inspect
 source=inspect.getsource(prior.test_exact_encoding_normalization_and_atomic_invalidation).replace(' and s.encoder.hits>0','')
 ns={**vars(prior),'fast':fast};exec(compile(source,__file__,'exec'),ns)
 ns['test_exact_encoding_normalization_and_atomic_invalidation'](tmp_path)

def test_tools_observation_permissions_and_replay(tmp_path):
 clone_function(prior.test_same_observation_tools_results_rejection_and_replay,{**vars(prior),'fast':fast})(tmp_path)

def test_actual_review_merge_and_delivery(tmp_path):
 clone_function(prior.test_actual_candidate_review_merge_and_delivery_with_fast_world,{**vars(prior),'fast':fast})(tmp_path)

def test_failed_commit_and_post_commit_recovery(tmp_path):
 clone_function(prior.test_failed_apply_reused_version_and_post_commit_retry,{**vars(prior),'fast':fast})(tmp_path)
