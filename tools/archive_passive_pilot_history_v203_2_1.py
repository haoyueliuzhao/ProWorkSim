"""Lossless archival of closed historical request/capture JSON; ordinary user only.

--prepare only reads metadata and writes the new local plan. --run streams each
selected episode to its own tar.zst on the existing /data1 owner directory,
verifies all decompressed file hashes, then releases only those original JSONs.
Old references require --restore before use; this is not transparent relocation.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/software-benchmark-v203-2-1/history-archive-preparation-r1'
PLAN=ART/'plan.json'
OUT=Path('/data1/proworksim-zhuxinrui/passive-history-v203-2-1')
BATCHES=(ROOT/'runs/software-benchmark-v066/v064-continuation-r3',
         ROOT/'runs/software-benchmark-v181/full-context-pilot-r1',
         ROOT/'runs/software-benchmark-v169/communication-wave2-r2')
VERSION='v203.2.1-owner-closed-request-json-lossless-archive-r1'
GIB=1024**3
BLOCK=1024**2
RAW=re.compile(r'(?:request|response|tokenize|tokenize-prefix)-[0-9]+\.json\Z')
SHA=re.compile(r'[0-9a-f]{64}\Z')
CAPTURE_FILES=frozenset({'payload.json','provenance.json','response.json','response-original.json',
    'projection-evidence.json','source-mapping-evidence.json','published-version-bindings.json'})
IDENTITY_KEYS=('size','allocated','dev','ino','mode','uid','gid','nlink','mtime_ns','ctime_ns')


def digest_file(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def ref(path):
    p=Path(path)
    if p.resolve()!=p:raise ValueError('Canonical paths must not change through symlinks')
    return {'path':str(p),'sha256':digest_file(p),'bytes':p.stat().st_size}


def checked(value):
    p=Path(value['path'])
    if ref(p)!=value:raise ValueError('Retained file changed: '+str(p))
    return p


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    sync_dir(p.parent);return ref(p)


def progress(value):
    p=ART/'progress.json';tmp=p.with_suffix('.tmp')
    with tmp.open('wb') as stream:stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,p);sync_dir(p.parent)


def identity(path):
    p=Path(path);s=p.lstat()
    if (p.resolve()!=p or not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1):
        raise ValueError('Only canonical singly linked owner regular files are admitted: '+str(p))
    if os.listxattr(p,follow_symlinks=False):raise ValueError('Extended metadata needs another protocol')
    return dict(size=s.st_size,allocated=s.st_blocks*512,dev=s.st_dev,ino=s.st_ino,
        mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid,nlink=s.st_nlink,
        mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)


def selected(relative):
    """Exact raw request and source-capture layouts; ledgers/summaries never match."""
    parts=Path(relative).parts
    if not parts or '..' in parts or Path(relative).is_absolute():return False
    if len(parts)==1:return bool(RAW.fullmatch(parts[0]))
    if len(parts)==2 and re.fullmatch(r'member_[0-9]{3}',parts[0]):return bool(RAW.fullmatch(parts[1]))
    if len(parts)==3 and parts[0] in {'request-capture-v157','request-capture-v181'}:
        return bool(SHA.fullmatch(parts[1])) and parts[2] in CAPTURE_FILES
    if len(parts)==4 and parts[:2]==('collaboration-observation','source-presentation-inputs'):
        return bool(SHA.fullmatch(parts[2])) and parts[3] in {'payload.json','provenance.json'}
    if len(parts)==3 and parts[:2]==('collaboration-observation','source-presentations'):
        return parts[2].endswith('.json') and bool(SHA.fullmatch(parts[2][:-5]))
    return False


def source_path(root,relative):
    p=Path(root)/relative
    if not selected(relative) or p.resolve()!=p or not p.is_relative_to(root):raise ValueError('Foreign archive member')
    return p


def unchanged(root,rows):
    for row in rows:
        p=source_path(root,row['relative']);s=identity(p)
        if any(s[k]!=row[k] for k in IDENTITY_KEYS):raise ValueError('Historical source changed: '+str(p))


def own_process_references(roots):
    roots=[str(Path(r)) for r in roots];matches=[];unreadable=[]
    def relevant(target):return any(target==r or target.startswith(r+'/') for r in roots)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=os.getuid():continue
        except FileNotFoundError:continue
        for leaf in ('cwd','exe','root'):
            try:
                target=os.readlink(proc/leaf)
                if relevant(target):matches.append({'pid':int(proc.name),'kind':leaf,'path':target})
            except FileNotFoundError:pass
            except PermissionError:unreadable.append((proc.name,leaf))
        try:fds=list((proc/'fd').iterdir())
        except FileNotFoundError:continue
        except PermissionError:unreadable.append((proc.name,'fd'));continue
        for fd in fds:
            try:
                target=os.readlink(fd)
                if relevant(target):matches.append({'pid':int(proc.name),'kind':'fd','path':target})
            except FileNotFoundError:pass
            except PermissionError:unreadable.append((proc.name,'fd-link'))
        try:
            for line in (proc/'maps').read_text().splitlines():
                fields=line.split(None,5)
                if len(fields)==6 and relevant(fields[5]):matches.append({'pid':int(proc.name),'kind':'mmap','path':fields[5]})
        except (FileNotFoundError,ProcessLookupError):pass
        except PermissionError:unreadable.append((proc.name,'maps'))
    if unreadable:raise PermissionError('Cannot prove own process view complete: '+repr(unreadable[:5]))
    if matches:raise PermissionError('Historical request data has a live own-process reference: '+repr(matches[:5]))
    return {'other_users_not_inspected':True,'matched_live_references':0,'ordinary_uid':os.getuid()}


def no_mount_below(root):
    for file in (Path('/proc/self/mountinfo'),Path('/proc/1/mountinfo')):
        for line in file.read_text().splitlines():
            field=line.split()[4]
            field=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),field)
            p=Path(field)
            if p==root or p.is_relative_to(root):raise PermissionError('Mounted source subtree is excluded')


def quiet(item,*,check_protected=True):
    if os.getuid()==0 or os.geteuid()==0:raise PermissionError('Never run this archive as root')
    root=Path(item['root']);batch=Path(item['batch']);episode=Path(item['episode'])
    if (batch not in BATCHES or root!=episode/'controller-output/model-ledger'
        or episode.parent!=batch/'episodes' or root.resolve()!=root or not root.is_dir()
        or not episode.name.isdigit()):raise PermissionError('Source is outside the three exact historical batches')
    for p in (batch,episode,root):
        if p.is_symlink() or p.stat().st_uid!=os.getuid():raise PermissionError('Foreign or symlink source directory')
    if list((batch/'resource-claims').glob('active-*.json')):raise PermissionError('Historical batch still has active resource claims')
    result=json.loads(checked(item['result']).read_bytes());q=json.loads(checked(item['quiescence']).read_bytes())
    if (result.get('status') not in {'closed','technical_unknown'} or q.get('quiescent') is not True
        or q.get('all_owned_objects_removed') is not True or q.get('cleanup_errors')!=[]
        or q.get('create_result_unknown') is not False or q.get('retained_objects',[])!=[]):
        raise PermissionError('Historical episode lacks complete ended/owned-cleanup evidence')
    if result.get('quiescence') not in (None,item['quiescence']):raise ValueError('Cleanup reference changed')
    no_mount_below(root);own_process_references([root])
    if check_protected:
        for witness in item['protected']:checked(witness)
    return root


def output_ready(*,create=False):
    parent=OUT.parent
    if (parent.resolve()!=parent or not parent.is_dir() or parent.stat().st_uid!=os.getuid()
        or stat.S_IMODE(parent.stat().st_mode)&0o077):raise PermissionError('Use the existing private owner directory on real/data1')
    if create:OUT.mkdir(mode=0o700,exist_ok=True)
    p=OUT if OUT.exists() else parent
    if p.resolve()!=p or p.stat().st_uid!=os.getuid():raise PermissionError('Archive directory ownership changed')
    if p.stat().st_dev==(ROOT/'runs').stat().st_dev:raise PermissionError('Archive destination must be the other real filesystem')
    return p


def prepare():
    if PLAN.exists():raise ValueError('Do not overwrite this preparation plan')
    output_ready();items=[];excluded=[];stats={}
    for order,batch in enumerate(BATCHES):
        if not (batch/'episodes').is_dir():continue
        for episode in sorted((batch/'episodes').iterdir(),key=lambda p:int(p.name) if p.name.isdigit() else 10**12):
            root=episode/'controller-output/model-ledger'
            if not root.is_dir() or not episode.name.isdigit():continue
            try:
                item={'root':str(root),'batch':str(batch),'episode':str(episode),'batch_order':order,
                    'item_id':batch.parent.name+'-'+episode.name,'result':ref(episode/'result.json'),
                    'quiescence':ref(episode/'quiescence.json'),'protected':[]}
                quiet(item,check_protected=False);rows=[];protected=[]
                for folder,dirs,files in os.walk(root,followlinks=False):
                    if any((Path(folder)/d).is_symlink() for d in dirs):raise ValueError('Symlink directory in historical ledger')
                    for name in sorted(files):
                        p=Path(folder)/name;relative=str(p.relative_to(root))
                        if selected(relative):rows.append({'relative':relative,'original_canonical_path':str(p),**identity(p)})
                        elif name in {'ledger.json','summary.json'}:protected.append(ref(p))
                if not rows:continue
                item.update(files=rows,protected=protected,allocated_bytes=sum(r['allocated'] for r in rows),
                    bytes=sum(r['size'] for r in rows),file_count=len(rows))
                items.append(item);stats.setdefault(batch.parent.name,{'episodes':0,'files':0,'allocated_bytes':0})
                st=stats[batch.parent.name];st['episodes']+=1;st['files']+=len(rows);st['allocated_bytes']+=item['allocated_bytes']
            except (OSError,ValueError,PermissionError) as error:
                excluded.append({'episode':str(episode),'type':type(error).__name__,'error':str(error)})
    # Maximize freed space per complete episode, preserving the v066-first order.
    items.sort(key=lambda x:(x['batch_order'],-x['allocated_bytes'],x['item_id']))
    plan={'version':VERSION,'source':ref(Path(__file__).resolve()),'uid':os.getuid(),'items':items,'excluded':excluded,
        'output_root':str(OUT),'output_device':output_ready().stat().st_dev,'source_device':(ROOT/'runs').stat().st_dev,
        'maximum_workers':2,'maximum_CPU_affinity_count':2,'minimum_stop_target_free_bytes':180*GIB,
        'default_stop_target_free_bytes':180*GIB,'archive_filesystem_floor_bytes':20*GIB,
        'maximum_source_allocated_bytes':sum(x['allocated_bytes'] for x in items),'by_batch':stats,
        'API_request_response_tokenization_and_source_capture_JSON_only':True,
        'ledgers_summaries_events_public_tests_patches_scores_unchanged':True,
        'original_reference_readers_require_explicit_restore':True,'no_symlink_relocation':True,
        'authority':'User standing authorization for lossless historical cleanup/compression and current pilot environment preparation; no root or shared service changes.',
        'prepared_only':True,'original_payload_hashes_computed_during_encoding_not_preparation':True,
        'model_calls':0,'Docker_operations':0,'historical_files_mutated':0}
    result=save(PLAN,plan)
    summary={k:v for k,v in plan.items() if k not in {'items','excluded'}}
    summary.update(plan=result,episodes=len(items),files=sum(x['file_count'] for x in items),excluded_count=len(excluded),
        potential_source_GiB=plan['maximum_source_allocated_bytes']/GIB)
    save(ART/'summary.json',summary);return summary


class HashReader:
    def __init__(self,stream):self.stream=stream;self.hash=hashlib.sha256();self.count=0
    def read(self,n=-1):
        raw=self.stream.read(n);self.hash.update(raw);self.count+=len(raw);return raw


def open_original(root,row):
    p=source_path(root,row['relative']);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    s=os.fstat(fd)
    if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(row['dev'],row['ino'],row['size'],row['mtime_ns'],row['ctime_ns']):
        os.close(fd);raise ValueError('Opened source differs from prepared inode')
    return os.fdopen(fd,'rb')


def stop_codec(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def encode(root,rows,directory):
    directory.mkdir(mode=0o700,parents=False,exist_ok=False);archive=directory/'requests.tar.zst';members=[]
    reserve=sum(r['size']+1024 for r in rows)+BLOCK
    if shutil.disk_usage(OUT).free < 20*GIB+reserve:raise RuntimeError('Archive disk lacks worst-case episode output reserve')
    with archive.open('xb') as output,(directory/'compression.stderr').open('xb') as error:
        p=subprocess.Popen(['/usr/bin/zstd','-q','-3','--long=27','-T1','-c'],stdin=subprocess.PIPE,stdout=output,stderr=error)
        try:
            with tarfile.open(fileobj=p.stdin,mode='w|',format=tarfile.PAX_FORMAT) as tar:
                for row in rows:
                    if shutil.disk_usage(OUT).free<20*GIB:raise RuntimeError('Archive filesystem floor reached; originals retained')
                    unchanged(root,[row]);info=tarfile.TarInfo(row['relative']);info.size=row['size']
                    info.mode,info.uid,info.gid=row['mode'],row['uid'],row['gid'];ns=row['mtime_ns'];info.mtime=ns//10**9
                    info.pax_headers['mtime']=f'{ns//10**9}.{ns%10**9:09d}'
                    with open_original(root,row) as stream:
                        reader=HashReader(stream);tar.addfile(info,reader)
                        if reader.count!=row['size']:raise ValueError('Short original file read')
                    unchanged(root,[row]);members.append({**row,'sha256':reader.hash.hexdigest()})
            p.stdin.close()
            if p.wait(timeout=120):raise RuntimeError('zstd encoding failed; originals retained')
            output.flush();os.fsync(output.fileno())
        except BaseException:
            try:p.stdin.close()
            except OSError:pass
            stop_codec(p);raise
    sync_dir(directory);return archive,members


def verify(archive,members):
    expected={r['relative']:r for r in members};seen=set()
    if len(expected)!=len(members):raise ValueError('Duplicate archive identity')
    with (archive.parent/'verification.stderr').open('ab') as error:
        p=subprocess.Popen(['/usr/bin/zstd','-q','--long=27','-dc',str(archive)],stdout=subprocess.PIPE,stderr=error)
        try:
            with tarfile.open(fileobj=p.stdout,mode='r|') as tar:
                for m in tar:
                    if not m.isfile() or m.name not in expected or m.name in seen:raise ValueError('Foreign or duplicate archive member')
                    row=expected[m.name];ns=row['mtime_ns']
                    if ((m.size,m.mode,m.uid,m.gid)!=(row['size'],row['mode'],row['uid'],row['gid'])
                        or m.pax_headers.get('mtime')!=f'{ns//10**9}.{ns%10**9:09d}'):
                        raise ValueError('Archive metadata mismatch')
                    with tar.extractfile(m) as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
                    if sha!=row['sha256']:raise ValueError('Decompressed original SHA mismatch')
                    seen.add(m.name)
            while p.stdout.read(BLOCK):pass
            if p.wait(timeout=60) or seen!=set(expected):raise ValueError('Incomplete zstd frame or file set')
        finally:
            p.stdout.close();stop_codec(p)
    return {'all_original_sha256_verified':True,'full_decompression':True,'files':len(seen)}


@contextmanager
def batch_read_lock(batch):
    # Shared lock prevents the existing allocator's exclusive new claims while
    # permitting up to two independent closed-episode archival readers.
    p=Path(batch)/'resource-claims/allocation.lock'
    if not p.is_file() or p.is_symlink() or p.stat().st_uid!=os.getuid():raise PermissionError('Missing owned resource allocation lock')
    with p.open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB);yield


def archive_one(item,plan_ref):
    directory=OUT/item['item_id']
    with batch_read_lock(item['batch']):
        root=quiet(item);unchanged(root,item['files'])
        archive,members=encode(root,item['files'],directory);proof=verify(archive,members)
        quiet(item);unchanged(root,members)
        verified=save(directory/'verified.json',{'version':VERSION,'item':item,'plan':plan_ref,
            'archive':ref(archive),'members':members,'verification':proof,'verified_unix':time.time()})
        save(Path(item['episode'])/'model-ledger-archive-v203-2-1.json',{'version':VERSION,'verified':verified,
            'original_canonical_paths_in_manifest':True,'not_transparent_to_old_checked_reference_readers':True,
            'restore_command':['.venv/bin/python','tools/archive_passive_pilot_history_v203_2_1.py',
                              '--restore',str(directory/'verified.json'),'--member','<relative-member>']})
        # Every original is validated before the first unlink; each is checked
        # again immediately before release. No write touches a source inode.
        unchanged(root,members);released=0;parents=set()
        for row in members:
            unchanged(root,[row]);path=source_path(root,row['relative']);path.unlink();parents.add(path.parent);released+=row['allocated']
        for parent in parents:sync_dir(parent)
        for witness in item['protected']:checked(witness)
        result={'version':VERSION,'item_id':item['item_id'],'verified':verified,
            'source_allocated_bytes_released':released,'archive_allocated_bytes':archive.stat().st_blocks*512,
            'source_files_released':len(members),'original_information_loss':False,
            'ledger_summary_patch_score_bytes_unchanged':True,'finished_unix':time.time()}
        save(directory/'released.json',result);return result


@contextmanager
def operation_lock():
    ART.mkdir(parents=True,exist_ok=True)
    with (ART/'operation.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);yield


def run(target_free_gib,workers):
    if target_free_gib<180 or workers not in (1,2):raise ValueError('Target>=180GiB and workers<=2 are required')
    plan=json.loads(PLAN.read_bytes());checked(plan['source']);plan_ref=ref(PLAN)
    if plan['uid']!=os.getuid() or os.getuid()==0:raise PermissionError('Wrong ordinary archival owner')
    output_ready(create=True);target=target_free_gib*GIB;results=[];errors=[];pending=iter(plan['items']);exhausted=False
    with operation_lock():
        affinity=os.sched_getaffinity(0);os.sched_setaffinity(0,set(sorted(affinity)[:2]))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                active={}
                while active or not exhausted:
                    while not exhausted and len(active)<workers:
                        if errors or shutil.disk_usage(ROOT/'runs').free>=target:exhausted=True;break
                        try:item=next(pending)
                        except StopIteration:exhausted=True;break
                        if (OUT/item['item_id']).exists():
                            errors.append({'item_id':item['item_id'],'error':'Archive identity already exists; preserve it and inspect instead of automatic replay'});exhausted=True;break
                        active[pool.submit(archive_one,item,plan_ref)]=item
                    if not active:break
                    done,_=wait(active,return_when=FIRST_COMPLETED)
                    for future in done:
                        item=active.pop(future)
                        try:results.append(future.result())
                        except Exception as e:errors.append({'item_id':item['item_id'],'type':type(e).__name__,'error':str(e)});exhausted=True
                    progress({'version':VERSION,'status':'draining_after_error' if errors else 'running',
                        'completed':len(results),'active':len(active),'errors':errors,
                        'source_allocated_bytes_released':sum(r['source_allocated_bytes_released'] for r in results),
                        'data0_current_free_bytes':shutil.disk_usage(ROOT/'runs').free,'target_free_bytes':target,
                        'archive_output_free_bytes':shutil.disk_usage(OUT).free,
                        'no_new_admission_after_target':True,'already_started_archives_finish':True})
        finally:os.sched_setaffinity(0,affinity)
        free=shutil.disk_usage(ROOT/'runs').free
        final={'version':VERSION,'status':'stopped_on_error' if errors else 'target_reached' if free>=target else 'eligible_inputs_exhausted',
            'completed':len(results),'errors':errors,'source_allocated_bytes_released':sum(r['source_allocated_bytes_released'] for r in results),
            'data0_current_free_bytes':free,'target_free_bytes':target,'results':results,
            'filesystem_free_delta_not_attributed_to_this_project':True,'historical_information_preserved_in_verified_archives':True}
        progress(final);save(ART/('final-'+str(time.time_ns())+'.json'),final);return final


def restore(proof_file,member):
    proof_path=Path(proof_file).resolve()
    if proof_path.name!='verified.json' or proof_path.parent.parent!=OUT:raise PermissionError('Foreign archive proof')
    with operation_lock():
        proof=json.loads(proof_path.read_bytes());item=proof['item'];root=quiet(item)
        if proof.get('version')!=VERSION or proof.get('verification',{}).get('all_original_sha256_verified') is not True:raise ValueError('Unverified archive')
        matches=[r for r in proof['members'] if r['relative']==member]
        if len(matches)!=1:raise ValueError('Select one exact archived member')
        row=matches[0];target=source_path(root,member)
        if proof['archive'].get('path')!=str(proof_path.parent/'requests.tar.zst') or item['item_id']!=proof_path.parent.name:
            raise PermissionError('Archive proof belongs to another item')
        archive=checked(proof['archive'])
        if target.exists() or target.is_symlink():raise FileExistsError('Restore never overwrites any existing path')
        temp=target.with_name(target.name+'.v203-2-1-restoring');found=False
        with (proof_path.parent/'restore.stderr').open('ab') as error:
            p=subprocess.Popen(['/usr/bin/zstd','-q','--long=27','-dc',str(archive)],stdout=subprocess.PIPE,stderr=error)
            try:
                with tarfile.open(fileobj=p.stdout,mode='r|') as tar:
                    for m in tar:
                        if m.name!=member:continue
                        if found or not m.isfile() or m.size!=row['size']:raise ValueError('Invalid restore member')
                        if shutil.disk_usage(target.parent).free<row['size']+20*GIB:raise RuntimeError('Insufficient original-filesystem restore reserve')
                        with tar.extractfile(m) as source,temp.open('xb') as output:
                            h=hashlib.sha256();count=0
                            for block in iter(lambda:source.read(BLOCK),b''):output.write(block);h.update(block);count+=len(block)
                            if count!=row['size'] or h.hexdigest()!=row['sha256']:raise ValueError('Restore bytes differ')
                            output.flush()
                            os.fchmod(output.fileno(),row['mode'])
                            if os.fstat(output.fileno()).st_gid!=row['gid']:os.fchown(output.fileno(),-1,row['gid'])
                            os.utime(output.fileno(),ns=(row['mtime_ns'],row['mtime_ns']));os.fsync(output.fileno())
                        found=True
                while p.stdout.read(BLOCK):pass
                if p.wait(timeout=60) or not found:raise ValueError('Restore frame incomplete')
                # link is atomic and refuses an independently appearing target.
                os.link(temp,target,follow_symlinks=False);temp.unlink();sync_dir(target.parent)
            finally:
                p.stdout.close();stop_codec(p)
                if temp.exists():temp.unlink()
        actual=ref(target);expected={'path':row['original_canonical_path'],'sha256':row['sha256'],'bytes':row['size']}
        if actual!=expected:raise ValueError('Restored original canonical reference differs')
        return {'restored':actual,'original_mode':row['mode'],'original_mtime_ns':row['mtime_ns'],
                'inode_and_ctime_new':True,'old_checked_reference_compatible':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true');group.add_argument('--restore',type=Path)
    parser.add_argument('--member');parser.add_argument('--workers',type=int,default=2);parser.add_argument('--target-free-gib',type=int,default=180)
    args=parser.parse_args()
    if args.prepare:result=prepare()
    elif args.run:result=run(args.target_free_gib,args.workers)
    else:
        if not args.member:parser.error('--restore requires --member')
        result=restore(args.restore,args.member)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
