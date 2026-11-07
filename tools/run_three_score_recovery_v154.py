"""Fresh control pairs, then three unchanged normally closed generation candidates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from proworksim import software_benchmark_rescore_v154 as scoring
from proworksim import software_benchmark_rescore_v150 as prior
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, RUN = scoring.ROOT, scoring.RUN
TASKS = ('psf__requests-1766','pytest-dev__pytest-6197')
INDICES = (10214,10215,10219)


def retain(path,value):
    if Path(path).exists():
        ref=reference(path)
        old=Path(path).read_bytes() if isinstance(value,bytes) else scoring.load(ref)
        if old!=value:
            raise ValueError('Previously staged immutable preparation bytes changed')
        return ref
    return write_new(path,value)


def command(*args):
    return [str(ROOT/'.venv/bin/python'), '-B', str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-m', 'proworksim.software_benchmark_rescore_v154', *map(str,args)]


def prepare():
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    RUN.mkdir(parents=True,exist_ok=True)
    (RUN/'coordinator').mkdir(exist_ok=True)
    old=scoring.load(reference(prior.PLAN))
    rows=[r for r in old['rows'] if r['slot_index'] in INDICES]
    if len(rows)!=3 or {r['instance_id'] for r in rows}!=set(TASKS):
        raise ValueError('Only the three specified previously technical-unknown candidates are allowed')
    result=scoring.load(reference(exports.OUTPUT/'10219/recovery-result.json'))
    baseline=scoring.load(result['baseline_snapshot'])
    project_ref=retain(RUN/'pytest6197-pyproject.toml',baseline['files']['pyproject.toml'].encode())
    wheelhouse=ROOT/'runs/software-benchmark-v142/role-pilot40-r1/pytest-build-preparation'
    wheels=[reference(wheelhouse/name) for name in (
        'setuptools-65.5.0-py3-none-any.whl','setuptools_scm-7.1.0-py3-none-any.whl',
        'wheel-0.44.0-py3-none-any.whl','packaging-23.1-py3-none-any.whl',
        'typing_extensions-4.4.0-py3-none-any.whl','tomli-2.0.1-py3-none-any.whl')]
    offline=scoring.offline_build_adapter().offline_build_plan(project_ref,wheels,target_python='3.9.20')
    retain(RUN/'offline-build-plan.json',offline)
    plan={'version':scoring.VERSION,'original_plan':reference(prior.PLAN),'rows':rows,
        'resources':{},'environments':{t:old['environments'][t] for t in TASKS},
        'constraints':scoring.CONSTRAINTS,'new_model_calls':0,'fresh_controls_first':True,
        'original_results_unchanged':True,'planned_containers':7,'authorization_ceiling':9}
    for task in TASKS:
        config=scoring.load(plan['environments'][task]['configuration'])
        for kind in ('gold','empty'):
            key='control-v154-'+task+'-'+kind
            plan['resources'][key]={'role':'control','instance_id':task,'patch_kind':kind,
                'image_id':config['scorer_request_base']['image']['image_id']}
    for row in rows:
        key='score-'+str(row['slot_index'])
        plan['resources'][key]=old['resources'][key]
    plan_ref=write_new(scoring.PLAN,plan)
    instance=scoring.build_scorer(manifest_provider=lambda:{})
    instance.environment.prepare()
    completed=subprocess.run(command('--manifest'),cwd=ROOT,env=scoring.base.clean_environment(),
        capture_output=True,text=True,timeout=120,check=True)
    manifest_ref=write_new(RUN/'coordinator/scorer-manifest.json',json.loads(completed.stdout))
    original_source=reference(prior.SOURCE)
    sources=[reference(scoring.__file__),reference(__file__),original_source]
    for ref in scoring.load(original_source)['files']:
        scoring.checked(ref)
        if ref not in sources:
            sources.append(ref)
    source_ref=write_new(scoring.SOURCE,{'files':sources,'active_sources_unchanged':True})
    auth=write_new(scoring.AUTH,{'status':'authorized_by_current_user_instructions','plan':plan_ref,
        'source_index':source_ref,'constraints':scoring.CONSTRAINTS,
        'scope':'Three unique locked normal-generation candidates10214/10215/10219 and four fresh environment controls; no API',
        'authorization_basis':'User requested actual testing, technical-failure recovery and standing non-disruptive experiment Docker permission',
        'maximum_containers':9,'currently_planned_containers':7,'maximum_parallel_scorers':2,
        'maximum_TLS_sessions':6,'maximum_connections':3072,'maximum_payload_bytes':384*1024**2,
        'model_calls':0,'new_volumes':0,'host_configuration_changes':False})
    return {'plan':plan_ref,'authorization':auth,'manifest':manifest_ref,'operations':0}


def request(*,task,kind=None,index=None,qualification=None):
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    plan_ref=reference(scoring.PLAN)
    plan=scoring.load(plan_ref)
    scorer=scoring.build_scorer(manifest_provider=lambda:scoring.load(reference(RUN/'coordinator/scorer-manifest.json')))
    if kind:
        key='control-v154-'+task+'-'+kind
        value={'version':scoring.VERSION,'resource_key':key,'instance_id':task,'slot_id':None,
            'configuration':plan['environments'][task]['configuration'],'patch_kind':kind,'candidate_lock':None}
    else:
        row=next(r for r in plan['rows'] if r['slot_index']==index)
        ref=reference(exports.OUTPUT/str(index)/'recovery-result.json')
        result=exports.validate_export_result_bounded(ref,row)
        key='score-'+str(index)
        admission={'slot_id':row['slot_id'],'slot_index':index,'endpoint':'code','export_result':ref,
            'candidate_lock':result['candidate_lock'],'scoring_attempt':1,'normal_generation_export_recovered':True}
        folder=RUN/'admissions'
        folder.mkdir(exist_ok=True)
        admission_ref=write_new(folder/(key+'.json'),admission)
        value={'version':scoring.VERSION,'resource_key':key,'instance_id':task,
            'slot_id':row['slot_id'],'source_slot_id':row['source_slot_id'],
            'configuration':row['configuration'],'patch_kind':None,'candidate_lock':result['candidate_lock'],
            'generation_result':ref,'measurement_kind':row['measurement_kind'],
            'group_id':row['group_id'],'organization_id':row['organization_id'],
            'qualification':qualification,'delivery_evidence':None,'recovery_admission':admission_ref}
    value.update(plan=plan_ref,limits=scorer.LIMITS,scorer_manifest=reference(RUN/'coordinator/scorer-manifest.json'),
        cpuset_cpus=None,directory=str(scoring.GRADING/key),**scorer.environment.request_fields(task))
    (scoring.GRADING/key).mkdir(parents=True,exist_ok=True)
    return write_new(scoring.GRADING/key/'request.json',value)


def run_one(ref,lane=0):
    value = scoring.load(ref)
    folder = Path(value['directory'])
    deadline = time.monotonic()+900
    while True:
        try:
            claim = scoring.policy().claim_resource(value['resource_key'],lane=lane)
            break
        except scoring.dispatch.ResourceBusy:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)
    write_new(folder/'capacity-claim.json',{'prepared_request':ref,'claim':claim})
    with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command('--request',ref['path']),cwd=ROOT,
            env=scoring.base.clean_environment(),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        try:
            returncode = process.wait(timeout=2100)
        except subprocess.TimeoutExpired:
            process.terminate()
            returncode = process.wait(timeout=240)
    quiet = scoring.load(reference(folder/'quiescence.json')) if (folder/'quiescence.json').exists() else {}
    complete = quiet.get('quiescent') is True and quiet.get('cleanup_errors') == []
    result = {'version':scoring.VERSION,'request':ref,'resource_key':value['resource_key'],
        'status':'process_exited','returncode':returncode,'cleanup_proven':complete,'model_calls':0}
    write_new(folder/'completion.json',result)
    if not complete:
        raise PermissionError('This scorer lacks full cleanup evidence; do not create another object')
    receipt = scoring.load(reference(folder/'receipt.json')) if (folder/'receipt.json').exists() else {}
    result.update(receipt=reference(folder/'receipt.json') if receipt else None,
        official_status=receipt.get('status'),resolved=receipt.get('resolved'))
    return result


def qualify(task):
    records = []
    for kind in ('gold','empty'):
        folder = scoring.GRADING/('control-v154-'+task+'-'+kind)
        records.append({'patch_kind':kind,**{name:reference(folder/(name+'.json'))
            for name in ('receipt','quiescence','completion')},
            'initial_container':reference(folder/'official-output/initial-container.json')})
    value = {'version':scoring.VERSION,'instance_id':task,'plan':reference(scoring.PLAN),
        'controls':records,'passed':True,'model_calls':0}
    output = RUN/'coordinator/qualifications'
    output.mkdir(parents=True,exist_ok=True)
    proposal = write_new(output/(task+'-proposal.json'),value)
    plan = scoring.load(reference(scoring.PLAN))
    scoring.build_scorer().validate_qualification(proposal,
        scoring.load(plan['environments'][task]['configuration']),reference(scoring.PLAN))
    return write_new(output/(task+'.json'),value)


def run():
    from concurrent.futures import ThreadPoolExecutor
    scoring.allowed()
    write_new(RUN/'started.json',{'unix':time.time(),'pid':os.getpid(),'model_calls':0})
    outcomes=[]
    qualifications={}
    for task in TASKS:
        refs=[request(task=task,kind=kind) for kind in ('gold','empty')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            batch=list(pool.map(lambda item:run_one(*item),[(ref,lane) for lane,ref in enumerate(refs)]))
        outcomes.extend(batch)
        atomic_write(RUN/'progress.json',json_bytes({'completed':len(outcomes),'planned':7,'outcomes':outcomes}))
        print(json.dumps({'controls':task,'outcomes':batch}),flush=True)
        qualifications[task]=qualify(task)
    plan=scoring.load(reference(scoring.PLAN))
    for index in INDICES:
        row=next(r for r in plan['rows'] if r['slot_index']==index)
        result=run_one(request(task=row['instance_id'],index=index,qualification=qualifications[row['instance_id']]))
        outcomes.append(result)
        atomic_write(RUN/'progress.json',json_bytes({'completed':len(outcomes),'planned':7,'outcomes':outcomes}))
        print(json.dumps(result),flush=True)
    return write_new(RUN/'summary.json',{'version':scoring.VERSION,'outcomes':outcomes,
        'qualifications':qualifications,'finished_unix':time.time(),'model_calls':0,
        'original_candidates_and_results_unchanged':True})



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--prepare',action='store_true')
    choice.add_argument('--run',action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else run(),ensure_ascii=False))
