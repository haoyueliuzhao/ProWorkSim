"""Remove explicitly inventoried, inactive, user-owned model/training payloads.

No directory recursion, root operation, process signal, dependency replacement,
download, or change to historical model manifests is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUTPUT = ROOT/'runs/storage-retirement-v153'
EXTERNAL_MODEL = Path('/data0/zhuxinrui/models/Qwen2.5-7B-Instruct-a09a35458c702b33eeacc393d103063234e8bc28')
ALLOWED_ROOTS = (ROOT/'runs', EXTERNAL_MODEL)
PROTECTED = (ROOT/'.venv', ROOT/'.train-venv', ROOT/'runs/v016-sdk', ROOT/'runs/v015-runtime',
             ROOT/'runs/software-benchmark-v149', ROOT/'runs/software-benchmark-v150',
             ROOT/'runs/software-benchmark-v151', ROOT/'runs/software-benchmark-v154')


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def identity(path):
    path = Path(path)
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid() or value.st_nlink != 1
            or path.resolve() != path):
        raise ValueError('Only an ordinary, direct, current-user, single-link file may be removed')
    return {'dev':value.st_dev,'inode':value.st_ino,'uid':value.st_uid,'nlink':value.st_nlink,
            'size':value.st_size,'mtime_ns':value.st_mtime_ns,'allocated_bytes':value.st_blocks*512}


def permitted(path, protected_files):
    path = Path(path)
    if not any(path.is_relative_to(root) for root in ALLOWED_ROOTS):
        return False
    if any(path.is_relative_to(root) for root in PROTECTED) or str(path) in protected_files:
        return False
    if path.is_relative_to(ROOT/'runs'):
        run = path.relative_to(ROOT/'runs').parts[0]
        if run.startswith('software-benchmark-'):
            return False  # Current and historical evaluation data are not training garbage.
    return True


def static_protection():
    files = set()
    for version in (146, 149, 150, 151, 154):
        root = ROOT/'runs'/f'software-benchmark-v{version}'
        if not root.exists():
            continue
        for path in root.glob('*/*sources*.json'):
            value = read(path)
            files.update(row['path'] for row in value.get('files', []) if isinstance(row,dict) and 'path' in row)
    return files


def occupancy(rows):
    """Match only exact targets/inodes; never print unrelated process arguments."""
    inode_set = {(r['identity']['dev'],r['identity']['inode']) for r in rows}
    paths = {r['path'] for r in rows}
    directories = {str(Path(r['path']).parent) for r in rows
                   if r['category'] in {'downloaded_model_weights','model_private_incomplete_download_cache'}}
    matches, unavailable, observed = [], 0, 0
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():
            continue
        try:
            uid = p.stat().st_uid
            args = (p/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (OSError, ProcessLookupError):
            unavailable += 1
            continue
        if any(arg in paths or arg in directories for arg in args):
            matches.append({'pid':int(p.name),'uid':uid,'kind':'exact_target_argument'})
        if uid != os.getuid():
            continue
        observed += 1
        try:
            for line in (p/'maps').read_text().splitlines():
                parts = line.split(maxsplit=5)
                if len(parts) == 6 and parts[5].removesuffix(' (deleted)') in paths:
                    matches.append({'pid':int(p.name),'uid':uid,'kind':'mapped_target'})
            for fd in (p/'fd').iterdir():
                try:
                    s = fd.stat()
                except OSError:
                    continue
                if (s.st_dev,s.st_ino) in inode_set:
                    matches.append({'pid':int(p.name),'uid':uid,'kind':'opened_target_inode'})
        except OSError:
            unavailable += 1
    return {'matches':matches,'current_user_processes_observed':observed,
            'unavailable_or_raced_process_fields':unavailable,'other_users_maps_or_fds_read':False}


def prepare(inventory, batch):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Ordinary user only')
    data = read(inventory)
    source_rows = data['delete_candidates']
    protected_files = static_protection()
    tracked = subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.split(b'\0')
    tracked = {str(ROOT/os.fsdecode(p)) for p in tracked if p}
    rows, skipped, seen = [], [], set()
    for row in source_rows:
        path = Path(row['path'])
        if not permitted(path, protected_files) or str(path) in tracked:
            skipped.append({'path':str(path),'reason':'protected_or_tracked'})
            continue
        current = identity(path)
        if any(row.get(k) != current[k] for k in ('dev','inode','uid','nlink','size','mtime_ns')):
            raise ValueError('The inventoried file changed: '+str(path))
        key = (current['dev'],current['inode'])
        if key in seen:
            continue
        seen.add(key)
        rows.append({'path':str(path),'category':row['category'],'identity':current})
    metadata = []
    for row in data.get('restore_metadata', []):
        path = row.get('path') or row.get('tree_with_LFS_hashes')
        if path:
            raw = Path(path).read_bytes()
            metadata.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    output = OUTPUT/batch
    value = {'version':'v153-user-authorized-training-and-model-retirement-r1',
        'prepared_unix':time.time(),'source_inventory':str(inventory),'files':rows,
        'allocated_bytes':sum(r['identity']['allocated_bytes'] for r in rows),
        'category_counts':dict(Counter(r['category'] for r in rows)), 'skipped':skipped,
        'protected_prefixes':[str(p) for p in PROTECTED], 'protected_metadata':metadata,
        'training_disabled_by_user':True,'no_automatic_local_model_redownload':True,
        'scope':'explicit payload files; retain tokenizers, environments, evaluation results and reports'}
    write(output/'plan.json',value)
    return {k:v for k,v in value.items() if k not in {'files','protected_metadata'}}


def execute(batch):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Ordinary user only')
    output = OUTPUT/batch
    plan = read(output/'plan.json')
    if (output/'execution-started.json').exists():
        raise PermissionError('This exact deletion pass has already entered; inspect its receipt')
    protected_files = static_protection()
    for row in plan['files']:
        if not permitted(row['path'],protected_files) or identity(row['path']) != row['identity']:
            raise ValueError('A planned target changed or became protected')
    occupied = occupancy(plan['files'])
    write(output/'occupancy-before.json',occupied)
    if occupied['matches']:
        raise PermissionError('One or more exact targets are still used; no deletion performed')
    write(output/'execution-started.json',{'unix':time.time(),'uid':os.getuid(),
          'plan_sha256':hashlib.sha256((output/'plan.json').read_bytes()).hexdigest()})
    deleted, errors = [], []
    with (output/'deletion-events.jsonl').open('x') as events:
        for row in plan['files']:
            try:
                path = Path(row['path'])
                if identity(path) != row['identity']:
                    raise ValueError('Target changed immediately before unlink')
                path.unlink()
                deleted.append(row)
                record = {'path':str(path),'deleted':True,'allocated_bytes':row['identity']['allocated_bytes']}
            except Exception as error:
                record = {'path':row['path'],'deleted':False,'error':type(error).__name__+': '+str(error)}
                errors.append(record)
            events.write(json.dumps(record,ensure_ascii=False)+'\n')
            events.flush()
    metadata_unchanged = all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256']
                             for r in plan['protected_metadata'])
    receipt = {'version':plan['version'],'finished_unix':time.time(),'uid':os.getuid(),
        'deleted_files':len(deleted),'allocated_bytes_deleted':sum(r['identity']['allocated_bytes'] for r in deleted),
        'allocated_bytes_are_not_global_filesystem_free_delta':True,
        'deleted_by_category':dict(Counter(r['category'] for r in deleted)),
        'all_deleted_paths_absent':all(not Path(r['path']).exists() for r in deleted),
        'metadata_unchanged':metadata_unchanged,'errors':errors,
        'services_stopped':0,'root_operations':0,'model_calls':0,'host_configuration_changes':0}
    write(output/'receipt.json',receipt)
    for folder in sorted({str(Path(r['path']).parent) for r in deleted if r['category']=='downloaded_model_weights'}):
        write(Path(folder)/'MODEL_WEIGHTS_REMOVED.json',{
            'status':'weights_removed_not_loadable','reason':'User retired training and temporarily removed local models',
            'receipt':str(output/'receipt.json'),'original_manifest_is_historical':True,
            'config_tokenizer_and_source_revision_retained':True,'automatic_redownload':False})
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',required=True,choices=('model-and-checkpoint-r1','training-raw-r1'))
    parser.add_argument('--inventory',type=Path)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args()
    value = execute(args.batch) if args.execute else prepare(args.inventory,args.batch)
    print(json.dumps(value,ensure_ascii=False,indent=2))
