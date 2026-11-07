"""Two fresh Requests1766 controls, then two unchanged stopped candidates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from proworksim import software_benchmark_rescore_v147 as scoring
from proworksim import software_benchmark_rescore_v145 as prior
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, RUN = scoring.ROOT, scoring.RUN
TASK = 'psf__requests-1766'
INDICES = (10103,10104)


def command(*args):
    return [str(ROOT/'.venv/bin/python'), '-B', str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-m', 'proworksim.software_benchmark_rescore_v147', *map(str,args)]


def prepare():
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN/'coordinator').mkdir(exist_ok=True)
    original = scoring.load(reference(prior.PLAN))
    rows = [row for row in original['rows'] if row['slot_index'] in INDICES]
    if len(rows) != 2 or any(row['instance_id'] != TASK for row in rows):
        raise ValueError('Only the two declared already-locked Requests1766 candidates are admitted')
    plan = {'version':scoring.VERSION, 'original_plan':reference(prior.PLAN), 'rows':rows,
        'environments':{TASK:original['environments'][TASK]},
        'candidates':{str(i):original['candidates'][str(i)] for i in INDICES},
        'resources':{}, 'constraints':scoring.CONSTRAINTS,
        'original_unknown_preserved':True, 'new_model_calls':0, 'fresh_controls_first':True}
    image = scoring.load(rows[0]['configuration'])['scorer_request_base']['image']['image_id']
    for kind in ('gold','empty'):
        key = 'control-v147-'+TASK+'-'+kind
        plan['resources'][key] = {'role':'control','instance_id':TASK,'patch_kind':kind,'image_id':image}
    for row in rows:
        key = 'stopped-score-'+str(row['slot_index'])
        plan['resources'][key] = {**original['resources'][key]}
    plan_ref = write_new(scoring.PLAN,plan)
    scoring.build_scorer(manifest_provider=lambda:{}).environment.prepare()
    completed = subprocess.run(command('--manifest'),cwd=ROOT,env=scoring.base.clean_environment(),
        capture_output=True,text=True,timeout=120,check=True)
    manifest = json.loads(completed.stdout)
    manifest_ref = write_new(RUN/'coordinator/scorer-manifest.json',manifest)
    sources = [reference(scoring.__file__),reference(__file__),reference(prior.SOURCE)]
    for ref in scoring.load(reference(prior.SOURCE))['files']:
        scoring.checked(ref)
        if ref not in sources:
            sources.append(ref)
    source_ref = write_new(scoring.SOURCE,{'files':sources,'previous_frozen_source':reference(prior.SOURCE)})
    authorization = write_new(scoring.AUTH,{'status':'authorized_by_current_user_instructions',
        'plan':plan_ref,'source_index':source_ref,'constraints':scoring.CONSTRAINTS,
        'scope':'Four serial Requests1766 scorers: gold, empty, original stopped10103/10104; no generation',
        'standing_permission':'实验测试相关的docker使用在不干扰服务器及其他用户的情况下可以使用，无需发起请求。',
        'user_instruction':'网络问题进入恢复或重新测试队列；处理经常出现的技术未知',
        'idle_revision':{'before_seconds':60,'after_seconds':180,'total_seconds':1800},
        'maximum_TLS_sessions':4,'maximum_connections':2048,'maximum_payload_bytes':256*1024**2,
        'host_mount_network_or_daemon_changes':False,'GPU_operations':0,'model_calls':0})
    return {'plan':plan_ref,'authorization':authorization,'manifest':manifest_ref,'operations':0}


def request(kind=None,index=None,qualification=None):
    plan_ref = reference(scoring.PLAN)
    plan = scoring.load(plan_ref)
    scorer = scoring.build_scorer(manifest_provider=lambda:scoring.load(reference(RUN/'coordinator/scorer-manifest.json')))
    if kind:
        key = 'control-v147-'+TASK+'-'+kind
        value = {'version':scoring.VERSION,'resource_key':key,'instance_id':TASK,'slot_id':None,
            'configuration':plan['environments'][TASK]['configuration'],'patch_kind':kind,
            'candidate_lock':None}
    else:
        row = next(row for row in plan['rows'] if row['slot_index'] == index)
        key = 'stopped-score-'+str(index)
        job = plan['candidates'][str(index)]
        value = {'version':scoring.VERSION,'resource_key':key,'instance_id':TASK,
            'slot_id':row['slot_id'],'source_slot_id':row['source_slot_id'],
            'configuration':row['configuration'],'patch_kind':None,'candidate_lock':job['candidate_lock'],
            'generation_result':job['result'],'measurement_kind':row['measurement_kind'],
            'group_id':row['group_id'],'organization_id':row['organization_id'],
            'qualification':qualification,'delivery_evidence':None}
    value.update(plan=plan_ref,limits=scorer.LIMITS,
        scorer_manifest=reference(RUN/'coordinator/scorer-manifest.json'),cpuset_cpus=None,
        directory=str(scoring.GRADING/key),**scorer.environment.request_fields(TASK))
    (scoring.GRADING/key).mkdir(parents=True,exist_ok=True)
    return write_new(scoring.GRADING/key/'request.json',value)


def run_one(ref):
    value = scoring.load(ref)
    folder = Path(value['directory'])
    deadline = time.monotonic()+900
    while True:
        try:
            claim = scoring.policy().claim_resource(value['resource_key'],lane=0)
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


def qualify():
    records = []
    for kind in ('gold','empty'):
        folder = scoring.GRADING/('control-v147-'+TASK+'-'+kind)
        records.append({'patch_kind':kind,**{name:reference(folder/(name+'.json'))
            for name in ('receipt','quiescence','completion')},
            'initial_container':reference(folder/'official-output/initial-container.json')})
    value = {'version':scoring.VERSION,'instance_id':TASK,'plan':reference(scoring.PLAN),
        'controls':records,'passed':True,'model_calls':0}
    output = RUN/'coordinator/qualifications'
    output.mkdir(parents=True,exist_ok=True)
    proposal = write_new(output/(TASK+'-proposal.json'),value)
    plan = scoring.load(reference(scoring.PLAN))
    scoring.build_scorer().validate_qualification(proposal,
        scoring.load(plan['environments'][TASK]['configuration']),reference(scoring.PLAN))
    return write_new(output/(TASK+'.json'),value)


def run():
    scoring.allowed()
    write_new(RUN/'started.json',{'pid':os.getpid(),'started_unix':time.time(),'model_calls':0})
    outcomes = []
    for kind in ('gold','empty'):
        result = run_one(request(kind=kind))
        outcomes.append(result)
        atomic_write(RUN/'progress.json',json_bytes({'completed':len(outcomes),'planned':4,'outcomes':outcomes}))
        print(json.dumps(result),flush=True)
    qualification = qualify()
    for index in INDICES:
        result = run_one(request(index=index,qualification=qualification))
        outcomes.append(result)
        atomic_write(RUN/'progress.json',json_bytes({'completed':len(outcomes),'planned':4,'outcomes':outcomes}))
        print(json.dumps(result),flush=True)
    return write_new(RUN/'summary.json',{'version':scoring.VERSION,'outcomes':outcomes,
        'qualification':qualification,'finished_unix':time.time(),'model_calls':0,
        'original_results_unchanged':True,'mitigation_only_not_HTTP_frame_proof':True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--prepare',action='store_true')
    choice.add_argument('--run',action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else run(),ensure_ascii=False))
