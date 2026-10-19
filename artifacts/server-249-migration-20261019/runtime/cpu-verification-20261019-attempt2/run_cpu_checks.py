import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

receipt = Path(__file__).parent
runtime = Path('/data0/zhuxinrui/proworksim-runtime')
project = '/data1/zhuxinrui/projects/ProWorkSim'
probe = (runtime / 'verify_cpu.py').read_text()
rows = []

def run_check(name, command, input_text=None):
    started = time.time()
    process = subprocess.run(['/usr/bin/timeout', '--kill-after=5s', '180s', str(runtime / 'run-cpu.sh'), *command], input=input_text, text=True, capture_output=True)
    stdout = receipt / (name + '.stdout')
    stderr = receipt / (name + '.stderr')
    stdout.write_text(process.stdout)
    stderr.write_text(process.stderr)
    row = {'name': name, 'command': command, 'started_at': started, 'ended_at': time.time(), 'returncode': process.returncode,
           'stdout': stdout.name, 'stderr': stderr.name,
           'stdout_sha256': hashlib.sha256(stdout.read_bytes()).hexdigest(), 'stderr_sha256': hashlib.sha256(stderr.read_bytes()).hexdigest()}
    rows.append(row)
    (receipt / 'summary.json').write_text(json.dumps({'checks': rows, 'passed': all(r['returncode'] == 0 for r in rows), 'expected_checks': 5,
        'all_checks_completed': len(rows) == 5, 'model_calls': 0, 'gpu_branch_executed': False, 'pytest_test_executions': 0,
        'base_standard_library_control_repeated': False}, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    return process.returncode


# Target-host metadata only: no .env read, no model file hashing/loading.
import stat
host_project=Path('/data0/zhuxinrui/projects/ProWorkSim')
external_models=sorted(Path('/data0/zhuxinrui/models').glob('*Qwen2.5*'))
asset_paths=[host_project/'.env',host_project/'runs/assets/models/Qwen3.5-9B-c20223623576',*external_models]
assets=[]
for p in asset_paths:
    info=p.lstat()
    assets.append({'path':str(p),'resolved_path':str(p.resolve(strict=True)), 'exists':p.exists(),
      'type':'symlink' if p.is_symlink() else 'directory' if p.is_dir() else 'file' if p.is_file() else 'other',
      'mode':oct(stat.S_IMODE(info.st_mode)),'host_uid':info.st_uid,'host_gid':info.st_gid,
      'symlink_target':str(p.readlink()) if p.is_symlink() else None})
(receipt/'asset-path-metadata.json').write_text(json.dumps({'scope':'requested .env and model-root metadata only',
    'paths':assets,'external_qwen25_directory_count':len(external_models),'content_read':False,'model_weights_hashed_or_loaded':False},indent=2)+'\n')
assert external_models, 'Expected externally migrated Qwen2.5 model root'

paths_and_tools = r'''
import json, os, subprocess
from pathlib import Path
old=Path('/data1/zhuxinrui/projects/ProWorkSim')
new=Path('/data0/zhuxinrui/projects/ProWorkSim')
home=Path('/home/zhuxinrui/datatmp/projects/ProWorkSim')
cache=Path('/home/zhuxinrui/.cache/huggingface')
cache_new=Path('/data0/zhuxinrui/.cache/huggingface')
result={'old_project_resolved':str(old.resolve()),'new_project_resolved':str(new.resolve()),'home_project_resolved':str(home.resolve()),
        'old_new_same_filesystem_object':old.samefile(new),'old_home_same_filesystem_object':old.samefile(home),
        'project_read_only':bool(os.statvfs(old).f_flag & os.ST_RDONLY),
        'hf_cache_visible':cache.is_dir(),'hf_cache_same_filesystem_object':cache.samefile(cache_new),
        'hf_cache_read_only':bool(os.statvfs(cache).f_flag & os.ST_RDONLY),'namespace_uid':os.getuid(),
        'nvidia_character_devices': [str(p) for p in Path('/dev').glob('nvidia*') if p.is_char_device()], 'tools':[]}
assert result['old_project_resolved']==str(old)
assert result['home_project_resolved']==str(old)
assert result['old_new_same_filesystem_object'] and result['old_home_same_filesystem_object']
assert result['project_read_only'] and result['hf_cache_read_only'] and result['hf_cache_same_filesystem_object']
assert result['nvidia_character_devices']==[]
for name in ['bash','git','rg','timeout','make','patch']:
    p=subprocess.run(['/usr/bin/'+name,'--version'],text=True,capture_output=True)
    result['tools'].append({'name':name,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    assert p.returncode==0, (name,p.stderr)
print(json.dumps(result,indent=2))
'''
if run_check('tools-and-paths', ['/usr/bin/python3.12','-B','-'], paths_and_tools):
    raise SystemExit(1)
run_check('venv-imports', [project+'/.venv/bin/python','-B','-','--packages','proworksim','openpyxl','duckdb','pytest','ruff'], probe)
run_check('cli-help', [project+'/.venv/bin/proworksim','--help'])
run_check('resident-imports', [project+'/runs/v016-sdk/resident-venv/bin/python','-B','-','--packages','proworksim','openpyxl','duckdb','torch','transformers','peft','accelerate'], probe)
run_check('cal2-imports', [project+'/artifacts/software-calibration-v051/cal2-sources/cal2/cpu-venv/bin/python','-B','-','--packages','pytest'], probe)
raise SystemExit(0 if all(r['returncode']==0 for r in rows) else 1)
