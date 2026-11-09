"""Only the fresh gold/empty pair; no generation or edits to existing controls."""
import json
from concurrent.futures import ThreadPoolExecutor
from proworksim import software_benchmark_scope_v183 as scope
from proworksim.software_benchmark_grading_v183 import factory
from proworksim.software_benchmark_candidates_v054 import reference

if __name__=='__main__':
    import os,resource
    os.sched_setaffinity(0,{46,47})
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    scope.require_allowed()
    grading=factory();prepared=grading.prepare_environment_qualifications()
    with ThreadPoolExecutor(max_workers=2) as pool:
        completed=list(pool.map(grading.run_request,prepared['controls']))
    result={'completions':completed,'API_calls':0}
    try:result['qualification']=grading.qualify('pylint-dev__pylint-8898');result['passed']=True
    except Exception as error:result.update(passed=False,error={'type':type(error).__name__,'message':str(error)})
    ref=scope.retain(scope.STATE_ROOT/'summary.json',result)
    print(json.dumps({'summary':ref,'passed':result['passed']}))
