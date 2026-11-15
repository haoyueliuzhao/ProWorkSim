import os, json, stat, gzip, time
from pathlib import Path

BASE = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = BASE / 'runs/account-retirement-20261115'
roots = json.loads((BASE / 'artifacts/historical-data-retirement-20261115/candidate-roots.json').read_text())
keep_words = ('summary', 'report', 'result', 'metric', 'score', 'usage', 'ledger', 'budget', 'receipt', 'manifest', 'quiescence', 'finalization')
skip_dirs = {'rootfs', 'sysroot', '.git', 'node_modules', 'site-packages', '.venv', 'venv'}
stats = []
with gzip.open(OUT / 'files.jsonl.gz', 'wt') as plan:
    for root in roots:
        s = {'root': root, 'files': 0, 'allocated_bytes': 0, 'preserved_files': 0, 'skipped_trees': [], 'errors': []}
        device = os.stat(root).st_dev
        def error(e): s['errors'].append(str(e))
        for parent, dirs, files in os.walk(root, followlinks=False, onerror=error):
            selected = []
            for name in dirs:
                q = Path(parent) / name
                try:
                    if q.is_symlink() or q.stat().st_dev != device or name in skip_dirs or 'report' in name.lower() or 'summary' in name.lower():
                        s['skipped_trees'].append(str(q)); continue
                    selected.append(name)
                except OSError as e: error(e)
            dirs[:] = selected
            for name in files:
                q = Path(parent) / name
                try:
                    t = q.lstat(); low = name.lower()
                    if not stat.S_ISREG(t.st_mode) or t.st_uid != os.getuid() or t.st_nlink != 1 or t.st_mtime > time.time()-86400:
                        s['preserved_files'] += 1; continue
                    if low.endswith(('.md', '.csv', '.tsv', '.sqlite', '.sqlite3', '.db')) or any(w in low for w in keep_words) or (low.endswith('.json') and t.st_size < 1024*1024):
                        s['preserved_files'] += 1; continue
                    item = {'path':str(q),'device':t.st_dev,'inode':t.st_ino,'size':t.st_size,'mtime_ns':t.st_mtime_ns,'allocated':t.st_blocks*512}
                    plan.write(json.dumps(item)+'\n');s['files'] += 1;s['allocated_bytes'] += item['allocated']
                except OSError as e: error(e)
        stats.append(s)
        print(json.dumps({k:s[k] for k in ('root','files','allocated_bytes')}), flush=True)
(OUT/'inventory.json').write_text(json.dumps(stats,indent=2)+'\n')
print(json.dumps({'total_files':sum(s['files'] for s in stats),'total_allocated_bytes':sum(s['allocated_bytes'] for s in stats)}),flush=True)
