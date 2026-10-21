"""Allow only source-proven, exact historical Git format diagnostics for r3.1."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import verified_actor_ancestry_v054 as ancestry  # noqa: E402
from tools.verified_actor_gitlinks_v054 import replacement  # noqa: E402
from tools.verified_image_prepare_v054 import now,save  # noqa: E402

EXCEPTIONS=ROOT/'config/v054-historical-git-format-exceptions-r31.json'
CONTROL=ROOT/'runs/software-benchmark-v054/images/historical-format-admission-r31'

SOURCE_INSPECTION=r'''
exception_policy=json.loads(EXCEPTION_POLICY_LITERAL)
specs=exception_policy['repos'][expected['repo']]['objects']
source_fsck=git('/testbed','fsck','--full','--no-reflogs','--unreachable',check=False)
source_lines=source_fsck.stderr.decode().splitlines()
reachable=set(line.split()[0] for line in git('/testbed','rev-list','--objects','HEAD').stdout.decode().splitlines())
source_objects=[]
for spec in specs:
    oid,kind=spec['object_id'],spec['object_type']
    raw=git('/testbed','cat-file',kind,oid).stdout
    actual=hashlib.sha1((kind+' '+str(len(raw))).encode()+b'\0'+raw).hexdigest()
    raw_sha=hashlib.sha256(raw).hexdigest()
    if (actual!=oid or raw_sha!=spec['raw_sha256'] or len(raw)!=spec['raw_bytes']
            or spec['diagnostic_line'] not in source_lines or oid not in reachable):
        raise RuntimeError('Official object does not reproduce the exact historical format diagnosis')
    source_objects.append(dict(spec,source_official_image_id=expected['official_image_id'],
       source_same_diagnostic=True,source_in_allowed_closure=True,source_object_hash_verified=True))
metadata['source_historical_format_observation']={
 'official_image_id':expected['official_image_id'],'objects':source_objects,
 'full_original_fsck_returncode':source_fsck.returncode,
 'full_original_fsck_stdout':source_fsck.stdout.decode(),
 'full_original_fsck_stderr':source_fsck.stderr.decode(),
 'policy_sha256':EXCEPTION_POLICY_SHA_LITERAL}
'''

TARGET_INSPECTION=r'''
historical_proofs=(metadata['source_historical_format_observation']['objects'] if item['path']=='' else [])
observed_lines=check.stderr.decode().splitlines()
expected_lines=[spec['diagnostic_line'] for spec in historical_proofs]
expected_code=4 if any(line.startswith('error in ') for line in expected_lines) else 0
format_only_ok=(not check.stdout and check.returncode==expected_code
                and sorted(observed_lines)==sorted(expected_lines))
connectivity=git(path,'fsck','--connectivity-only','--no-reflogs','--unreachable',check=False)
if connectivity.returncode or connectivity.stdout or connectivity.stderr:
    raise RuntimeError('Historical-format exception does not excuse connectivity failure')
checked_proofs=[]
for spec in historical_proofs:
    raw=git(path,'cat-file',spec['object_type'],spec['object_id']).stdout
    oid=hashlib.sha1((spec['object_type']+' '+str(len(raw))).encode()+b'\0'+raw).hexdigest()
    if oid!=spec['object_id'] or hashlib.sha256(raw).hexdigest()!=spec['raw_sha256'] or len(raw)!=spec['raw_bytes']:
        raise RuntimeError('Historical object changed during allowed-closure transfer')
    checked_proofs.append(dict(spec,target_object_hash_verified=True))
'''


def programs():
    body=EXCEPTIONS.read_bytes()
    exception_sha=hashlib.sha256(body).hexdigest()
    source=SOURCE_INSPECTION.replace('EXCEPTION_POLICY_LITERAL',repr(body.decode()))
    source=source.replace('EXCEPTION_POLICY_SHA_LITERAL',repr(exception_sha))
    donor=replacement(ancestry.DONOR,"for index, item in enumerate(repositories):",
                      source+"\nfor index, item in enumerate(repositories):")
    restore=replacement(ancestry.RESTORE,
                         "    commit_count=int(text(git(path,'rev-list','--count','HEAD')))",
                         '\n'.join('    '+line if line else '' for line in TARGET_INSPECTION.splitlines())
                         +"\n    commit_count=int(text(git(path,'rev-list','--count','HEAD')))")
    restore=replacement(restore,"if (check.returncode or check.stdout or check.stderr or commit_count!=item['commit_count']",
                         "if (not format_only_ok or commit_count!=item['commit_count']")
    restore=replacement(restore,"'no_unreachable_objects':True,'fsck_returncode':check.returncode,",
                         "'no_unreachable_objects':True,'fsck_returncode':check.returncode,"
                         "'fsck_structural_validation_passed':True,'fsck_connectivity_returncode':connectivity.returncode,"
                         "'historical_format_exceptions':checked_proofs,"
                         "'historical_format_exception_policy_sha256':"+repr(exception_sha)+",")
    restore=replacement(restore,"result={'git_ancestry':",
                         "result={'source_historical_format_observation':metadata['source_historical_format_observation'],"
                         "'git_ancestry':")
    policy_sha=hashlib.sha256(ancestry.POLICY.read_bytes()+b'\0'+body+b'\0'+donor.encode()+b'\0'+restore.encode()).hexdigest()
    return donor,restore,policy_sha,exception_sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance',action='append')
    parser.add_argument('--workers',type=int,default=16)
    args=parser.parse_args()
    if not 1<=args.workers<=16:
        parser.error('at most sixteen preparation containers')
    CONTROL.mkdir(parents=True,exist_ok=True)
    donor,restore,sha,exception_sha=programs()
    policy=json.loads(EXCEPTIONS.read_bytes())
    state={'schema':'proworksim.v054.historical-format-admission-r31','started_at_utc':now(),
           'status':'waiting_for_original_batch','policy_sha256':sha,
           'historical_format_exception_policy_sha256':exception_sha,'workers':args.workers,
           'model_calls':0,'network_requests':0,'results':{}}
    save(CONTROL/'state.json',state)
    with (ancestry.OUTPUT/'controller.lock').open('a+b') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(30)
        selected=[]
        for path in sorted((ancestry.OUTPUT/'instances').glob('*.json')):
            failed=json.loads(path.read_bytes())
            if failed['status']!='technical_unknown' or (args.instance and failed['instance_id'] not in args.instance):
                continue
            specs=policy['repos'].get(failed['repo'],{}).get('objects',[])
            if not specs or not all(item['diagnostic_line'] in failed.get('error','') for item in specs):
                raise ValueError('Failure outside the exact historical format exception set')
            previous=json.loads((ancestry.PREVIOUS/path.name).read_bytes())
            history=ancestry.OUTPUT/'prior-attempts'/failed['instance_id']/(str(time.time_ns())+'.json')
            history.parent.mkdir(parents=True,exist_ok=True)
            path.rename(history)
            selected.append(previous)
        state.update(status='preparing_exact_exceptions',selected_instances=len(selected))
        save(CONTROL/'state.json',state)
        ancestry.DONOR,ancestry.RESTORE=donor,restore
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(ancestry.prepare,previous,sha):previous['instance_id'] for previous in selected}
            for future in as_completed(futures):
                result=future.result()
                result.update(schema='proworksim.v054.actor-admission-r3.1',
                              historical_format_exception_policy_sha256=exception_sha,
                              base_ancestry_policy_sha256=policy['parent_ancestry_policy_sha256'])
                save(ancestry.OUTPUT/'instances'/(result['instance_id']+'.json'),result)
                state['results'][result['instance_id']]={key:result.get(key) for key in ('status','actor_image_id','error')}
                state['admitted_count']=sum(row['status']=='actor_baseline_admitted' for row in state['results'].values())
                save(CONTROL/'state.json',state)
        state.update(status='closed',completed_at_utc=now())
        save(CONTROL/'state.json',state)
        batch_path=ancestry.OUTPUT/'state.json'
        batch=json.loads(batch_path.read_bytes())
        save(CONTROL/('prior-main-state-'+str(time.time_ns())+'.json'),batch)
        batch['results'].update(state['results'])
        batch['admitted_count']=sum(row['status']=='actor_baseline_admitted' for row in batch['results'].values())
        batch['technical_unknown_count']=sum(row['status']=='technical_unknown' for row in batch['results'].values())
        batch.update(status='all_selected_admitted' if batch['admitted_count']==500 else 'closed_with_technical_unknown',
                     historical_format_revision_policy_sha256=sha,completed_at_utc=now())
        save(batch_path,batch)
        print(json.dumps({key:value for key,value in state.items() if key!='results'}))


if __name__=='__main__':
    main()
