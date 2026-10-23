import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v054/deferred-scoring-parallel-r2'
OLD = 'proworksim-v054-deferred-scoring-r1.service'
NEW = 'proworksim-v054-deferred-scoring-parallel-r2.service'
SHA = '4aeafc44cfab0f2574b82d58a2a40dbb7a77db9fa32283b15862e5ec7573807c'


def show(unit):
    r = subprocess.run(['systemctl', '--user', 'show', unit,
        '--property=MainPID,ActiveState,SubState,InvocationID,KillMode,ControlGroup'],
        check=True, capture_output=True, text=True, timeout=15)
    return dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)


def process(pid):
    try:
        text = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return None
    parts = text[text.rfind(')') + 2:].split()
    return {'pid': pid, 'start_ticks': int(parts[19]), 'state': parts[0]}


def write(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


intent = json.loads((OUT / 'parent-freeze-intent.json').read_bytes())
quiet = json.loads((OUT / 'natural-child-exit.json').read_bytes())
assert quiet['plan']['sha256'] == SHA and quiet['child_signals'] == 0
assert hashlib.sha256((OUT / 'plan.json').read_bytes()).hexdigest() == SHA
pid = intent['parent_before']['pid']
stopped = False
try:
    old = show(OLD)
    assert old['MainPID'] == str(pid) and old['InvocationID'] == intent['old_unit_state']['InvocationID']
    p = process(pid)
    assert p['start_ticks'] == intent['parent_before']['start_ticks'] and p['state'] == 'T'
    group = Path('/sys/fs/cgroup' + intent['old_unit_state']['ControlGroup'])
    others = []
    for f in group.rglob('cgroup.procs'):
        for value in f.read_text().split():
            item = process(int(value))
            if item and item['pid'] != pid and item['state'] != 'Z':
                others.append(item)
    assert not others, 'Original scoring descendants have not drained'
    child = process(intent['child_before']['pid'])
    assert child is None or child['start_ticks'] != intent['child_before']['start_ticks'] or child['state'] == 'Z'
    service = '[Unit]\nDescription=ProWorkSim Qwen deferred scoring parallel r2\n\n[Service]\nType=simple\nRestart=no\nKillMode=process\n'
    service += 'WorkingDirectory=' + str(ROOT) + '\nEnvironment="PYTHONPATH=' + str(ROOT / 'src') + ':' + str(ROOT / 'tools') + ':' + str(ROOT) + '"\n'
    service += 'ExecStart=' + str(ROOT / '.venv/bin/python') + ' -B ' + str(ROOT / 'tools/run_deferred_scoring_parallel_v054_r2.py') + ' run --plan ' + str(OUT / 'plan.json') + ' --sha256 ' + SHA + '\n'
    with (OUT / NEW).open('x') as stream:
        stream.write(service)
    old_text = subprocess.run(['systemctl', '--user', 'cat', OLD], check=True, capture_output=True, text=True).stdout
    with (OUT / 'old-unit-retained.service').open('x') as stream:
        stream.write(old_text)
    write('service-handoff-intent.json', {'old_unit': OLD, 'new_unit': NEW, 'old_identity': old,
        'parent': p, 'original_child': child, 'live_old_descendants_except_parent': others,
        'only_old_frozen_parent_remaining': True, 'child_signals': 0, 'new_model_calls': 0,
        'original_progress_preserved': True, 'plan_sha256': SHA,
        'new_unit_definition_sha256': hashlib.sha256(service.encode()).hexdigest()})
    subprocess.run(['systemctl', '--user', 'stop', OLD], check=True, timeout=20)
    stopped = True
    after = show(OLD)
    assert after['MainPID'] == '0' and after['ActiveState'] in {'inactive', 'failed'}
    if group.exists():
        assert 'populated 1' not in (group / 'cgroup.events').read_text()
    subprocess.run(['systemctl', '--user', 'link', '--runtime', str(OUT / NEW)], check=True, capture_output=True, text=True, timeout=15)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=15)
    subprocess.run(['systemctl', '--user', 'start', NEW], check=True, timeout=15)
    time.sleep(1)
    current = show(NEW)
    write('new-manager-started.json', {'old_after': after, 'new_unit': current,
        'child_signals': 0, 'old_scoring_subtree_interrupted': False, 'new_model_calls': 0})
    assert current['ActiveState'] == 'active' and int(current['MainPID']) > 0
    print(json.dumps({'status': 'parallel_r2_started', 'unit': current, 'child_signals': 0}))
except BaseException:
    if not stopped:
        current = process(pid)
        if current and current['start_ticks'] == intent['parent_before']['start_ticks']:
            os.kill(pid, signal.SIGCONT)
    raise
