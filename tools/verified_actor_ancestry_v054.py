"""Rebuild only allowed Git ancestry while preserving official runtime versions."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verified_image_prepare_v054 import (  # noqa: E402
    DOCKER, SOCKET, daemon_identity, disk_gate, docker, now, save,
)

OUTPUT = ROOT / "runs/software-benchmark-v054/images/actor-admission-r3"
PREVIOUS = ROOT / "runs/software-benchmark-v054/images/actor-admission-r2/instances"
POLICY = ROOT / "config/v054-actor-ancestry-r3.json"

COMMON = r'''
import hashlib,json,os,shutil,subprocess,sys,tarfile
def run(args,data=None,check=True,stdout=subprocess.PIPE):
    result=subprocess.run(args,input=data,stdout=stdout,stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(repr(args[:5])+': '+result.stderr.decode('utf-8','replace')[-3000:])
    return result
def git(path,*args,**kwargs):
    return run(['git','-c','safe.directory='+path,'-C',path]+list(args),**kwargs)
def text(value):
    return value.stdout.decode().strip()
def runtime_version(python,module):
    code='import importlib,json; value=importlib.import_module('+repr(module)+'); print(json.dumps({"version":str(getattr(value,"__version__","unknown")),"module_file":str(getattr(value,"__file__","unknown"))}))'
    result=run([python,'-c',code],check=False)
    value={'returncode':result.returncode,'stdout':result.stdout.decode('utf-8','replace'),
           'stderr':result.stderr.decode('utf-8','replace')}
    if result.returncode==0:
        value.update(json.loads(value['stdout'].splitlines()[-1]))
    return value
'''

DONOR = COMMON + r'''
expected=json.loads(sys.argv[1])
root='/tmp/pws-allowed-ancestry'
os.makedirs(root)
repositories=[{'path':'','head':expected['official_head'],'tree':expected['official_tree'],
               'base':expected['dataset_base']}]
repositories += [{'path':item['path'],'head':item['official_commit'],
                   'tree':item['official_tree'],'base':item['official_commit']}
                  for item in expected.get('submodules',[])]
metadata={'repositories':[],'runtime_version':runtime_version(expected['public_python'],expected['module'])}
for index, item in enumerate(repositories):
    path='/testbed'+('/'+item['path'] if item['path'] else '')
    if text(git(path,'rev-parse','HEAD'))!=item['head'] or text(git(path,'rev-parse','HEAD^{tree}'))!=item['tree']:
        raise RuntimeError('Original repository identity changed')
    if git(path,'merge-base','--is-ancestor',item['base'],item['head'],check=False).returncode:
        raise RuntimeError('Expected base is not an ancestor of the allowed head')
    branch=git(path,'symbolic-ref','--quiet','HEAD',check=False)
    original_ref=text(branch) if branch.returncode==0 else None
    tags=[]
    rejected=[]
    for line in text(git(path,'for-each-ref','--format=%(refname) %(objectname)','refs/tags')).splitlines():
        name,oid=line.split()
        peeled=git(path,'rev-parse',name+'^{}',check=False)
        target=text(peeled)
        valid=(peeled.returncode==0 and text(git(path,'cat-file','-t',target,check=False))=='commit'
               and git(path,'merge-base','--is-ancestor',target,item['base'],check=False).returncode==0)
        descriptor={'name':name,'oid':oid,'peeled_commit':target}
        (tags if valid else rejected).append(descriptor)
    filename='repository-'+str(index)+'.pack'
    with open(root+'/'+filename,'wb') as stream:
        git(path,'pack-objects','--stdout','--revs',
            data=('\n'.join([item['head']]+[tag['oid'] for tag in tags])+'\n').encode(),stdout=stream)
    metadata['repositories'].append(dict(item,pack=filename,original_head_ref=original_ref,
       retained_tags=tags,rejected_tags=rejected,commit_count=int(text(git(path,'rev-list','--count',item['head']))),
       original_describe=text(git(path,'describe','--tags','--always','--long','--dirty',check=False))))
with open(root+'/metadata.json','w') as stream:
    json.dump(metadata,stream,sort_keys=True)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
    archive.add(root+'/metadata.json',arcname='metadata.json',recursive=False)
    for item in metadata['repositories']:
        archive.add(root+'/'+item['pack'],arcname=item['pack'],recursive=False)
'''

RESTORE = COMMON + r'''
expected=json.loads(sys.argv[1])
root='/tmp/pws-allowed-ancestry'
os.makedirs(root)
with tarfile.open('/tmp/pws-allowed-ancestry.tar','r') as archive:
    for member in archive:
        if not member.isfile() or (member.name!='metadata.json' and not (
            member.name.startswith('repository-') and member.name.endswith('.pack') and
            member.name[len('repository-'):-len('.pack')].isdigit())):
            raise RuntimeError('Unexpected ancestry transport member')
        with open(root+'/'+member.name,'wb') as output:
            shutil.copyfileobj(archive.extractfile(member),output)
with open(root+'/metadata.json') as stream:
    metadata=json.load(stream)
receipts=[]
for item in reversed(metadata['repositories']):
    path='/testbed'+('/'+item['path'] if item['path'] else '')
    control=path+'/.git'
    if os.path.islink(control):
        raise RuntimeError('Unexpected Git control symlink')
    if os.path.isdir(control):
        shutil.rmtree(control)
    elif os.path.isfile(control):
        os.unlink(control)
    git(path,'init','--quiet')
    git(path,'config','core.filemode','true')
    git(path,'config','core.logallrefupdates','false')
    with open(root+'/'+item['pack'],'rb') as source:
        p=subprocess.run(['git','-C',path,'index-pack','--stdin'],stdin=source,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError('Cannot import allowed object closure: '+p.stderr.decode()[-3000:])
    branch=item['original_head_ref']
    if branch is not None:
        if not branch.startswith('refs/heads/'):
            raise RuntimeError('Original HEAD ref is not a branch')
        git(path,'symbolic-ref','HEAD',branch)
        git(path,'update-ref',branch,item['head'])
    else:
        git(path,'update-ref','--no-deref','HEAD',item['head'])
    for tag in item['retained_tags']:
        git(path,'update-ref',tag['name'],tag['oid'])
    git(path,'read-tree',item['head'])
    git(path,'update-index','--refresh')
    git(path,'repack','-ad')
    git(path,'prune','--expire=now')
    check=git(path,'fsck','--full','--no-reflogs','--unreachable',check=False)
    commit_count=int(text(git(path,'rev-list','--count','HEAD')))
    object_types=git(path,'cat-file','--batch-all-objects','--batch-check=%(objecttype)').stdout.splitlines()
    refs=text(git(path,'for-each-ref','--format=%(refname) %(objectname)')).splitlines()
    wanted=sorted(([branch+' '+item['head']] if branch else [])+
                  [tag['name']+' '+tag['oid'] for tag in item['retained_tags']])
    beyond=text(git(path,'rev-list','--all','--not','HEAD'))
    if (check.returncode or check.stdout or check.stderr or commit_count!=item['commit_count']
            or object_types.count(b'commit')!=commit_count or sorted(refs)!=wanted or beyond
            or text(git(path,'rev-parse','HEAD'))!=item['head']
            or text(git(path,'rev-parse','HEAD^{tree}'))!=item['tree']
            or text(git(path,'status','--porcelain'))):
        raise RuntimeError('Allowed ancestry admission failed: '+item['path']+' '+check.stderr.decode()[-2000:])
    describe=text(git(path,'describe','--tags','--always','--long','--dirty',check=False))
    receipts.append({'path':item['path'],'allowed_head':item['head'],'dataset_base':item['base'],
       'tree':item['tree'],'commit_count':commit_count,'allowed_ancestry_only':True,
       'all_refs_within_allowed_ancestry':True,'no_unreachable_objects':True,'fsck_returncode':check.returncode,
       'original_head_ref':branch,'retained_tags':item['retained_tags'],'rejected_tags':item['rejected_tags'],
       'original_describe':item['original_describe'],'actor_describe':describe})
actor_version=runtime_version(expected['public_python'],expected['module'])
official_version=metadata['runtime_version']
equal=(official_version.get('returncode')==0 and actor_version.get('returncode')==0
       and actor_version.get('version')==official_version.get('version'))
if not equal:
    raise RuntimeError('Runtime version differs: '+json.dumps({'official':official_version,'actor':actor_version}))
result={'git_ancestry':next(item for item in receipts if item['path']==''),
        'submodule_ancestry':[item for item in receipts if item['path']!=''],
        'runtime_version':{'module':expected['module'],'official':official_version,'actor':actor_version,'equal':equal},
        'actor_head':text(git('/testbed','rev-parse','HEAD')),
        'actor_tree':text(git('/testbed','rev-parse','HEAD^{tree}'))}
shutil.rmtree(root)
os.unlink('/tmp/pws-allowed-ancestry.tar')
print(json.dumps(result))
'''


def policy_sha256():
    return hashlib.sha256(POLICY.read_bytes()+b'\0'+DONOR.encode()+b'\0'+RESTORE.encode()).hexdigest()


def config_blob(image_id):
    digest=image_id.removeprefix('sha256:')
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid image ID')
    data=subprocess.run(['sudo','-n','cat',str(ROOT/'runs/software-panel-v053/docker/data/image/overlay2/imagedb/content/sha256'/digest)],capture_output=True,check=True).stdout
    if hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError('Actor config identity mismatch')
    path=OUTPUT/'configs'/(digest+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    return str(path)


def prepare(prior, policy_sha):
    path=OUTPUT/'instances'/(prior['instance_id']+'.json')
    if path.exists():
        value=json.loads(path.read_bytes())
        if value['policy_sha256']!=policy_sha:
            raise ValueError('Existing r3 policy differs')
        return value
    disk_gate(OUTPUT,200*1024**3)
    record={key:value for key,value in prior.items() if key not in (
        'actor_image_id','actor_image_name','actor_config_blob','actor_config_digest','actor_head','actor_tree',
        'git_commit_object_count','old_head_unavailable','dataset_base_object_unavailable','publication_recovery',
        'recovered_from','completed_at_utc','error','error_type')}
    record.update(schema='proworksim.v054.actor-admission-r3',status='preparing',policy_sha256=policy_sha,
                  r2_actor_image_id=prior['actor_image_id'],r2_policy_sha256=prior['policy_sha256'],
                  started_at_utc=now(),network_requests=0)
    module={'scikit-learn/scikit-learn':'sklearn','pytest-dev/pytest':'pytest'}.get(prior['repo'],prior['repo'].rsplit('/',1)[-1])
    expected={key:prior[key] for key in ('official_head','official_tree','dataset_base','public_python')}
    expected.update(module=module,submodules=prior.get('submodules',[]))
    expected.update(official_image_id=prior['official_image_id'],repo=prior['repo'])
    name='pws-v054-r3-'+hashlib.sha256(prior['instance_id'].encode()).hexdigest()[:16]
    container=None
    try:
        with tempfile.TemporaryDirectory(prefix=name+'-',dir=OUTPUT) as temporary:
            archive=Path(temporary)/'allowed-ancestry.tar'
            error_log=Path(temporary)/'donor-stderr.txt'
            command=[DOCKER,'--host',SOCKET,'run','--rm','--name',name+'-donor','--network','none','--read-only',
                     '--cap-drop','ALL','--security-opt','no-new-privileges','--cpus','4','--memory','16g',
                     '--pids-limit','4096','--tmpfs','/tmp:rw,nosuid,nodev,size=2g',
                     '--env','HOME=/tmp','--env','PYTHONDONTWRITEBYTECODE=1','--workdir','/testbed',
                     '--entrypoint','/usr/bin/python3',prior['official_image_id'],'-I','-c',DONOR,json.dumps(expected)]
            with archive.open('wb') as output,error_log.open('wb') as errors:
                result=subprocess.run(command,stdout=output,stderr=errors,timeout=1200)
            if result.returncode:
                raise RuntimeError('Allowed ancestry donor failed: '+error_log.read_text()[-4000:])
            container=docker('create','--pull','never','--name',name,'--network','none','--cap-drop','ALL',
                             '--security-opt','no-new-privileges','--cpus','4','--memory','16g','--pids-limit','4096',
                             '--workdir','/testbed',
                             '--entrypoint','/bin/bash',prior['actor_image_id'],'-c','exec sleep infinity').stdout.strip()
            docker('start',container)
            docker('cp',str(archive),container+':/tmp/pws-allowed-ancestry.tar',timeout=300)
            result=docker('exec','--env','HOME=/tmp','--env','PYTHONDONTWRITEBYTECODE=1',container,
                          '/usr/bin/python3','-I','-c',RESTORE,json.dumps(expected),timeout=1200,check=False)
            if result.returncode:
                raise RuntimeError('Allowed ancestry restore failed: '+result.stderr[-5000:])
            record.update(json.loads(result.stdout))
            record['git_commit_object_count']=record['git_ancestry']['commit_count']
            for item in record.get('submodules',[]):
                ancestry=next(value for value in record['submodule_ancestry'] if value['path']==item['path'])
                item.update(shallow=False,commit_object_count=ancestry['commit_count'],git_ancestry=ancestry)
            tag='proworksim/v054-actor-r3:'+prior['instance_id'].replace('__','_')
            actor_id=docker('commit','--change','LABEL proworksim.baseline.policy='+policy_sha,container,tag,timeout=1200).stdout.strip().splitlines()[-1]
            record.update(status='actor_baseline_admitted',actor_image_id=actor_id,actor_config_digest=actor_id,
                          actor_image_name=tag,actor_config_blob=config_blob(actor_id),completed_at_utc=now())
    except Exception as error:
        record.update(status='technical_unknown',error_type=type(error).__name__,error=str(error)[:6000],completed_at_utc=now())
    finally:
        if container:
            docker('rm','--force',container,check=False)
        docker('rm','--force',name+'-donor',check=False)
    save(path,record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance',action='append')
    parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.workers<=8:
        parser.error('at most eight concurrent containers')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with (OUTPUT/'controller.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows=[json.loads(p.read_bytes()) for p in sorted(PREVIOUS.glob('*.json'))]
        if len(rows)!=500 or any(row['status']!='actor_baseline_admitted' for row in rows):
            raise ValueError('Complete existing 500-image r2 admission required')
        selected=[row for row in rows if not args.instance or row['instance_id'] in args.instance]
        if args.instance and len(selected)!=len(set(args.instance)):
            raise ValueError('Selection is outside the fixed batch')
        policy_sha=policy_sha256()
        state={'schema':'proworksim.v054.actor-ancestry-batch-r3','policy_sha256':policy_sha,
               'started_at_utc':now(),'status':'preparing','planned_instances':500,'selected_instances':len(selected),
               'workers':args.workers,'daemon':daemon_identity(),'model_calls':0,'network_requests':0,'results':{}}
        save(OUTPUT/'state.json',state)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(prepare,row,policy_sha):row['instance_id'] for row in selected}
            for future in as_completed(futures):
                value=future.result()
                state['results'][value['instance_id']]={key:value.get(key) for key in ('status','actor_image_id','error')}
                state['admitted_count']=sum(row['status']=='actor_baseline_admitted' for row in state['results'].values())
                state['technical_unknown_count']=sum(row['status']=='technical_unknown' for row in state['results'].values())
                save(OUTPUT/'state.json',state)
        state.update(status='all_selected_admitted' if state['admitted_count']==len(selected) else 'closed_with_technical_unknown',completed_at_utc=now())
        save(OUTPUT/'state.json',state)
        print(json.dumps({key:value for key,value in state.items() if key not in ('results','daemon')}))


if __name__=='__main__':
    main()
