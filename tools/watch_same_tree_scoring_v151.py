"""Four-hour formal scoring after pure recovery of normally completed exports.

Only proven normal controller completions repaired by v149 enter two bounded
official scorers. Only technical scoring failures receive one same-candidate retry.
No generation/API, no historical-result writes, no control reruns or new services.
"""
from __future__ import annotations

import argparse
import importlib.util
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

ROOT=scoring.ROOT
RUN=ROOT/'runs/software-benchmark-v151/same-tree-score-handoff-r1'
OLD=scoring.RUN
spec=importlib.util.spec_from_file_location('v150_owned_scoring_handoff_basis',ROOT/'tools/watch_normal_export_scoring_v150.py')
legacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
VERSION='v151-same-tree-official-score-reuse-handoff-r1'
prepare_request=legacy.prepare_request
run_one=legacy.run_one
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


def existing_attempts(row,endpoint):
    values=[]
    for attempt,infix in ((1,''),(2,'retry-')):
        key=('score-' if endpoint=='code' else 'delivery-score-')+infix+str(row['slot_index'])
        folder=scoring.GRADING/key
        claim=OLD/'resource-claims'/(key+'.json')
        if not claim.exists():
            continue
        completion=folder/'completion.json'
        quiet=folder/'quiescence.json'
        if not completion.exists() or not quiet.exists():
            raise PermissionError('A consumed predecessor scorer has no complete exit proof')
        value=scoring.load(reference(completion))
        proof=scoring.load(reference(quiet))
        if (proof.get('quiescent') is not True or proof.get('cleanup_errors')!=[]
                or proof.get('create_result_unknown') is not False):
            raise PermissionError('A consumed predecessor scorer is not quiescent')
        values.append({**value,'completion':reference(completion),'scoring_attempt':attempt})
    return values


def reuse_same_tree(row,export_ref,code):
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    value=exports.validate_export_result_bounded(export_ref,row)
    if value.get('submitted') is not True or value.get('same_tree') is not True:
        raise ValueError('Only an actual legal submission of the same final tree can reuse code scoring')
    code_lock=scoring.load(value['candidate_lock'])
    delivery_lock=scoring.load(value['delivery_lock'])
    if (code_lock['tree_sha256']!=delivery_lock['tree_sha256']
            or scoring.load(code_lock['patch_receipt'])['patch']!=scoring.load(delivery_lock['patch_receipt'])['patch']):
        raise ValueError('Code and legal-delivery candidate bytes differ')
    if code.get('state')!='scored' or code.get('cleanup_proven') is not True or code.get('returncode')!=0:
        raise ValueError('A completed known code score is required')
    request=scoring.load(code['request'])
    receipt=scoring.load(code['receipt'])
    identity=scoring.load(receipt['identity'])
    report=receipt.get('official_result',[None,{}])[1].get(row['instance_id'],{})
    folder=Path(request['directory'])
    quiet=scoring.load(reference(folder/'quiescence.json'))
    if (request.get('slot_id')!=row['slot_id'] or request.get('candidate_lock')!=value['candidate_lock']
            or request.get('generation_result')!=export_ref
            or receipt.get('status')!='official_report' or type(receipt.get('resolved')) is not bool
            or receipt.get('resolved') is not code.get('resolved')
            or identity.get('request')!=code['request'] or identity.get('candidate_lock')!=value['candidate_lock']
            or identity.get('endpoint')!='code' or identity.get('plan')!=reference(scoring.PLAN)
            or identity.get('scorer_manifest')!=reference(OLD/'coordinator/scorer-manifest.json')
            or report.get('resolved') is not receipt['resolved']
            or report.get('patch_successfully_applied') is not True or report.get('infra_failure')
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors')!=[]):
        raise ValueError('The same-tree reuse lost exact official candidate, environment or cleanup evidence')
    return {'version':VERSION,'slot_id':row['slot_id'],'slot_index':row['slot_index'],
        'endpoint':'delivery','state':'same_tree_official_result_reused','resolved':code['resolved'],
        'normal_generation_export_recovered':True,'export_result':export_ref,
        'code_receipt':code['receipt'],'code_request':code['request'],
        'code_candidate_lock':value['candidate_lock'],'delivery_candidate_lock':value['delivery_lock'],
        'legal_delivery_evidence':value['delivery_evidence'],'closure_proof':value['closure_proof'],
        'new_containers':0,'new_model_calls':0,'original_records_unchanged':True,
        'historical_additional_delivery_scores':[v['completion'] for v in existing_attempts(row,'delivery')]}


def prepare():
    RUN.mkdir(parents=True,exist_ok=True)
    scoring.allowed()
    return retain(RUN/'proposal.json',{'version':VERSION,'source':reference(__file__),
        'original_plan':reference(scoring.PLAN),'original_authorization':reference(scoring.AUTH),
        'original_sources':reference(scoring.SOURCE),'maximum_containers_unchanged':168,
        'maximum_parallel_scorers_unchanged':2,'same_tree_reuses_known_code':True,
        'different_tree_delivery_scored_separately':True,'original_deadline_preserved':True,
        'new_model_calls':0,'host_configuration_changes':False})


def authorize_handoff():
    scoring.allowed()
    old_start=scoring.load(reference(OLD/'started.json'))
    old_summary=scoring.load(reference(OLD/'summary.json'))
    stop=scoring.load(reference(RUN/'old-watcher-stop.json'))
    if stop.get('old_pid')!=old_start['pid'] or stop.get('process_exited') is not True:
        raise PermissionError('The exact old watcher has not demonstrably exited')
    plan=scoring.load(reference(scoring.PLAN))
    consumed=[]
    for row in plan['rows']:
        for endpoint in ('code','delivery'):
            consumed.extend(v['completion'] for v in existing_attempts(row,endpoint))
    return retain(RUN/'authorization.json',{'version':VERSION,'proposal':reference(RUN/'proposal.json'),
        'source':reference(__file__),'predecessor_summary':reference(OLD/'summary.json'),
        'predecessor_stop':reference(RUN/'old-watcher-stop.json'),
        'already_consumed_completed_scorers':consumed,
        'latest_predecessor_reason':old_summary['stop_reason'],
        'original_deadline_unix':old_start['started_unix']+old_start['watch_seconds'],
        'only_unused_original_resource_identities':True,'resource_ceiling_not_extended':True,
        'new_model_calls':0})


def watch():
    from proworksim import software_benchmark_closed_export_recovery_v149 as exports
    scoring.allowed()
    auth=scoring.load(reference(RUN/'authorization.json'))
    if auth['source']!=reference(__file__):
        raise PermissionError('The reviewed handoff source changed')
    plan=scoring.load(reference(scoring.PLAN))
    deadline=time.monotonic()+max(0,auth['original_deadline_unix']-time.time())
    write_new(RUN/'started.json',{'version':VERSION,'pid':os.getpid(),'started_unix':time.time(),
        'original_deadline_unix':auth['original_deadline_unix'],'new_model_calls':0})
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    states,canonical,handled,pending,active,deferred={},{},set(),deque(),{},{}
    available,queued=[0,1],set()
    last_poll=-1e9
    reason='original_watcher_deadline'
    export_done=False
    def key(row,endpoint):
        return str(row['slot_index'])+':'+endpoint
    def run_job(job,lane):
        row,endpoint,ref,attempt,prior=job
        request_ref=prepare_request(row,endpoint,ref,attempt=attempt,prior_completion=prior)
        return run_one(request_ref,deadline,lane)
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='v151-score') as pool:
        while time.monotonic()<deadline or active:
            changed=False
            for future,(job,lane) in list(active.items()):
                if not future.done():
                    continue
                del active[future]
                available.append(lane)
                row,endpoint,ref,attempt,prior=job
                target=key(row,endpoint)
                queued.discard(target)
                changed=True
                try:
                    result=future.result()
                    states[target]=result
                    if result['state']=='scored':
                        completion=reference(Path(scoring.load(result['request'])['directory'])/'completion.json')
                        canonical[target]={**result,'completion':completion,'export_result':ref,
                            'slot_id':row['slot_id'],'slot_index':row['slot_index'],'endpoint':endpoint}
                        handled.add(target)
                    elif result['state']=='technical_unknown':
                        completion=reference(Path(scoring.load(result['request'])['directory'])/'completion.json')
                        if attempt==1 and not stop.is_set():
                            pending.append((row,endpoint,ref,2,completion))
                            queued.add(target)
                        else:
                            canonical[target]={**result,'completion':completion,'export_result':ref}
                            handled.add(target)
                    elif result['state']=='blocked_cleanup':
                        reason='owned_scoring_cleanup_not_proven'
                        stop.set()
                    else:
                        deferred[target]=job
                        queued.add(target)
                except Exception as error:
                    resource=('score-' if endpoint=='code' else 'delivery-score-')+('retry-' if attempt==2 else '')+str(row['slot_index'])
                    consumed=(OLD/'resource-claims'/(resource+'.json')).exists()
                    states[target]={'state':'blocked_owned_execution' if consumed else 'waiting_evidence',
                        'error':{'type':type(error).__name__,'message':str(error)}}
                    if consumed:
                        reason='owned_scoring_incomplete'
                        stop.set()
                    else:
                        deferred[target]=job
                        queued.add(target)
            if not stop.is_set() and time.monotonic()-last_poll>=POLL_SECONDS:
                last_poll=time.monotonic()
                changed=True
                for job in deferred.values():
                    pending.append(job)
                deferred.clear()
                export_done=(exports.OUTPUT/'summary.json').is_file()
                progress=exports.OUTPUT/'progress.json'
                if progress.is_file():
                    try:
                        export_done=export_done or json.loads(progress.read_bytes()).get('complete') is True
                    except (OSError,ValueError):
                        pass
                for row in sorted(plan['rows'],key=lambda r:r['slot_index']):
                    path=exports.OUTPUT/str(row['slot_index'])/'recovery-result.json'
                    for endpoint in ('code','delivery'):
                        target=key(row,endpoint)
                        if target in handled or target in queued:
                            continue
                        if not path.exists():
                            states[target]={'state':'skip_not_exported' if export_done else 'waiting_normal_export'}
                            if export_done:
                                handled.add(target)
                            continue
                        try:
                            ref=reference(path)
                            exported=scoring.load(ref)
                            if exported.get('row')!=row or exported.get('completed_work_proven_before_export') is not True:
                                raise ValueError('The new normal export lacks its exact original row')
                            if endpoint=='delivery' and exported.get('submitted') is not True:
                                canonical[target]={'state':'no_legal_delivery','resolved':False,'export_result':ref,
                                    'slot_id':row['slot_id'],'slot_index':row['slot_index'],'endpoint':endpoint,
                                    'normal_generation_export_recovered':True,'new_containers':0}
                                states[target]=canonical[target]
                                handled.add(target)
                                continue
                            if endpoint=='delivery' and exported.get('same_tree') is True:
                                code=canonical.get(key(row,'code'))
                                if code and code.get('state')=='scored':
                                    value=reuse_same_tree(row,ref,code)
                                    receipt=retain(RUN/'same-tree-delivery'/(str(row['slot_index'])+'.json'),value)
                                    canonical[target]={**value,'receipt':receipt}
                                    states[target]=canonical[target]
                                    handled.add(target)
                                elif key(row,'code') in handled:
                                    canonical[target]={'state':'same_tree_code_technical_unknown','resolved':None,
                                        'export_result':ref,'new_containers':0,'new_model_calls':0}
                                    states[target]=canonical[target]
                                    handled.add(target)
                                else:
                                    states[target]={'state':'waiting_same_tree_code_score'}
                                continue
                            previous=existing_attempts(row,endpoint)
                            known=next((v for v in previous if v['state']=='scored'),None)
                            if known:
                                canonical[target]={**known,'export_result':ref,'slot_id':row['slot_id'],
                                    'slot_index':row['slot_index'],'endpoint':endpoint,'inherited_known_score':True}
                                states[target]=canonical[target]
                                handled.add(target)
                            elif len(previous)>=2:
                                canonical[target]={**previous[-1],'export_result':ref,'inherited_final_unknown':True}
                                states[target]=canonical[target]
                                handled.add(target)
                            else:
                                attempt=2 if previous else 1
                                prior=previous[-1]['completion'] if previous else None
                                pending.append((row,endpoint,ref,attempt,prior))
                                queued.add(target)
                                states[target]={'state':'queued','attempt':attempt,'export_result':ref}
                        except Exception as error:
                            states[target]={'state':'waiting_evidence','error':{'type':type(error).__name__,'message':str(error)}}
            while pending and available and not stop.is_set() and time.monotonic()+2400<=deadline:
                job=pending.popleft()
                lane=available.pop(0)
                active[pool.submit(run_job,job,lane)]=(job,lane)
            if changed:
                atomic_write(RUN/'canonical-results.json',json_bytes({'version':VERSION,'results':canonical,
                    'same_tree_delivery_reuses_code':True,'old_score_receipts_unchanged':True,'new_model_calls':0}))
                atomic_write(RUN/'watch-progress.json',json_bytes({'version':VERSION,'pid':os.getpid(),
                    'updated_unix':time.time(),'targets':states,'handled':len(handled),
                    'active_scorers':len(active),'pending_scorers':len(pending)+len(deferred),
                    'normal_exporter_finished':export_done,'original_deadline_unix':auth['original_deadline_unix'],
                    'scorers_created_total':sum((OLD/'resource-claims'/(k+'.json')).exists() for k in plan['resources'])}))
            if export_done and len(handled)==84 and not active and not pending:
                reason='all_normal_exports_classified_and_scored'
                break
            if stop.is_set() and not active:
                break
            if time.monotonic()>=deadline and not active:
                break
            time.sleep(1) if stop.is_set() else stop.wait(1)
    return write_new(RUN/'summary.json',{'version':VERSION,'finished_unix':time.time(),
        'stop_reason':reason,'targets':states,'canonical_results':canonical,
        'old_score_receipts_unchanged':True,'new_model_calls':0})


def launch():
    scoring.allowed()
    auth=scoring.load(reference(RUN/'authorization.json'))
    if auth['source']!=reference(__file__) or (RUN/'started.json').exists() or (RUN/'launch-result.json').exists():
        raise PermissionError('A changed or consumed successor owner cannot start')
    argv=[str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).resolve()),'--watch']
    with (RUN/'watcher.stdout.log').open('xb') as stdout,(RUN/'watcher.stderr.log').open('xb') as stderr:
        process=subprocess.Popen(argv,cwd=ROOT,env=scoring.base.clean_environment(),
            stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
    return write_new(RUN/'launch-result.json',{'pid':process.pid,'started_unix':time.time(),
        'source':reference(__file__),'authorization':reference(RUN/'authorization.json'),
        'original_deadline_unix':auth['original_deadline_unix'],'new_model_calls':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare','authorize-handoff','launch','watch'):
        modes.add_argument('--'+name,action='store_true')
    args=parser.parse_args()
    value=(prepare() if args.prepare else authorize_handoff() if args.authorize_handoff else
           launch() if args.launch else watch())
    print(json.dumps(value,ensure_ascii=False),flush=True)

