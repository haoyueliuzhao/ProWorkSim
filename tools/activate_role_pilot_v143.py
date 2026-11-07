"""Activate a frozen explicitly granted pilot; no grant is created by this tool."""
from __future__ import annotations

import argparse
import json
import subprocess
import time

from proworksim import software_benchmark_scope_v143 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

VERSION = 'v143-explicit-postgrant-role-pilot-activation-r1'
OUTPUT = scope.STATE_ROOT/'activation'
PHASES = ('reuse_completed_endpoint_probe', 'cold_grading_preparation', 'launch_unique_user_coordinator')


def postgrant_sequence():
    return list(PHASES)


def run_phase(name, argv, timeout):
    write_new(OUTPUT/(name+'-intent.json'), {'phase':name,'command':argv,'started_unix':time.time(),
        'automatic_retry':False})
    with (OUTPUT/(name+'.stdout')).open('xb') as out, (OUTPUT/(name+'.stderr')).open('xb') as err:
        proc = subprocess.run(argv, cwd=scope.ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            timeout=timeout, check=False)
    value = {'phase':name,'returncode':proc.returncode,'finished_unix':time.time(),
        'stdout':reference(OUTPUT/(name+'.stdout')),'stderr':reference(OUTPUT/(name+'.stderr')),
        'automatic_retry':False}
    ref = write_new(OUTPUT/(name+'-result.json'), value)
    if proc.returncode:
        raise RuntimeError('Activation failed without replay: '+str(ref['path']))
    return ref


def verify_probe_if_available():
    # The recovery scope verifies exact original evidence and unchanged network
    # conditions. Reuse never emits a second health probe or claims a new one.
    return scope.validate_original_probe_reuse()


def activate():
    authority = scope.require_allowed('v143.prepare')
    proposal = scope.load(reference(scope.PROPOSAL_FILE))
    if proposal.get('postgrant_sequence') != list(PHASES) or proposal.get('constraints') != scope.CONSTRAINTS:
        raise PermissionError('Activation order or bounded resources differ from the grant')
    if OUTPUT.exists() or any((scope.API_ROOT/name).exists() for name in ('launch-intent.json','execution-started.json')):
        raise PermissionError('This activation identity has been entered; retain it without replay')
    OUTPUT.mkdir(parents=True)
    write_new(OUTPUT/'intent.json', {'version':VERSION,'started_unix':time.time(),
        'authorization':reference(scope.AUTH_FILE),'user_grant':authority['user_grant'],
        'source_index':reference(scope.SOURCE_FILE),'phases':list(PHASES),
        'system_slice_operations':0,'automatic_retry':False})
    python = [str(scope.ROOT/'.venv/bin/python'), '-B']
    steps = []
    try:
        steps.append({'phase':PHASES[0], **verify_probe_if_available()})
        cold = run_phase(PHASES[1],[*python,str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
            str(scope.ROOT/'tools/prepare_grading_v143.py'),'--prepare-qualifications'],360)
        steps.append({'phase':PHASES[1],'execution':cold})
        launch = run_phase(PHASES[2],[*python,str(scope.ROOT/'tools/launch_role_pilot_v143.py'),'--launch'],90)
        record = scope.load(reference(scope.API_ROOT/'launch-result.json'))
        if record.get('returncode') != 0 or record.get('unit') != scope.API_UNIT:
            raise ValueError('The exact new ordinary-user owner launch is unproven')
        steps.append({'phase':PHASES[2],'execution':launch,'launch':reference(scope.API_ROOT/'launch-result.json')})
        return write_new(OUTPUT/'completion.json', {'version':VERSION,'status':'coordinator_launched',
            'steps':steps,'finished_unix':time.time(),'actual_tasks_complete':False,
            'system_slice_operations':0,'actual_environment_and_zero_model_controls_still_required':True})
    except BaseException as error:
        write_new(OUTPUT/'failure.json', {'version':VERSION,'status':'activation_failed',
            'steps':steps,'finished_unix':time.time(),'error':{'type':type(error).__name__,'message':str(error)},
            'automatic_retry':False,'owned_resource_state_requires_inspection':True})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true',required=True)
    parser.parse_args()
    print(json.dumps(activate(),ensure_ascii=False))
