"""Cold local preparation of 48 reuse proofs and four unexecuted TLS controls."""
from __future__ import annotations

import json
import os
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
attempts=[]


def deny(event,_args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto',
                 'subprocess.Popen','os.system','os.fork','os.posix_spawn'}:
        attempts.append(event)
        raise RuntimeError('Qualification preparation must remain local and resource-free')


sys.addaudithook(deny)


def main():
    from proworksim import software_benchmark_grading_v131 as grading
    from proworksim.software_benchmark_candidates_v054 import reference,write_new
    def no_authority(*_args,**_kwargs):
        raise RuntimeError('No execution authority may be obtained in this CPU preparation')
    grading.scope.require_allowed=grading.scope.require_grading_allowed=no_authority
    prepared=grading.prepare_environment_qualifications_local()
    assert len(prepared['qualifications'])==48 and len(prepared['controls'])==4
    assert set(prepared['reuse_failures'])==grading.FRESH_CONTROL_TASKS
    verified=grading.verify_prepared_identity()
    assert verified['passed'] and not attempts
    output=grading.scope.ARTIFACT_ROOT/'grading-transport-control-r1/preparation.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    return write_new(output,{'version':'v131-real-cold-grading-preparation-r1','passed':True,
        'source':reference(__file__),'scorer_source':reference(grading.__file__),
        'scope_source':reference(grading.scope.__file__),
        'plan':reference(grading.scope.PLAN_FILE),
        'reused_qualified_environments':sorted(prepared['qualifications']),
        'prepared_fresh_control_requests':prepared['controls'],
        'live_TLS_qualification_still_pending':True,'fresh_controls_executed':0,
        'current_identity_verified':verified,'forbidden_operation_attempts':attempts,
        'model_calls':0,'Docker_operations':0,'network_connections':0})


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
