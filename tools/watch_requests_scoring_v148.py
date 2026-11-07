"""Four-hour, sixty-second read-only polling of eight bounded scoring endpoints.

Only normally closed v146 Requests1766 attempts whose final primary scoring
remains technical-unknown enter a serial, identical-candidate idle180 scorer.
No generation/API, no historical-result writes, no control reruns or new services.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from proworksim import software_benchmark_rescore_v148 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT,RUN = scoring.ROOT,scoring.RUN
WATCH_SECONDS = 4*3600
POLL_SECONDS = 60


def command(*args):
    return [str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-m','proworksim.software_benchmark_rescore_v148',*map(str,args)]


def retain(path,value):
    path=Path(path)
    if path.exists():
        ref=reference(path)
        if scoring.load(ref)!=value:
            raise ValueError('An immutable watcher artifact changed')
        return ref
    path.parent.mkdir(parents=True,exist_ok=True)
    return write_new(path,value)


def prepare():
    RUN.mkdir(parents=True,exist_ok=True)
    (RUN/'coordinator').mkdir(exist_ok=True)
    original=scoring.load(reference(scoring.active.scope.PLAN_FILE))
    rows=[r for r in original['rows'] if r['slot_index'] in scoring.TARGET_INDICES]
    if (len(rows)!=4 or {r['slot_index'] for r in rows}!=set(scoring.TARGET_INDICES)
            or any(r['instance_id']!='psf__requests-1766' for r in rows)):
        raise ValueError('The exact four declared Requests1766 identities changed')
    plan={'version':scoring.VERSION,'original_plan':reference(scoring.active.scope.PLAN_FILE),
        'rows':rows,'resources':{},'environments':{'psf__requests-1766':original['environments']['psf__requests-1766']},
        'constraints':scoring.CONSTRAINTS,'new_model_calls':0,'new_environment_controls':0,
        'watch_seconds':WATCH_SECONDS,'poll_seconds':POLL_SECONDS,
        'final_primary_technical_unknown_required':True,'normal_primary_failures_retried':False}
    for row in rows:
        for endpoint,prefix in [('code','score-'),('delivery','delivery-score-')]:
            key=prefix+str(row['slot_index'])
            plan['resources'][key]={**original['resources'][key],'recovery_round':None,
                'score_retry':False,'overlay_endpoint':endpoint,'same_locked_candidate_required':True}
    plan_ref=write_new(scoring.PLAN,plan)
    instance=scoring.build_scorer(manifest_provider=lambda:{})
    instance.environment.prepare()
    completed=subprocess.run(command('--manifest'),cwd=ROOT,env=scoring.base.clean_environment(),
        capture_output=True,text=True,timeout=120,check=True)
    manifest_ref=write_new(RUN/'coordinator/scorer-manifest.json',json.loads(completed.stdout))
    qualification=reference(scoring.qualified.RUN/'coordinator/qualifications/psf__requests-1766.json')
    instance.validate_qualification(qualification,scoring.load(rows[0]['configuration']),plan_ref)
    sources=[reference(scoring.__file__),reference(__file__)]
    for original_index in [scoring.qualified.SOURCE,scoring.active.scope.SOURCE_FILE]:
        index_ref=reference(original_index)
        sources.append(index_ref)
        for ref in scoring.load(index_ref)['files']:
            scoring.checked(ref)
            if ref not in sources:
                sources.append(ref)
    source_ref=write_new(scoring.SOURCE,{'files':sources,'active_runtime_changed':False})
    auth=write_new(scoring.AUTH,{'status':'authorized_by_current_user_instructions',
        'plan':plan_ref,'source_index':source_ref,'constraints':scoring.CONSTRAINTS,
        'authorization_basis':'Requested automatic recovery of technical network scoring failures; standing non-disruptive experiment Docker permission',
        'scope':'Only v146 Requests1766 indices10214,10215,10235,10236; code/delivery each at most once',
        'model_calls':0,'new_volumes':0,'new_controls':0,'new_services':0,
        'maximum_TLS_sessions':8,'maximum_connections':4096,'maximum_payload_bytes':512*1024**2,
        'watch_seconds':WATCH_SECONDS,'poll_seconds':POLL_SECONDS,'host_configuration_changes':False})
    return {'plan':plan_ref,'source':source_ref,'authorization':auth,'qualification':qualification,
            'manifest':manifest_ref,'operations':0}


def prepare_request(row,endpoint,admission):
    scoring.validate_admission(admission)
    key=('score-' if endpoint=='code' else 'delivery-score-')+str(row['slot_index'])
    admission_ref=retain(RUN/'admissions'/(key+'.json'),admission)
    result=scoring.load(admission['generation_result'])
    original=scoring.load(admission['prior_request'])
    scorer=scoring.build_scorer(manifest_provider=lambda:scoring.load(reference(RUN/'coordinator/scorer-manifest.json')))
    fields=scorer.environment.request_fields(row['instance_id'])
    value={**original,'version':scoring.VERSION,'resource_key':key,'plan':reference(scoring.PLAN),
        'candidate_lock':admission['candidate_lock'],'generation_result':admission['generation_result'],
        'qualification':reference(scoring.qualified.RUN/'coordinator/qualifications/psf__requests-1766.json'),
        'scorer_manifest':reference(RUN/'coordinator/scorer-manifest.json'),
        'directory':str(scoring.GRADING/key),'cpuset_cpus':None,
        'delivery_evidence':result.get('delivery_evidence') if endpoint=='delivery' else None,
        'recovery_admission':admission_ref,**fields}
    value.pop('retry_of_request',None)
    return retain(scoring.GRADING/key/'request.json',value)


def run_one(ref,deadline):
    request=scoring.load(ref)
    folder=Path(request['directory'])
    if time.monotonic()+2400>deadline:
        return {'state':'waiting_watcher_deadline','request':ref}
    try:
        claim=scoring.policy().claim_resource(request['resource_key'],lane=0)
    except scoring.dispatch.ResourceBusy:
        return {'state':'waiting_capacity','request':ref}
    write_new(folder/'capacity-claim.json',{'prepared_request':ref,'claim':claim})
    with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
        process=subprocess.Popen(command('--request',ref['path']),cwd=ROOT,
            env=scoring.base.clean_environment(),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        try:
            code=process.wait(timeout=2100)
        except subprocess.TimeoutExpired:
            process.terminate()
            code=process.wait(timeout=240)
    quiet_path,receipt_path=folder/'quiescence.json',folder/'receipt.json'
    quiet=scoring.load(reference(quiet_path)) if quiet_path.exists() else {}
    receipt=scoring.load(reference(receipt_path)) if receipt_path.exists() else {}
    clean=(quiet.get('quiescent') is True and quiet.get('cleanup_errors')==[]
           and quiet.get('create_result_unknown') is False)
    known=clean and code==0 and receipt.get('status')=='official_report' and type(receipt.get('resolved')) is bool
    result={'state':'scored' if known else 'technical_unknown' if clean else 'blocked_cleanup',
        'request':ref,'returncode':code,'cleanup_proven':clean,
        'receipt':reference(receipt_path) if receipt_path.exists() else None,
        'resolved':receipt.get('resolved') if known else None,'model_calls':0,
        'original_scores_changed':False,'same_candidate_scoring_revision':scoring.VERSION}
    write_new(folder/'completion.json',result)
    return result


def watch():
    scoring.allowed()
    plan=scoring.load(reference(scoring.PLAN))
    deadline=time.monotonic()+WATCH_SECONDS
    started={'pid':os.getpid(),'started_unix':time.time(),'watch_seconds':WATCH_SECONDS,
        'poll_seconds':POLL_SECONDS,'model_calls':0,'maximum_containers':8}
    write_new(RUN/'started.json',started)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    states,overlays,handled={},{},set()
    stop_reason='watcher_deadline'
    while not stop.is_set() and time.monotonic()<deadline:
        for row in sorted(plan['rows'],key=lambda r:r['slot_index']):
            for endpoint in ('code','delivery'):
                key=str(row['slot_index'])+':'+endpoint
                if key in handled or stop.is_set():
                    continue
                try:
                    admission=scoring.inspect_target(row,endpoint)
                    states[key]=admission
                    if admission['state'].startswith('skip_'):
                        handled.add(key)
                    elif admission['state']=='eligible':
                        if time.monotonic()+2400>deadline:
                            states[key]={'state':'waiting_watcher_deadline'}
                            continue
                        request_ref=prepare_request(row,endpoint,admission)
                        result=run_one(request_ref,deadline)
                        states[key]=result
                        if result['state'] in {'scored','technical_unknown','blocked_cleanup'}:
                            handled.add(key)
                            overlays[key]={'slot_id':row['slot_id'],'slot_index':row['slot_index'],
                                'endpoint':endpoint,'primary_admission':admission,**result}
                            atomic_write(RUN/'overlay-results.json',json_bytes({
                                'version':scoring.VERSION,'results':overlays,
                                'original_records_unchanged':True,'new_model_calls':0}))
                        if result['state']=='blocked_cleanup':
                            stop_reason='owned_scorer_cleanup_not_proven'
                            stop.set()
                except Exception as error:
                    # A half-written primary JSON during a lightweight poll is
                    # retried on the next poll; a consumed own identity is not.
                    resource=('score-' if endpoint=='code' else 'delivery-score-')+str(row['slot_index'])
                    consumed=(RUN/'resource-claims'/(resource+'.json')).exists()
                    states[key]={'state':'blocked_own_execution' if consumed else 'waiting_evidence',
                        'error':{'type':type(error).__name__,'message':str(error)}}
                    if consumed:
                        stop_reason='own_scoring_execution_incomplete'
                        stop.set()
        primary_finished=(scoring.active.scope.API_ROOT/'run-summary.json').is_file()
        atomic_write(RUN/'watch-progress.json',json_bytes({'version':scoring.VERSION,
            'pid':os.getpid(),'updated_unix':time.time(),'targets':states,'handled':len(handled),
            'planned_endpoints':8,'primary_finished':primary_finished,
            'scorers_created':sum((RUN/'resource-claims'/(key+'.json')).is_file()
                                 for key in plan['resources']),
            'remaining_seconds':max(0,deadline-time.monotonic()),'new_model_calls':0}))
        if primary_finished and len(handled)==8:
            stop_reason='primary_finished_all_targets_handled'
            break
        stop.wait(min(POLL_SECONDS,max(0,deadline-time.monotonic())))
    if stop.is_set() and stop_reason=='watcher_deadline':
        stop_reason='requested_stop_after_owned_work'
    return write_new(RUN/'summary.json',{'version':scoring.VERSION,'started':started,
        'finished_unix':time.time(),'stop_reason':stop_reason,'targets':states,'overlays':overlays,
        'original_records_unchanged':True,'new_model_calls':0,'new_services_or_slices':0})


def launch():
    scoring.allowed()
    if (RUN/'launch-intent.json').exists() or (RUN/'started.json').exists():
        raise ValueError('An existing watcher identity cannot be launched twice')
    argv=[str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).resolve()),'--watch']
    write_new(RUN/'launch-intent.json',{'argv':argv,'created_unix':time.time(),
        'authority':reference(scoring.AUTH),'source':reference(scoring.SOURCE)})
    with (RUN/'watcher.stdout.log').open('xb') as stdout,(RUN/'watcher.stderr.log').open('xb') as stderr:
        process=subprocess.Popen(argv,cwd=ROOT,env=scoring.base.clean_environment(),
            stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
    return write_new(RUN/'launch-result.json',{'pid':process.pid,'started_unix':time.time(),
        'new_user_process':True,'system_service_or_slice_created':False,'new_model_calls':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    for option in ('prepare','launch','watch'):
        group.add_argument('--'+option,action='store_true')
    args=parser.parse_args()
    result=prepare() if args.prepare else launch() if args.launch else watch()
    print(json.dumps(result,ensure_ascii=False),flush=True)
