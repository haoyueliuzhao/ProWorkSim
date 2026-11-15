import os, json, gzip, stat, hashlib, time, collections
from pathlib import Path

BASE = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = BASE/'runs/account-retirement-20261115'
ART = BASE/'artifacts/historical-data-retirement-20261115'
plan = json.loads((ART/'plan-summary.json').read_text())
assert os.getuid() == 1021
assert hashlib.sha256((OUT/'files.jsonl.gz').read_bytes()).hexdigest() == plan['manifest_sha256']
roots = json.loads((ART/'candidate-roots.json').read_text())
summary = {'started_unix':time.time(), 'uid':os.getuid(), 'removed_files':0, 'removed_allocated_bytes':0, 'by_disk_bytes':{}, 'errors':[], 'skipped_changed':0, 'root_operations':'read-only preflight; no root deletion'}
disk = collections.Counter()
def open_parent(path):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in Path(path).parent.parts[1:]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = nxt
        return fd
    except BaseException:
        os.close(fd); raise

with gzip.open(OUT/'files.jsonl.gz','rt') as source, gzip.open(OUT/'deletion-events.jsonl.gz','wt') as events:
    for line in source:
        item = json.loads(line); path = item['path']; fd = None
        assert any(path.startswith(r+'/') for r in roots)
        try:
            fd = open_parent(path); name = Path(path).name
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
            assert stat.S_ISREG(s.st_mode) and s.st_uid == 1021 and s.st_nlink == 1
            if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns) != (item['device'],item['inode'],item['size'],item['mtime_ns']):
                summary['skipped_changed'] += 1; continue
            os.unlink(name,dir_fd=fd)
            try: os.stat(name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError: pass
            else: raise RuntimeError('Path reappeared after deletion')
            summary['removed_files'] += 1; summary['removed_allocated_bytes'] += s.st_blocks*512
            disk[Path(path).parts[1]] += s.st_blocks*512
            events.write(json.dumps({'path':path,'allocated_bytes':s.st_blocks*512,'status':'removed_and_absent'})+'\n')
            if summary['removed_files'] % 5000 == 0:
                events.flush(); print(json.dumps({'removed_files':summary['removed_files'],'removed_allocated_bytes':summary['removed_allocated_bytes']}),flush=True)
        except (OSError,AssertionError,RuntimeError) as e:
            summary['errors'].append({'path':path,'error':repr(e)})
        finally:
            if fd is not None: os.close(fd)
summary['by_disk_bytes'] = dict(disk)
summary['finished_unix'] = time.time()
(ART/'deletion-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
