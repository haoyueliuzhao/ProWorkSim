"""Lossless content-addressed archive for the fixed fourteen closed v050 JSON files.

Only an explicit allowlist is mutable. Archive validation precedes every raw
removal. Historical SHA references remain meaningful after explicit restore;
old records and outcomes are never rewritten. No model or credential is read.
"""
from __future__ import annotations
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'runs/history-archive-v050-r1'
VERSION='v050-closed-history-lossless-archive-r1'
ROOT_NAMES=['software-learning-v050-resume-r'+str(i) for i in range(1,7)]+['software-learning-v050-resume-r6-restored']
ALLOWLIST=[ROOT/'runs'/name/leaf for name in ROOT_NAMES for leaf in ('entries.json','pretraining-admission.json')]
CHUNK=1024**2


def digest_path(path):
    h=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        while data:=stream.read(CHUNK):h.update(data);size+=len(data)
    return {'path':str(Path(path).resolve()),'sha256':h.hexdigest(),'bytes':size}


def identity(path):
    st=Path(path).lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or Path(path).resolve()!=Path(path):
        raise ValueError('Allowlisted raw must be a distinct regular nonsymlink file')
    return {'device':st.st_dev,'inode':st.st_ino,'nlink':st.st_nlink,'bytes':st.st_size,
            'allocated_bytes':st.st_blocks*512,'mtime_ns':st.st_mtime_ns,
            'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}


def put(path,value):
    path=Path(path)
    raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def load_ref(ref):
    if digest_path(ref['path'])!=ref:raise ValueError('Immutable archive metadata changed')
    return json.loads(Path(ref['path']).read_bytes())


def no_candidate_process_use():
    """Refuse observed same-user uses; existing supervisor closure is separately sealed."""
    targets=set(map(str,ALLOWLIST));roots={str(p.parent) for p in ALLOWLIST};matches=[];denied=0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
        try:
            if entry.stat().st_uid!=os.getuid():continue
            command=(entry/'cmdline').read_bytes()
            if any(root.encode() in command for root in roots):matches.append({'pid':int(entry.name),'kind':'command_root'})
            for fd in (entry/'fd').iterdir():
                try:target=os.readlink(fd)
                except OSError:continue
                if target in targets:matches.append({'pid':int(entry.name),'kind':'open_candidate','path':target})
        except OSError:denied+=1
    if matches:raise RuntimeError('Candidate may be in use: '+json.dumps(matches))
    return {'observed_candidate_uses':[],'same_uid_proc_denied':denied,
            'scope':'same_uid_proc_plus_sealed_closed_supervisors_not_universal_other_user_proof'}


def fingerprint():
    OUT.mkdir(exist_ok=False)
    audit=ROOT/'runs/software-benchmark-v055/history-compression-readonly-r1/current-reference-audit.json'
    evidence=json.loads(audit.read_bytes())
    if not evidence.get('queue_exhausted') or evidence.get('candidate_prefix_matches'):
        raise ValueError('Current host reference exclusion is incomplete or contains a candidate')
    supervisors=[]
    for name in ROOT_NAMES:
        path=ROOT/'runs'/name/'supervisor.json';value=json.loads(path.read_bytes())
        if value.get('status') not in ('complete','closed_with_unknowns') or not value.get('ended_at'):
            raise ValueError('Historical supervisor has not closed')
        supervisors.append({'reference':digest_path(path),'status':value['status'],'ended_at':value['ended_at']})
    use=no_candidate_process_use();rows=[]
    for path in ALLOWLIST:
        before=identity(path);ref=digest_path(path)
        if identity(path)!=before:raise RuntimeError('Raw changed during fingerprint')
        rows.append({'original':ref,'identity':before,'supervisor':next(x for x in supervisors if Path(x['reference']['path']).parent==path.parent)})
        print(json.dumps({'event':'fingerprinted','path':str(path),'bytes':ref['bytes']}),flush=True)
    groups={}
    for row in rows:groups.setdefault(row['original']['sha256'],[]).append(row['original']['path'])
    return put(OUT/'plan.json',{'version':VERSION,'created_unix':time.time(),'source':digest_path(__file__),
        'current_reference_audit':digest_path(audit),'same_user_process_observation':use,
        'allowlist':rows,'content_groups':groups,'codec':'gzip','compression_level':1,
        'remove_raw_only_after_full_decompression_sha256_verification':True,
        'historical_results_unchanged':True,'default_restore_root':str(OUT/'restored'),
        'required_resources':{'CPUQuota':'200%','MemoryMax':'2147483648','IOWeight':'10','Nice':'10','IOSchedulingClass':'idle'}})


class HashingWriter:
    def __init__(self,stream):self.stream=stream;self.hash=hashlib.sha256();self.size=0
    def write(self,data):
        n=self.stream.write(data)
        if n!=len(data):raise OSError('Short archive write')
        self.hash.update(data);self.size+=n;return n
    def flush(self):self.stream.flush()


def make_object(rows,objects):
    first=rows[0];source=Path(first['original']['path']);sha=first['original']['sha256']
    final=objects/(sha+'.json.gz');partial=objects/(sha+'.json.gz.partial')
    if final.exists() or partial.exists():raise FileExistsError('An existing attempt is retained; explicit recovery required')
    if identity(source)!=first['identity']:raise RuntimeError('Raw source identity changed')
    rawhash=hashlib.sha256();rawsize=0
    with source.open('rb') as original,partial.open('xb') as rawout:
        writer=HashingWriter(rawout)
        with gzip.GzipFile(filename='',mode='wb',fileobj=writer,compresslevel=1,mtime=0) as encoded:
            while data:=original.read(CHUNK):encoded.write(data);rawhash.update(data);rawsize+=len(data)
        rawout.flush();os.fsync(rawout.fileno())
        compressed_sha,compressed_size=writer.hash.hexdigest(),writer.size
    if rawhash.hexdigest()!=sha or rawsize!=first['original']['bytes'] or identity(source)!=first['identity']:
        raise RuntimeError('Raw bytes changed while encoding; preserve original')
    # Exactly one full readback verification of each unique compressed object.
    decoded_hash=hashlib.sha256();decoded_bytes=0
    with gzip.open(partial,'rb') as stream:
        while data:=stream.read(CHUNK):decoded_hash.update(data);decoded_bytes+=len(data)
    if decoded_hash.hexdigest()!=sha or decoded_bytes!=rawsize:
        raise ValueError('Full archive readback differs; preserve every original')
    os.link(partial,final);partial.unlink()
    proof={'version':VERSION,'original_sha256':sha,'original_bytes':rawsize,
           'archive':{'path':str(final),'sha256':compressed_sha,'bytes':compressed_size},
           'codec':'gzip','level':1,'full_decompression_sha256_verified':True,
           'verified_unix':time.time(),'source_raw':first['original']}
    return put(objects/(sha+'.verified.json'),proof),proof


def archive(plan_ref):
    plan=load_ref(plan_ref)
    if plan['version']!=VERSION or plan['source']!=digest_path(__file__):raise ValueError('Unknown archive implementation')
    if [Path(row['original']['path']) for row in plan['allowlist']]!=ALLOWLIST:raise ValueError('Only fixed fourteen paths are authorized')
    load_ref(plan['current_reference_audit'])
    for row in plan['allowlist']:
        load_ref(row['supervisor']['reference'])
        if identity(row['original']['path'])!=row['identity']:raise RuntimeError('Allowlist identity changed')
    no_candidate_process_use()
    objects=OUT/'objects';objects.mkdir(exist_ok=False)
    receipts=OUT/'paths';receipts.mkdir(exist_ok=False)
    removed=[];failures=[];groups=[]
    with (OUT/'archive.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for sha,paths in plan['content_groups'].items():
            rows=[row for row in plan['allowlist'] if row['original']['sha256']==sha]
            try:
                object_ref,proof=make_object(rows,objects)
                groups.append({'verification':object_ref,'archive':proof['archive'],'original_paths':paths})
                no_candidate_process_use()
                for row in rows:
                    path=Path(row['original']['path'])
                    if identity(path)!=row['identity']:raise RuntimeError('Raw identity changed before release')
                    marker={'version':VERSION,'state':'archived_raw_available_via_explicit_restore','original':row['original'],
                        'original_identity':row['identity'],'plan':plan_ref,'verified_object':object_ref,
                        'restore_tool':str(Path(__file__).resolve()),'default_restore_root':plan['default_restore_root'],
                        'old_sha_references_require_restore_to_original_path_before_normal_validation':True}
                    marker_ref=put(path.with_name(path.name+'.archive.json'),marker)
                    path.unlink()
                    released={'original':row['original'],'original_identity':row['identity'],
                              'marker':marker_ref,'archive':proof['archive'],'released_unix':time.time()}
                    put(receipts/(hashlib.sha256(str(path).encode()).hexdigest()+'.json'),released)
                    removed.append(released)
                    print(json.dumps({'event':'archived_and_raw_released','path':str(path),'bytes':row['original']['bytes']}),flush=True)
            except Exception as error:
                failure={'group_sha256':sha,'error':{'type':type(error).__name__,'message':str(error)},'automatic_retry':False}
                put(OUT/('failure-'+sha+'.json'),failure);failures.append(failure)
    result={'version':VERSION,'plan':plan_ref,'finished_unix':time.time(),'removed_paths':removed,'objects':groups,'failures':failures,
            'released_raw_allocated_bytes':sum(row['original_identity']['allocated_bytes'] for row in removed),
            'compressed_object_bytes':sum(group['archive']['bytes'] for group in groups),
            'file_content_lost':False,'experimental_outcomes_modified':False,'model_calls':0}
    return put(OUT/'result.json',result)


def restore(plan_ref,*,destination=None,original_paths=False,selected=None):
    plan=load_ref(plan_ref)
    if plan['version']!=VERSION:raise ValueError('Unknown archive plan')
    targetroot=Path(destination).resolve() if destination else Path(plan['default_restore_root'])
    if original_paths and destination:raise ValueError('Choose new-directory or original-path restore')
    rows=[row for row in plan['allowlist'] if selected is None or row['original']['path']==selected]
    if not rows:raise ValueError('Requested path is absent from the archive index')
    for row in rows:
        original=Path(row['original']['path']);sha=row['original']['sha256']
        if original not in ALLOWLIST:raise ValueError('Archive path escaped the fixed historical allowlist')
        proof=json.loads((OUT/'objects'/(sha+'.verified.json')).read_bytes())
        if proof['original_sha256']!=sha or proof['original_bytes']!=row['original']['bytes'] or not proof['full_decompression_sha256_verified']:
            raise ValueError('Archive object metadata does not match original identity')
        target=original if original_paths else targetroot/original.relative_to(ROOT)
        if target.exists() or target.is_symlink():raise FileExistsError('Restore refuses to overwrite '+str(target))
        target.parent.mkdir(parents=True,exist_ok=True)
        partial=target.with_name(target.name+'.restore-partial')
        h=hashlib.sha256();size=0
        with gzip.open(proof['archive']['path'],'rb') as encoded,partial.open('xb') as stream:
            while data:=encoded.read(CHUNK):stream.write(data);h.update(data);size+=len(data)
            stream.flush();os.fsync(stream.fileno())
        if h.hexdigest()!=sha or size!=row['original']['bytes']:raise ValueError('Restored bytes failed original SHA')
        os.chmod(partial,row['identity']['mode']);os.utime(partial,ns=(row['identity']['mtime_ns'],row['identity']['mtime_ns']))
        os.link(partial,target);partial.unlink()  # Exclusive final creation: never replace a raced-in file.
        print(json.dumps({'restored':str(target),'original_sha256':sha,'bytes':size}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='operation',required=True)
    commands.add_parser('fingerprint')
    for name in ('archive','restore'):
        p=commands.add_parser(name);p.add_argument('--plan',required=True,type=Path);p.add_argument('--sha256',required=True)
        if name=='restore':p.add_argument('--destination');p.add_argument('--original-paths',action='store_true');p.add_argument('--path')
    args=parser.parse_args()
    if args.operation=='fingerprint':print(json.dumps(fingerprint()));return
    ref=digest_path(args.plan)
    if ref['sha256']!=args.sha256:raise ValueError('Archive plan seal changed')
    if args.operation=='archive':print(json.dumps(archive(ref)))
    else:restore(ref,destination=args.destination,original_paths=args.original_paths,selected=args.path)


if __name__=='__main__':main()
