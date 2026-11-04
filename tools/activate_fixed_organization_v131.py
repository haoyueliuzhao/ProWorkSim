"""Enter one explicitly granted v131 admission/launch sequence; never grant it."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1')

from proworksim import software_benchmark_scope_v131 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new

VERSION='v131-explicit-postgrant-single-activation-r1'
OUTPUT=scope.BATCH_ROOT/'activation'
PROBE=scope.ROOT/'tools/check_httpbin_direct_v131.py'
PROBE_INTENT=scope.ARTIFACT_ROOT/'httpbin-direct-intent-r1.json'
PROBE_RESULT=scope.ARTIFACT_ROOT/'httpbin-direct-diagnostic-r1.json'
GRADING_PREPARATION=scope.ARTIFACT_ROOT/'grading-transport-control-r1/preparation.json'
PHASES=('bounded_direct_httpbin_probe','cold_grading_preparation',
        'create_or_verify_exact_new_parent','launch_unique_user_coordinator')


def phase_argv(name):
    python=[str(scope.ROOT/'.venv/bin/python'),'-B']
    if name==PHASES[0]:
        return [*python,str(PROBE),'--execute']
    if name==PHASES[1]:
        return [*python,str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
                str(scope.ROOT/'tools/prepare_grading_v131.py')]
    if name==PHASES[3]:
        return [*python,str(scope.ROOT/'tools/launch_fixed_organization_v131.py'),'--launch']
    raise ValueError('The parent phase uses its exact guarded Python API, not a shell command')


def validate_probe_evidence(value,resolution):
    selected=resolution.get('selected_ip')
    probes=value.get('probes',[])
    return (value.get('version')=='v131-public-httpbin-reachability-r1'
        and value.get('passed') is True and value.get('host')=='httpbin.org'
        and value.get('source')==reference(PROBE) and value.get('proxy_used') is False
        and value.get('automatic_retry') is False and value.get('host_listener') is False
        and value.get('maximum_connections')==4 and len(probes)<=4
        and type(value.get('application_bytes')) is int and 0<=value['application_bytes']<=64*1024
        and value.get('maximum_application_bytes')==64*1024
        and resolution.get('source')=='v131_current_DNS_and_bounded_endpoint_probe'
        and value.get('panel_identity',{}).get('plan')==reference(scope.PLAN_FILE)
        and resolution.get('hostname')=='httpbin.org' and resolution.get('ports')==[80,443]
        and resolution.get('ipv4')==[selected] and selected in value.get('current_DNS_ipv4',[])
        and resolution.get('automatic_retry') is False
        and all(any(p.get('ip')==selected and p.get('port')==port and p.get('get_contract_valid') is True
                    and (port!=443 or p.get('TLS_verified') is True and p.get('TLS_verify_mode')==2
                         and p.get('TLS_check_hostname') is True) for p in probes) for port in (80,443)))


def require_probe_result():
    proof=reference(PROBE_RESULT)
    result=scope.load(proof)
    resolution=scope.load(reference(scope.NETWORK_RESOLUTION_FILE))
    if (result.get('intent')!=reference(PROBE_INTENT) or resolution.get('diagnostic')!=proof
            or not validate_probe_evidence(result,resolution)):
        raise ValueError('The current single direct probe has no valid frozen endpoint')
    return {'diagnostic':proof,'network_resolution':reference(scope.NETWORK_RESOLUTION_FILE)}


def run_phase(name,argv,timeout):
    started=time.time()
    write_new(OUTPUT/(name+'-intent.json'),{'version':VERSION,'phase':name,'command':argv,
        'started_unix':started,'automatic_retry':False})
    with (OUTPUT/(name+'.stdout')).open('xb') as stdout, (OUTPUT/(name+'.stderr')).open('xb') as stderr:
        completed=subprocess.run(argv,cwd=scope.ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                 timeout=timeout,check=False)
    receipt={'version':VERSION,'phase':name,'returncode':completed.returncode,
        'started_unix':started,'finished_unix':time.time(),
        'stdout':reference(OUTPUT/(name+'.stdout')),'stderr':reference(OUTPUT/(name+'.stderr')),
        'automatic_retry':False}
    ref=write_new(OUTPUT/(name+'-result.json'),receipt)
    if completed.returncode:
        raise RuntimeError('The activation phase failed without replay: '+name+'; receipt='+str(ref['path']))
    return ref


def activate():
    from proworksim import software_benchmark_api_parent_v131 as parent
    # This is the first external-action boundary. Neither tool creates an
    # approved record; both independent exact grants must already be present.
    authority=scope.require_allowed('v131.prepare')
    parent_authority,parent_proposal=parent.approved()
    if authority.get('status')!='approved' or parent_authority.get('status')!='approved':
        raise PermissionError('Both concrete runtime and aggregate-parent grants are required')
    proposal=scope.load(reference(scope.PROPOSAL_FILE))
    if (proposal.get('aggregate_parent_proposal')!=reference(parent.PROPOSAL)
            or proposal.get('postgrant_sequence')!=list(PHASES)
            or proposal.get('constraints')!=scope.CONSTRAINTS
            or parent_proposal.get('slice')!=scope.CONTAINER_PARENT):
        raise PermissionError('The granted activation order or new parent identity differs')
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json','execution-started.json')):
        raise PermissionError('An entered user-service identity cannot be activated again')
    if OUTPUT.exists():
        raise PermissionError('An activation attempt already exists; preserve it for explicit recovery')
    if parent.RELEASED.exists():
        raise PermissionError('A released parent identity cannot be recreated')
    OUTPUT.mkdir(parents=True)
    write_new(OUTPUT/'intent.json',{'version':VERSION,'started_unix':time.time(),
        'runtime_authorization':reference(scope.AUTH_FILE),'user_grant':authority['user_grant'],
        'parent_authorization':reference(parent.AUTHORIZATION),'proposal':reference(scope.PROPOSAL_FILE),
        'source_index':reference(scope.SOURCE_FILE),'phases':list(PHASES),'automatic_retry':False})
    steps=[]
    try:
        if PROBE_INTENT.exists() or PROBE_RESULT.exists() or scope.NETWORK_RESOLUTION_FILE.exists():
            steps.append({'phase':PHASES[0],'existing_single_completed_probe_reused':require_probe_result()})
        else:
            receipt=run_phase(PHASES[0],phase_argv(PHASES[0]),120)
            steps.append({'phase':PHASES[0],'execution':receipt,**require_probe_result()})
        if GRADING_PREPARATION.exists():
            value=scope.load(reference(GRADING_PREPARATION))
            if value.get('passed') is not True or value.get('plan')!=reference(scope.PLAN_FILE):
                raise ValueError('An existing cold preparation belongs to another code or plan')
            from proworksim import software_benchmark_grading_v131 as grading
            receipt=run_phase('verify_existing_cold_preparation',grading.command(['--verify-preparation']),300)
            steps.append({'phase':PHASES[1],'existing_preparation':reference(GRADING_PREPARATION),'verification':receipt})
        else:
            if scope.COORDINATOR_ROOT.exists() and any(scope.COORDINATOR_ROOT.iterdir()):
                raise ValueError('Partial grading preparation is retained; do not merge or silently retry it')
            receipt=run_phase(PHASES[1],phase_argv(PHASES[1]),360)
            value=scope.load(reference(GRADING_PREPARATION))
            if value.get('passed') is not True or value.get('live_TLS_qualification_still_pending') is not True:
                raise ValueError('Cold metadata preparation cannot claim live TLS qualification')
            steps.append({'phase':PHASES[1],'execution':receipt,'preparation':reference(GRADING_PREPARATION)})
        if parent.CREATED.exists():
            qualified=parent.require_qualified()
            steps.append({'phase':PHASES[2],'existing_exact_parent_verified':qualified})
        else:
            if (parent.RUN/'create-intent.json').exists():
                raise PermissionError('Consumed parent-start identity requires explicit reconciliation, not replay')
            created=parent.create()
            qualified=parent.require_qualified()
            steps.append({'phase':PHASES[2],'created':created,'qualification':qualified})
        receipt=run_phase(PHASES[3],phase_argv(PHASES[3]),90)
        launched=scope.load(reference(scope.API_ROOT/'launch-result.json'))
        if launched.get('returncode')!=0 or launched.get('unit')!=scope.API_UNIT:
            raise ValueError('The unique new coordinator launch is unproven')
        steps.append({'phase':PHASES[3],'execution':receipt,'launch':reference(scope.API_ROOT/'launch-result.json')})
        return write_new(OUTPUT/'completion.json',{'version':VERSION,'status':'coordinator_launched',
            'finished_unix':time.time(),'steps':steps,'actual_task_completion_claimed':False,
            'live_actor_and_TLS_qualification_run_by_coordinator':True,'automatic_retry':False})
    except BaseException as error:
        write_new(OUTPUT/'failure.json',{'version':VERSION,'status':'activation_failed',
            'finished_unix':time.time(),'steps':steps,
            'error':{'type':type(error).__name__,'message':str(error)},
            'automatic_retry':False,'prior_records_preserved':True,
            'owned_resource_state_requires_inspection_before_recovery':True})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true',required=True)
    parser.parse_args()
    print(json.dumps(activate(),ensure_ascii=False))
