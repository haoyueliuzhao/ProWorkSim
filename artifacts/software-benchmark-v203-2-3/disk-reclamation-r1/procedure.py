from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import gzip, hashlib, json, os, shutil, stat, tarfile, time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'artifacts/software-benchmark-v203-2-3/disk-reclamation-r1'
CASES = [('v203-2-1', 'r1'), ('v203-2-1', 'r2')] + [('v203-2-3', 'r'+str(i)) for i in range(1,5)] + [('v143','r1'), ('v146','r1'), ('v157','r1'), ('v159','r1'), ('v161','r1'), ('v161','r2'), ('v168','r1'), ('v170','r1'), ('v181','r1'), ('v181','r2'), ('v181','r3'), ('v192','r1')]
TARGETS = [ROOT/'runs'/('software-benchmark-'+v)/('sdk-bundle-'+r) for v,r in CASES]
UID = os.getuid()
if UID == 0 or os.geteuid() != UID: raise RuntimeError('Ordinary owner only')
os.nice(10)
OUT.mkdir(parents=True, exist_ok=False)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()

def save(path, value):
    with path.open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def owned(path, kind=None):
    s=path.lstat()
    if s.st_uid != UID or stat.S_ISLNK(s.st_mode):raise RuntimeError('Not an ordinary owned path: '+str(path))
    if kind=='dir' and not stat.S_ISDIR(s.st_mode):raise RuntimeError('Not directory')
    if kind=='file' and not stat.S_ISREG(s.st_mode):raise RuntimeError('Not regular file')
    return s

def active_references(stage):
    prefixes=(str(stage),str(stage.relative_to(ROOT)))
    refs=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=UID:continue
            for key in ('cwd','exe','root'):
                try:
                    value=os.readlink(proc/key)
                    if value==prefixes[0] or value.startswith(prefixes[0]+'/'):refs.append({'pid':proc.name,'kind':key,'path':value})
                except (OSError,PermissionError):pass
            for key in ('cmdline','maps'):
                try:
                    text=(proc/key).read_bytes().replace(b'\0',b' ').decode(errors='replace')
                    if any(p in text for p in prefixes):refs.append({'pid':proc.name,'kind':key})
                except (OSError,PermissionError):pass
            try:
                for fd in (proc/'fd').iterdir():
                    try:
                        value=os.readlink(fd)
                        if value==prefixes[0] or value.startswith(prefixes[0]+'/'):refs.append({'pid':proc.name,'kind':'fd','path':value})
                    except OSError:pass
            except OSError:pass
        except (OSError,PermissionError):continue
    return refs

def verify(bundle):
    started=time.time();stage=bundle/'stage';owned(bundle,'dir');owned(stage,'dir')
    if stage==ROOT/'runs/software-benchmark-v203-2-3/sdk-bundle-r5/stage':raise RuntimeError('Protected final stage')
    refs=active_references(stage)
    if refs:raise RuntimeError('Active references: '+json.dumps(refs))
    mp=bundle/'manifest.json';owned(mp,'file');raw=mp.read_bytes();manifest=json.loads(raw)
    archive=Path(manifest['archive']['path'])
    if archive.parent!=bundle or archive.name!='runtime.tar.gz':raise RuntimeError('Archive outside exact bundle')
    owned(archive,'file')
    if archive.stat().st_size!=manifest['archive']['bytes'] or sha(archive)!=manifest['archive']['sha256']:raise RuntimeError('Archive reference/hash mismatch')
    inv=Path(manifest['member_inventory']['path']);owned(inv,'file')
    if inv.parent!=bundle or inv.stat().st_size!=manifest['member_inventory']['bytes'] or sha(inv)!=manifest['member_inventory']['sha256']:raise RuntimeError('Inventory reference/hash mismatch')
    inventory=json.loads(inv.read_bytes());listed={r['path']:r['bytes'] for r in inventory}
    if len(listed)!=len(inventory):raise RuntimeError('Duplicate inventory')
    observed={};metadata=[]
    for current, dirs, files in os.walk(stage,followlinks=False):
        for name in dirs+files:
            path=Path(current)/name;s=owned(path)
            if not (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)):raise RuntimeError('Unsupported stage object')
            relative=path.relative_to(stage).as_posix();observed[relative]=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,stat.S_ISDIR(s.st_mode))
            metadata.append({'path':relative,'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'mtime_ns':s.st_mtime_ns,'kind':'directory' if stat.S_ISDIR(s.st_mode) else 'file'})
    members=set();regular={};size=0
    with tarfile.open(archive,'r|gz') as tar:
        for item in tar:
            name=item.name.rstrip('/');p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or name in members:raise RuntimeError('Unsafe/duplicate archive member')
            members.add(name)
            if name not in observed:raise RuntimeError('Archive member absent in stage: '+name)
            path=stage/name;s=owned(path)
            if item.isdir():
                if not stat.S_ISDIR(s.st_mode):raise RuntimeError('Directory mismatch')
            elif item.isfile():
                if not stat.S_ISREG(s.st_mode) or s.st_size!=item.size:raise RuntimeError('Regular file mismatch')
                h1=hashlib.sha256();h2=hashlib.sha256();src=tar.extractfile(item)
                with path.open('rb') as dst:
                    while chunk:=src.read(1024*1024):h1.update(chunk)
                    while chunk:=dst.read(1024*1024):h2.update(chunk)
                if h1.digest()!=h2.digest():raise RuntimeError('Unarchived stage content: '+name)
                regular[name]=item.size;size+=item.size
            else:raise RuntimeError('Unsupported archive member type')
    if members!=set(observed) or regular!=listed:raise RuntimeError('Stage/archive/inventory tree mismatch')
    receipt={'bundle':str(bundle.relative_to(ROOT)), 'stage':str(stage.relative_to(ROOT)), 'uid':UID,
      'archive':manifest['archive'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'member_inventory':manifest['member_inventory'],
      'archive_sha256_verified':True,'full_archive_read':True,'all_stage_regular_file_bytes_equal_archive':True,
      'exact_stage_archive_inventory_file_set':True,'owner_only':True,'files':len(regular),'directories':len(members)-len(regular),
      'logical_file_bytes':size,'verification_wall_seconds':time.time()-started,
      'protected_final_stage_untouched':True,'tar_manifest_sources_results_dependencies_retained':True,
      'restoration':'Create a new empty stage; tar --no-same-owner -xzf runtime.tar.gz -C stage. Saved stage metadata records original ordinary-owner modes and timestamps.'}
    return stage,observed,metadata,receipt

before=shutil.disk_usage(ROOT).free
save(OUT/'intent.json',{'version':'v203.2.3-owned-archived-sdk-stage-reclamation-r1','uid':UID,'targets':[str(p.relative_to(ROOT)) for p in TARGETS],'protected_stage':str(ROOT/'runs/software-benchmark-v203-2-3/sdk-bundle-r5/stage'),'disk_available_before':before,'delete_only':'stage after archive and every staged file verification','workers':2,'nice':os.getpriority(os.PRIO_PROCESS,0)})
results=[]
with ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(verify,p) for p in TARGETS]
    for n,(bundle,future) in enumerate(zip(TARGETS,futures),1):
        label=bundle.parent.name+'-'+bundle.name
        try:
            stage,observed,metadata,receipt=future.result()
            refs=active_references(stage)
            if refs:raise RuntimeError('Active reference before deletion: '+json.dumps(refs))
            freed=owned(stage,'dir').st_blocks*512
            for relative,prior in observed.items():
                s=owned(stage/relative)
                if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,stat.S_ISDIR(s.st_mode))!=prior:raise RuntimeError('Stage changed after validation: '+relative)
                if stat.S_ISDIR(s.st_mode) or s.st_nlink==1:freed+=s.st_blocks*512
            metadata_path=OUT/(label+'-stage-metadata.json.gz')
            with gzip.open(metadata_path,'xt') as f:json.dump(metadata,f,separators=(',',':'))
            receipt.update(metadata={'path':str(metadata_path.relative_to(ROOT)),'sha256':sha(metadata_path)},expected_reclaimed_allocated_bytes=freed,active_owner_process_references=[])
            save(OUT/(label+'-verified.json'),receipt)
            shutil.rmtree(stage)
            receipt.update(status='removed_verified_reconstructible_stage',stage_absent=not stage.exists(),completed_unix=time.time())
            save(OUT/(label+'-result.json'),receipt)
        except Exception as error:
            receipt={'bundle':str(bundle.relative_to(ROOT)),'status':'skipped','error_type':type(error).__name__,'error':str(error)}
            save(OUT/(label+'-skipped.json'),receipt)
        results.append(receipt)
        print(json.dumps({'index':n,'bundle':str(bundle.relative_to(ROOT)),'status':receipt['status'],'bytes':receipt.get('expected_reclaimed_allocated_bytes',0),'error':receipt.get('error')},ensure_ascii=False),flush=True)
after=shutil.disk_usage(ROOT).free
summary={'version':'v203.2.3-owned-archived-sdk-stage-reclamation-r1','results':results,'verified_stage_allocated_bytes_reclaimed':sum(r.get('expected_reclaimed_allocated_bytes',0) for r in results if r['status']=='removed_verified_reconstructible_stage'),'disk_available_before':before,'disk_available_after':after,'observed_free_space_change':after-before,'concurrent_other_io_may_affect_free_space_delta':True,'preserved_final_bundle':str(ROOT/'runs/software-benchmark-v203-2-3/sdk-bundle-r5'),'root_operations':0}
save(OUT/'summary.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)
