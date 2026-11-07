"""Four-hour formal scoring after pure recovery of normally completed exports.

Only proven normal controller completions repaired by v149 enter two bounded
official scorers. Only technical scoring failures receive one same-candidate retry.
No generation/API, no historical-result writes, no control reruns or new services.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from proworksim import software_benchmark_rescore_v150 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT,RUN = scoring.ROOT,scoring.RUN
WATCH_SECONDS = 4*3600
POLL_SECONDS = 60


def command(*args):
    return [str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-m','proworksim.software_benchmark_rescore_v150',*map(str,args)]


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
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    RUN.mkdir(parents=True,exist_ok=True)
    (RUN/'coordinator').mkdir(exist_ok=True)
    original=scoring.load(reference(scoring.active.scope.PLAN_FILE))
    rows=original['rows']
    if len(rows)!=42 or {r['slot_index'] for r in rows}!=set(range(10200,10242)):
        raise ValueError('Only the frozen42 v146 identities may use formal export recovery')
    plan={'version':scoring.VERSION,'original_plan':reference(scoring.active.scope.PLAN_FILE),
        'rows':rows,'resources':{},'environments':original['environments'],
        'constraints':scoring.CONSTRAINTS,'new_model_calls':0,'new_environment_controls':0,
        'watch_seconds':WATCH_SECONDS,'poll_seconds':POLL_SECONDS,
        'normal_controller_work_closed_required':True,'maximum_scoring_attempts_per_endpoint':2}
    for row in rows:
        for endpoint,prefix in [('code','score-'),('delivery','delivery-score-')]:
            for infix in ('','retry-'):
                key=prefix+infix+str(row['slot_index'])
                plan['resources'][key]={**original['resources'][key],'recovery_round':None,
                    'score_retry':False,'overlay_endpoint':endpoint,'same_locked_candidate_required':True}
    plan_ref=write_new(scoring.PLAN,plan)
    instance=scoring.build_scorer(manifest_provider=lambda:{})
    instance.environment.prepare()
    completed=subprocess.run(command('--manifest'),cwd=ROOT,env=scoring.base.clean_environment(),
        capture_output=True,text=True,timeout=120,check=True)
    manifest_ref=write_new(RUN/'coordinator/scorer-manifest.json',json.loads(completed.stdout))
    qualifications={}
    for task,env in plan['environments'].items():
        ref=(reference(scoring.qualified.RUN/'coordinator/qualifications'/(task+'.json'))
             if task=='psf__requests-1766' else
             reference(scoring.active.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json')))
        instance.validate_qualification(ref,scoring.load(env['configuration']),plan_ref)
        qualifications[task]=ref
    write_new(RUN/'qualifications.json',qualifications)
    sources=[reference(scoring.__file__),reference(__file__),reference(exports.__file__),reference(exports.closure.__file__)]
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
        'authorization_basis':'Requested actual evaluation and automatic technical network recovery; standing non-disruptive experiment Docker permission',
        'scope':'Only42 v146 normally closed and v149 exported original candidates; each code/delivery at most2 scoring attempts',
        'model_calls':0,'new_volumes':0,'new_controls':0,'new_services':0,
        'maximum_TLS_sessions':32,'maximum_connections':16384,'maximum_payload_bytes':2048*1024**2,
        'watch_seconds':WATCH_SECONDS,'poll_seconds':POLL_SECONDS,'host_configuration_changes':False})
    return {'plan':plan_ref,'source':source_ref,'authorization':auth,'qualified_tasks':len(qualifications),
            'manifest':manifest_ref,'operations':0}


def prepare_request(row,endpoint,export_ref,*,attempt=1,prior_completion=None):
    result=scoring.load(export_ref)
    field='candidate_lock' if endpoint=='code' else 'delivery_lock'
    key=('score-' if endpoint=='code' else 'delivery-score-')+('retry-' if attempt==2 else '')+str(row['slot_index'])
    admission={'slot_id':row['slot_id'],'slot_index':row['slot_index'],'endpoint':endpoint,
        'export_result':export_ref,'candidate_lock':result[field],'scoring_attempt':attempt,
        'normal_generation_export_recovered':True}
    if attempt==2:
        first=scoring.load(prior_completion)
        admission.update(prior_completion=prior_completion,prior_request=first['request'])
    scoring.validate_admission(admission)
    admission_ref=retain(RUN/'admissions'/(key+'.json'),admission)
    scorer=scoring.build_scorer(manifest_provider=lambda:scoring.load(reference(RUN/'coordinator/scorer-manifest.json')))
    value={'version':scoring.VERSION,'resource_key':key,'instance_id':row['instance_id'],
        'slot_id':row['slot_id'],'source_slot_id':row['source_slot_id'],
        'configuration':row['configuration'],'patch_kind':None,'candidate_lock':result[field],
        'generation_result':export_ref,'measurement_kind':row['measurement_kind'],
        'group_id':row['group_id'],'organization_id':row['organization_id'],
        'plan':reference(scoring.PLAN),'limits':scorer.LIMITS,
        'qualification':scoring.load(reference(RUN/'qualifications.json'))[row['instance_id']],
        'scorer_manifest':reference(RUN/'coordinator/scorer-manifest.json'),
        'directory':str(scoring.GRADING/key),'cpuset_cpus':None,
        'delivery_evidence':result.get('delivery_evidence') if endpoint=='delivery' else None,
        'recovery_admission':admission_ref,**scorer.environment.request_fields(row['instance_id'])}
    return retain(scoring.GRADING/key/'request.json',value)


def run_one(ref,deadline,lane):
    request=scoring.load(ref)
    folder=Path(request['directory'])
    if time.monotonic()+2400>deadline:
        return {'state':'waiting_watcher_deadline','request':ref}
    try:
        claim=scoring.policy().claim_resource(request['resource_key'],lane=lane)
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
        'original_scores_changed':False,'same_candidate_scoring_revision':scoring.VERSION,'normal_generation_export_recovered':True}
    write_new(folder/'completion.json',result)
    return result


def watch():
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    scoring.allowed()
    plan=scoring.load(reference(scoring.PLAN))
    rows={row['slot_id']:row for row in plan['rows']}
    deadline=time.monotonic()+WATCH_SECONDS
    started={'pid':os.getpid(),'started_unix':time.time(),'watch_seconds':WATCH_SECONDS,
        'poll_seconds':POLL_SECONDS,'model_calls':0,'maximum_containers':168}
    write_new(RUN/'started.json',started)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    states,overlays,handled,pending,active={},{},set(),deque(),{}
    deferred_jobs={}
    available=[0,1]
    queued=set()
    last_poll=-1e9
    stop_reason='watcher_deadline'
    export_done=False
    def identity(row,endpoint):
        return str(row['slot_index'])+':'+endpoint
    def execute(job,lane):
        row,endpoint,ref,attempt,prior=job
        request_ref=prepare_request(row,endpoint,ref,attempt=attempt,prior_completion=prior)
        return run_one(request_ref,deadline,lane)
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='v150-score') as pool:
        while time.monotonic()<deadline or active:
            changed=False
            for future,(job,lane) in list(active.items()):
                if not future.done():
                    continue
                del active[future]
                available.append(lane)
                row,endpoint,ref,attempt,prior=job
                key=identity(row,endpoint)
                queued.discard(key)
                changed=True
                try:
                    value=future.result()
                    states[key]=value
                    if value['state'] in {'scored','technical_unknown','blocked_cleanup'}:
                        request=scoring.load(value['request'])
                        completion=reference(Path(request['directory'])/'completion.json')
                        entry={'slot_id':row['slot_id'],'slot_index':row['slot_index'],
                            'group_id':row['organization_id'],'endpoint':endpoint,
                            'export_result':ref,'scoring_attempt':attempt,'completion':completion,**value}
                        overlays.setdefault(key,[]).append(entry)
                        atomic_write(RUN/'overlay-results.json',json_bytes({
                            'version':scoring.VERSION,'results':overlays,
                            'normal_generation_export_recovered':True,
                            'original_records_unchanged':True,'new_model_calls':0}))
                        if value['state']=='technical_unknown' and attempt==1 and not stop.is_set():
                            pending.append((row,endpoint,ref,2,completion))
                            queued.add(key)
                            states[key]={**value,'retry_queued':True}
                        else:
                            handled.add(key)
                        if value['state']=='blocked_cleanup':
                            stop_reason='owned_scorer_cleanup_not_proven'
                            stop.set()
                    else:
                        deferred_jobs[key]=job
                        queued.add(key)
                except Exception as error:
                    prefix=('score-' if endpoint=='code' else 'delivery-score-')+('retry-' if attempt==2 else '')
                    consumed=(RUN/'resource-claims'/(prefix+str(row['slot_index'])+'.json')).exists()
                    states[key]={'state':'blocked_own_execution' if consumed else 'waiting_evidence',
                        'error':{'type':type(error).__name__,'message':str(error)}}
                    if consumed:
                        stop_reason='own_scoring_execution_incomplete'
                        stop.set()
                    else:
                        deferred_jobs[key]=job
                        queued.add(key)
            now=time.monotonic()
            if not stop.is_set() and now-last_poll>=POLL_SECONDS:
                last_poll=now
                changed=True
                for job in deferred_jobs.values():
                    pending.append(job)
                deferred_jobs.clear()
                export_done=(exports.OUTPUT/'summary.json').is_file()
                progress=exports.OUTPUT/'progress.json'
                if progress.is_file():
                    try:
                        export_done=export_done or json.loads(progress.read_bytes()).get('complete') is True
                    except (ValueError,OSError):
                        pass
                for row in sorted(rows.values(),key=lambda r:(r['slot_index']!=10209,r['slot_index'])):
                    path=exports.OUTPUT/str(row['slot_index'])/'recovery-result.json'
                    for endpoint in ('code','delivery'):
                        key=identity(row,endpoint)
                        if key in handled or key in queued:
                            continue
                        if not path.is_file():
                            states[key]={'state':'skip_not_exported' if export_done else 'waiting_normal_export'}
                            if export_done:
                                handled.add(key)
                            continue
                        try:
                            ref=reference(path)
                            value=scoring.load(ref)
                            if (value.get('completed_work_proven_before_export') is not True
                                    or value.get('row')!=row or value.get('model_resampling') is not False):
                                raise ValueError('An unfinished model or foreign row cannot enter formal recovery scoring')
                            if endpoint=='delivery' and value.get('submitted') is not True:
                                entry={'slot_id':row['slot_id'],'slot_index':row['slot_index'],
                                    'endpoint':endpoint,'state':'no_legal_delivery','resolved':False,
                                    'export_result':ref,'new_model_calls':0,'new_containers':0,
                                    'normal_generation_export_recovered':True}
                                states[key]=entry
                                overlays[key]=[entry]
                                handled.add(key)
                                continue
                            pending.append((row,endpoint,ref,1,None))
                            queued.add(key)
                            states[key]={'state':'queued','export_result':ref}
                        except Exception as error:
                            states[key]={'state':'waiting_export_evidence','error':{'type':type(error).__name__,'message':str(error)}}
            while pending and available and not stop.is_set() and time.monotonic()+2400<=deadline:
                job=pending.popleft()
                lane=available.pop(0)
                active[pool.submit(execute,job,lane)]=(job,lane)
            if changed:
                atomic_write(RUN/'watch-progress.json',json_bytes({'version':scoring.VERSION,
                    'pid':os.getpid(),'updated_unix':time.time(),'targets':states,'handled':len(handled),
                    'planned_endpoints':84,'normal_exporter_finished':export_done,
                    'active_scorers':len(active),'pending_scorers':len(pending)+len(deferred_jobs),
                    'scorers_created':sum((RUN/'resource-claims'/(key+'.json')).is_file() for key in plan['resources']),
                    'remaining_seconds':max(0,deadline-time.monotonic()),'new_model_calls':0}))
            if export_done and len(handled)==84 and not active and not pending:
                stop_reason='all_normal_exports_classified_and_scored'
                break
            if stop.is_set() and not active:
                break
            if time.monotonic()>=deadline and not active:
                break
            time.sleep(1) if stop.is_set() else stop.wait(1)
    if stop.is_set() and stop_reason=='watcher_deadline':
        stop_reason='requested_stop_after_owned_work'
    atomic_write(RUN/'overlay-results.json',json_bytes({'version':scoring.VERSION,'results':overlays,
        'normal_generation_export_recovered':True,'original_records_unchanged':True,'new_model_calls':0}))
    return write_new(RUN/'summary.json',{'version':scoring.VERSION,'started':started,
        'finished_unix':time.time(),'stop_reason':stop_reason,'targets':states,'overlays':overlays,
        'unstarted_jobs':[{'slot_id':job[0]['slot_id'],'endpoint':job[1],'attempt':job[3]}
                          for job in [*pending,*deferred_jobs.values()]],
        'normal_generation_export_recovered':True,'original_records_unchanged':True,
        'new_model_calls':0,'new_services_or_slices':0})


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
