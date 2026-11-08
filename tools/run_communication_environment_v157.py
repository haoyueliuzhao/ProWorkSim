"""Execute only already prepared fresh gold/empty controls for the pilot."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from proworksim import software_benchmark_scope_v157 as scope
from proworksim import software_benchmark_grading_v157 as grading
from proworksim.software_benchmark_candidates_v054 import reference,write_new

def run():
    scope.require_grading_allowed('v157.run')
    prepared=scope.load(reference(scope.COORDINATOR_ROOT/'qualification-preparation.json'))
    worker=grading.factory()
    completed=[]
    def execute(ref):
        result=worker.run_request(ref)
        if worker.trustworthy_cleanup(ref) is not True:
            raise PermissionError('An owned control lacks cleanup proof')
        return {'request':ref,'completion':result}
    with ThreadPoolExecutor(max_workers=scope.MAX_GRADERS) as pool:
        pending={pool.submit(execute,r):r for r in prepared['controls']}
        for future in as_completed(pending):
            try:completed.append(future.result())
            except Exception as error:
                completed.append({'request':pending[future],'status':'technical_unknown',
                    'error':{'type':type(error).__name__,'message':str(error)}})
    qualifications=dict(prepared['qualifications'])
    for task in prepared['reuse_failures']:
        try:qualifications[task]={'status':'qualified','qualification':worker.qualify(task)}
        except Exception as error:
            qualifications[task]={'status':'not_qualified','passed':False,'error':str(error)}
    value={'version':scope.VERSION,'qualifications':qualifications,'control_completions':completed,
        'model_calls':0,'new_containers_requested':len(prepared['controls']),
        'shared_host_changes':0,'exceptions_do_not_remove_tasks':True}
    return write_new(scope.API_ROOT/'environment-only-qualification-status-r2.json',value)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true',required=True)
    parser.parse_args();print(json.dumps(run(),ensure_ascii=False))
