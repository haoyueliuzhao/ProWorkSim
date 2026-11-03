"""Record the user's prelaunch increase without adding attempts, money or objects."""
from __future__ import annotations

import copy
import json

from proworksim import software_benchmark_scope_v111 as prior
from proworksim import software_benchmark_scope_v112 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def prepare():
    if (scope.AUTH_FILE.exists()
            or any((root/'execution-started.json').exists() for root in (prior.API_ROOT,scope.API_ROOT))
            or any((scope.BATCH_ROOT/'resource-claims').glob('*.json'))):
        raise PermissionError('Only a wholly unstarted batch may change its concurrency plan')
    authority=prior.require_allowed()
    old=prior.load(authority['plan'])
    new=copy.deepcopy(old)
    new.update(version=scope.VERSION,constraints=copy.deepcopy(scope.CONSTRAINTS),
        original_plan=reference(prior.PLAN_FILE),original_authorization=reference(prior.AUTH_FILE),
        concurrency_amendment={'instruction':'提高并发','before_any_resource_dispatch':True,
            'old_generation_concurrency':8,'new_generation_concurrency':16,
            'score_concurrency':2,'same_per_object_limits':True,
            'new_cpu_limit':112,'new_memory_limit_bytes':576*scope.GIB,
            'additional_generation_attempts':0,'additional_container_or_volume_allowance':0,
            'additional_cash':0,'same_user_service':scope.API_UNIT})
    assert new['rows']==old['rows'] and new['resources']==old['resources']
    scope.validate_plan(new)
    ref=scope.retain(scope.PLAN_FILE,new)
    return {'plan':ref,'generation_pairs':16,'grading':2,'additional_attempts':0,
            'API_requests':0,'Docker_operations':0,'service_operations':0}


if __name__=='__main__':
    print(json.dumps(prepare(),ensure_ascii=False))
