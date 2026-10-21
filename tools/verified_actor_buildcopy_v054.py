"""Close the one observed official untracked, redundant Requests build copy."""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import verified_actor_baseline_v054 as baseline  # noqa: E402
from tools.verified_actor_gitlinks_v054 import replacement  # noqa: E402
from tools.verified_image_prepare_v054 import now, save  # noqa: E402

EXTENSION = ROOT / "config/v054-actor-requests-buildcopy-r1.json"
CONTROL = ROOT / "runs/software-benchmark-v054/images/buildcopy-admission-r1"

REMOVE_COPY = r'''
observed_status=text(git('status','--porcelain'))
extension=policy['buildcopy_extension']
if observed_status!=extension['observed_initial_status']:
    raise RuntimeError('Observed Requests build-copy state changed')
if git('diff','--exit-code',check=False).returncode or git('diff','--cached','--exit-code',check=False).returncode:
    raise RuntimeError('Tracked Requests baseline changed')
untracked=git('ls-files','--others','--exclude-standard','-z').stdout.split(b'\0')
copy_proofs=[]
for value in untracked:
    if not value:
        continue
    relative=value.decode()
    prefix='build/lib/requests/'
    if not relative.startswith(prefix):
        raise RuntimeError('Unrecognized untracked public entry: '+relative)
    copied='/testbed/'+relative
    original='/testbed/requests/'+relative[len(prefix):]
    if (os.path.islink(copied) or os.path.islink(original)
            or not os.path.isfile(copied) or not os.path.isfile(original)):
        raise RuntimeError('Duplicate must be a contained regular public file')
    with open(copied,'rb') as stream:
        left=stream.read()
    with open(original,'rb') as stream:
        right=stream.read()
    if left!=right:
        raise RuntimeError('Untracked build copy differs from public original: '+relative)
    copy_proofs.append({'path':relative,'public_original':original,'bytes':len(left),
                        'sha256':hashlib.sha256(left).hexdigest()})
if not copy_proofs:
    raise RuntimeError('No proven duplicate exists')
shutil.rmtree('/testbed/build/lib/requests')
for empty in ('/testbed/build/lib','/testbed/build'):
    if os.path.isdir(empty) and not os.listdir(empty):
        os.rmdir(empty)
'''


def policy_identity():
    policy, parent_sha = baseline.policy_identity()
    extension = json.loads(EXTENSION.read_bytes())
    policy['buildcopy_extension'] = extension
    program = replacement(baseline.CONTAINER_PROGRAM,
                          "if text(git('status','--porcelain')):",
                          REMOVE_COPY + "\nif text(git('status','--porcelain')):")
    program = replacement(program, "'source_module_paths':source_paths}))",
                          "'source_module_paths':source_paths,'removed_public_build_duplicates':copy_proofs}))")
    sha = hashlib.sha256(baseline.POLICY_PATH.read_bytes()+b'\0'
                         +EXTENSION.read_bytes()+b'\0'+program.encode()).hexdigest()
    return policy, sha, parent_sha, program


def main():
    CONTROL.mkdir(parents=True, exist_ok=True)
    policy, sha, parent_sha, program = policy_identity()
    extension=policy['buildcopy_extension']
    with (baseline.OUTPUT/'controller.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan=json.loads(baseline.SOURCE.read_bytes())
        row=next(item for item in plan['images'] if item['instance_id']==extension['instance_id'])
        if row['config_digest']!=extension['official_image_id'] or row.get('status')!='loaded':
            raise ValueError('Original fixed Requests image differs')
        path=baseline.OUTPUT/'instances'/(row['instance_id']+'.json')
        prior=json.loads(path.read_bytes())
        if prior['status']=='actor_baseline_admitted' and prior['policy_sha256']==sha:
            return
        if (prior['status']!='technical_unknown' or prior['policy_sha256']!=parent_sha
                or 'Official setup checkout is not clean' not in prior.get('error','')):
            raise ValueError('Prior failure does not match this necessary repair')
        history=baseline.OUTPUT/'prior-attempts'/row['instance_id']/(str(time.time_ns())+'.json')
        history.parent.mkdir(parents=True,exist_ok=True)
        path.rename(history)
        baseline.CONTAINER_PROGRAM=program
        result=baseline.prepare(row,policy,sha)
        result.update(base_policy_sha256=parent_sha,buildcopy_extension=extension['version'])
        save(path,result)
        save(CONTROL/'state.json',{'at_utc':now(),'policy_sha256':sha,'result':result,'model_calls':0})
        batch_path=baseline.OUTPUT/'state.json'
        batch=json.loads(batch_path.read_bytes())
        save(CONTROL/'previous-main-batch-state.json',batch)
        batch['results'][row['instance_id']]={'status':result['status'],'actor_image_id':result.get('actor_image_id'),'error':result.get('error')}
        batch['admitted_count']=sum(item['status']=='actor_baseline_admitted' for item in batch['results'].values())
        batch['technical_unknown_count']=sum(item['status']=='technical_unknown' for item in batch['results'].values())
        batch.update(status='all_selected_admitted' if batch['admitted_count']==500 else 'closed_with_technical_unknown',
                     buildcopy_extension_policy_sha256=sha,completed_at_utc=now())
        save(batch_path,batch)
        print(json.dumps({'instance_id':row['instance_id'],'status':result['status'],'actor_image_id':result.get('actor_image_id')}))


if __name__=='__main__':
    main()
