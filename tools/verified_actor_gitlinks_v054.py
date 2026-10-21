"""Finish the six structurally identified gitlink baselines after the r2 batch."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import verified_actor_baseline_v054 as baseline  # noqa: E402
from tools.verified_image_prepare_v054 import now, save  # noqa: E402

EXTENSION = ROOT / "config/v054-actor-gitlinks-r1.json"
CONTROL = ROOT / "runs/software-benchmark-v054/images/gitlink-admission-r1"

CAPTURE = r'''
def subgit(path,*args,**kwargs):
    return command(['git','-c','safe.directory='+path,'-C',path]+list(args),**kwargs)
def indexed(path):
    normal=[]
    links=[]
    for entry in subgit(path,'ls-files','--stage','-z').stdout.split(b'\0'):
        if not entry:
            continue
        descriptor,name=entry.split(b'\t',1)
        mode,oid,stage=descriptor.decode().split()
        if stage!='0':
            raise RuntimeError('Unmerged index in public baseline')
        if mode=='160000':
            links.append({'path':name.decode(),'oid':oid})
        else:
            normal.append(name)
    return b'\0'.join(normal)+b'\0',links
root_normal,root_links=indexed('/testbed')
submodules=[]
def capture_submodule(relative,expected):
    path='/testbed/'+relative
    if not in_checkout(path) or not os.path.exists(path+'/.git'):
        raise RuntimeError('Expected initialized contained public submodule: '+relative)
    head=text(subgit(path,'rev-parse','HEAD'))
    if head!=expected or text(subgit(path,'status','--porcelain')):
        raise RuntimeError('Submodule checkout differs from official gitlink: '+relative)
    normal,links=indexed(path)
    item={'path':relative,'official_commit':head,
          'official_tree':text(subgit(path,'rev-parse','HEAD^{tree}')),
          'raw_commit':subgit(path,'cat-file','commit',head).stdout,
          'normal':normal,'links':links,
          'ignored':subgit(path,'ls-files','--others','--ignored','--exclude-standard','-z').stdout}
    submodules.append(item)
    for link in links:
        capture_submodule(relative+'/'+link['path'],link['oid'])
for link in root_links:
    capture_submodule(link['path'],link['oid'])
if not submodules:
    raise RuntimeError('Gitlink extension requires an actual initialized submodule')
tracked=root_normal
'''

REBUILD = r'''
submodule_receipts=[]
for item in reversed(submodules):
    path='/testbed/'+item['path']
    if os.path.lexists(path+'/.git'):
        remove(path+'/.git')
    subgit(path,'init','--quiet')
    subgit(path,'config','core.filemode','true')
    subgit(path,'config','core.logallrefupdates','false')
    subgit(path,'update-index','--add','-z','--stdin',data=item['normal'])
    for link in item['links']:
        subgit(path,'update-index','--add','--cacheinfo','160000,'+link['oid']+','+link['path'])
    tree=text(subgit(path,'write-tree'))
    if tree!=item['official_tree']:
        raise RuntimeError('Submodule public tree changed: '+item['path'])
    commit=text(subgit(path,'hash-object','-t','commit','-w','--stdin',data=item['raw_commit']))
    if commit!=item['official_commit']:
        raise RuntimeError('Submodule current commit identity changed')
    with open(path+'/.git/shallow','w') as stream:
        stream.write(commit+'\n')
    subgit(path,'symbolic-ref','HEAD','refs/heads/v054-baseline')
    subgit(path,'update-ref','refs/heads/v054-baseline',commit)
    check=subgit(path,'fsck','--full','--strict','--no-reflogs','--unreachable',check=False)
    objects=subgit(path,'cat-file','--batch-all-objects','--batch-check=%(objecttype)').stdout.splitlines()
    count=objects.count(b'commit')
    clean=not text(subgit(path,'status','--porcelain'))
    ignored=subgit(path,'ls-files','--others','--ignored','--exclude-standard','-z').stdout
    if check.returncode or check.stdout or check.stderr or count!=1 or not clean or ignored!=item['ignored']:
        raise RuntimeError('Submodule isolation check failed: '+item['path'])
    submodule_receipts.append({'path':item['path'],'official_commit':commit,'official_tree':tree,
       'actor_commit':commit,'actor_tree':tree,'commit_object_count':count,'shallow':True,
       'working_tree_clean':clean,'git_fsck_returncode':check.returncode,
       'old_object_database_removed':True,'parent_gitlink_oid_preserved':True,
       'ignored_build_artifact_count':len(ignored.split(b'\0'))-1})
'''


def replacement(program, before, after):
    if program.count(before) != 1:
        raise ValueError("Base program changed: explicit extension review required")
    return program.replace(before, after)


def extended_program():
    program = baseline.CONTAINER_PROGRAM
    program = replacement(program, "tracked=git('ls-files','-z').stdout", CAPTURE)
    program = replacement(program, "shutil.rmtree('/testbed/.git')",
                          "shutil.rmtree('/testbed/.git')\n" + REBUILD)
    program = replacement(program, "git('update-index','--add','-z','--stdin',data=tracked)",
                          "git('update-index','--add','-z','--stdin',data=tracked)\n"
                          "for link in root_links:\n"
                          "    git('update-index','--add','--cacheinfo','160000,'+link['oid']+','+link['path'])")
    return replacement(program, "'source_module_paths':source_paths}))",
                       "'source_module_paths':source_paths,'submodules':submodule_receipts,"
                       "'parent_gitlinks':root_links}))")


def policy_identity():
    policy, base_sha = baseline.policy_identity()
    extension = json.loads(EXTENSION.read_bytes())
    policy['gitlink_extension'] = extension
    program = extended_program()
    sha = hashlib.sha256(baseline.POLICY_PATH.read_bytes() + b'\0'
                         + EXTENSION.read_bytes() + b'\0' + program.encode()).hexdigest()
    return policy, sha, base_sha, program


def main():
    CONTROL.mkdir(parents=True, exist_ok=True)
    policy, sha, base_sha, program = policy_identity()
    state = {'schema': 'proworksim.v054.gitlink-admission-r1', 'status': 'waiting_for_original_batch',
             'started_at_utc': now(), 'policy_sha256': sha, 'base_policy_sha256': base_sha,
             'model_calls': 0, 'network_requests': 0, 'workers': 6, 'results': {}}
    save(CONTROL / 'state.json', state)
    with (baseline.OUTPUT / 'controller.lock').open('a+b') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(30)
        plan = json.loads(baseline.SOURCE.read_bytes())
        identities = policy['gitlink_extension']['affected_instances']
        selected = [row for row in plan['images'] if row['instance_id'] in identities]
        if len(selected) != 6 or any(row.get('status') != 'loaded' for row in selected):
            raise ValueError('All six original loaded identities are required')
        for row in selected:
            path = baseline.OUTPUT / 'instances' / (row['instance_id'] + '.json')
            prior = json.loads(path.read_bytes())
            if prior['status'] == 'actor_baseline_admitted' and prior['policy_sha256'] == sha:
                continue
            if (prior['status'] != 'technical_unknown' or prior['policy_sha256'] != base_sha
                    or 'astropy_helpers' not in prior.get('error','')):
                raise ValueError('Extension does not match prior structural failure')
            history = baseline.OUTPUT / 'prior-attempts' / row['instance_id'] / (str(time.time_ns())+'.json')
            history.parent.mkdir(parents=True,exist_ok=True)
            path.rename(history)
        baseline.CONTAINER_PROGRAM = program
        state['status'] = 'preparing_gitlink_tasks'
        save(CONTROL / 'state.json', state)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for result in pool.map(lambda row: baseline.prepare(row, policy, sha), selected):
                result['base_policy_sha256'] = base_sha
                result['gitlink_extension'] = policy['gitlink_extension']['version']
                save(baseline.OUTPUT / 'instances' / (result['instance_id']+'.json'), result)
                state['results'][result['instance_id']] = {
                    'status': result['status'], 'actor_image_id': result.get('actor_image_id'),
                    'error': result.get('error')}
                save(CONTROL / 'state.json', state)
        state.update(status='closed', completed_at_utc=now(),
                     admitted_count=sum(row['status']=='actor_baseline_admitted' for row in state['results'].values()))
        save(CONTROL / 'state.json', state)
        batch_path=baseline.OUTPUT / 'state.json'
        batch=json.loads(batch_path.read_bytes())
        save(CONTROL / 'previous-main-batch-state.json',batch)
        batch['results'].update(state['results'])
        batch['admitted_count']=sum(row['status']=='actor_baseline_admitted' for row in batch['results'].values())
        batch['technical_unknown_count']=sum(row['status']=='technical_unknown' for row in batch['results'].values())
        batch.update(status='all_selected_admitted' if batch['admitted_count']==500 else 'closed_with_technical_unknown',
                     gitlink_extension_policy_sha256=sha, completed_at_utc=now())
        save(batch_path,batch)
        print(json.dumps({key:value for key,value in state.items() if key!='results'}))


if __name__ == '__main__':
    main()
