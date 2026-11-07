"""One bounded user-level cache hint for completed pilot files; deletes nothing.

No global drop_caches, cgroup writes, process signals, runtime edits or new jobs.
Only clean cached pages of eligible private regular files may be discarded by
POSIX_FADV_DONTNEED; this is advisory and does not remove file contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'runs/software-benchmark-v142/role-pilot40-r1'
API=BATCH/'deployment-v143/api-coordinator'
OUTPUT=ROOT/'artifacts/software-benchmark-v144/completed-cache-advice-r1'
CGROUP=Path('/sys/fs/cgroup')/f'user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice/proworksim-v142-role-pilot.service'
GIB=1024**3
MAX_FILES=32
MAX_BYTES=8*GIB
TARGET_BYTES=26*GIB
NAMES=('controller-output.tar.zst','baseline-snapshot.tar.gz','baseline-snapshot.json','terminal-snapshot.tar.gz','terminal-snapshot.json')


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    p=Path(path).resolve()
    raw=p.read_bytes()
    return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def load_ref(value):
    if ref(value['path'])!=value:
        raise ValueError('Completion evidence changed')
    return read(value['path'])


def memory():
    values={key:int((CGROUP/key).read_text()) for key in ('memory.current','memory.high','memory.max')}
    if (values['memory.high'],values['memory.max'])!=(30*GIB,32*GIB):
        raise ValueError('Only the unchanged reviewed pilot manager may be observed')
    counts=dict(row.split() for row in (CGROUP/'memory.stat').read_text().splitlines())
    return {**values,'anon_bytes':int(counts['anon']),'file_bytes':int(counts['file'])}


def qualify(score_ref):
    score=load_ref(score_ref)
    row=score['row']
    if not 10000<=row['slot_index']<=10119 or not row['slot_id'].startswith('v142:'):
        raise ValueError('Foreign task')
    delivery=score.get('delivery',{})
    if (score.get('cleanup_proven') is not True or score.get('official_endpoint',{}).get('status')!='scored'
            or type(delivery.get('resolved')) is not bool or delivery.get('scoring_request') is not None):
        raise ValueError('Code or delivery still requires work')
    generation=load_ref(score['generation_result'])
    quiet=load_ref(generation['quiescence'])
    if (generation.get('status')!='closed' or quiet.get('quiescent') is not True
            or quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors')!=[]):
        raise ValueError('Task writers or resource cleanup remain unproven')
    return row


def identity(path):
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1:
        raise ValueError('Only current-user private regular files, without hard links')
    return {'device':s.st_dev,'inode':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns}


def prepare():
    if os.getuid()==0 or os.geteuid()==0:
        raise PermissionError('Ordinary user only')
    candidates=[]
    for path in sorted((API/'score-records').glob('*-code.json')):
        try:
            proof=ref(path)
            row=qualify(proof)
        except ValueError:
            continue
        folder=BATCH/'episodes'/str(row['slot_index'])
        for name in NAMES:
            path=folder/name
            if not path.is_file():
                continue
            try:
                metadata=identity(path)
            except ValueError:
                continue
            if metadata['size']>=32*1024**2:
                candidates.append({'path':str(path.resolve()),'identity':metadata,'score_record':proof})
    selected=[]
    total=0
    for item in sorted(candidates,key=lambda r:r['identity']['size'],reverse=True):
        size=item['identity']['size']
        if len(selected)<MAX_FILES and total+size<=MAX_BYTES:
            selected.append(item)
            total+=size
    OUTPUT.mkdir(parents=True,exist_ok=True)
    plan={'version':'v144-completed-private-file-cache-advice-r1','source':ref(__file__),
        'before':memory(),'files':selected,'nominal_file_bytes':total,'maximum_files':MAX_FILES,
        'maximum_nominal_bytes':MAX_BYTES,'target_manager_bytes':TARGET_BYTES,
        'global_cache_control':False,'file_deletion':False,'content_write':False,'runtime_change':False}
    with (OUTPUT/'plan.json').open('x') as stream:
        json.dump(plan,stream,ensure_ascii=False,indent=2)
    return plan


def execute():
    if os.getuid()==0 or os.geteuid()==0 or (OUTPUT/'execution.json').exists():
        raise PermissionError('Only one ordinary-user hint pass is allowed')
    plan=read(OUTPUT/'plan.json')
    if (plan['source']!=ref(__file__) or len(plan['files'])>MAX_FILES
            or sum(r['identity']['size'] for r in plan['files'])>MAX_BYTES):
        raise ValueError('The bounded file inventory changed')
    result={'plan':ref(OUTPUT/'plan.json'),'started_unix':time.time(),'before':memory(),
            'actions':[],'data_deleted':False,'host_or_runtime_configuration_changed':False}
    with (OUTPUT/'execution.json').open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    for item in plan['files']:
        if memory()['memory.current']<=TARGET_BYTES:
            break
        row=qualify(item['score_record'])
        path=Path(item['path'])
        if (path.parent!=BATCH/'episodes'/str(row['slot_index']) or path.name not in NAMES
                or path.resolve()!=path or identity(path)!=item['identity']):
            raise ValueError('File is outside its unchanged completed task')
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            opened=os.fstat(descriptor)
            if (opened.st_dev,opened.st_ino)!=(item['identity']['device'],item['identity']['inode']):
                raise ValueError('The opened file identity changed')
            os.posix_fadvise(descriptor,0,0,os.POSIX_FADV_DONTNEED)
        finally:
            os.close(descriptor)
        if identity(path)!=item['identity']:
            raise ValueError('A supposedly completed file changed during the hint')
        result['actions'].append({'path':str(path),'file_identity_unchanged':True,
            'advice':'POSIX_FADV_DONTNEED','nominal_bytes':item['identity']['size']})
    result.update(after=memory(),finished_unix=time.time(),
                  nominal_bytes_are_not_claimed_reclaimed_memory=True)
    with (OUTPUT/'result.json').open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true')
    modes.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    result=prepare() if args.prepare else execute()
    print(json.dumps({k:v for k,v in result.items() if k not in {'files','actions'}},ensure_ascii=False))
