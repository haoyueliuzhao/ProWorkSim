import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from datetime import datetime, timezone

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = Path(__file__).resolve().parent
UNIT = 'proworksim-v055-deepseek-six-conditions-native-host-r9.service'
ENTRY = ROOT / 'tools/run_deepseek_queue_native_host_v055_r9.py'
STATE = ROOT / 'runs/software-benchmark-v055/queue-r1/state.json'
PLAN = ROOT / 'runs/software-benchmark-v055/partial-export-recovery-r1/plan.json'
PLAN_SHA = '4bdebe65c9946ecde450b44450f84e3d1570c4f066bb7b32e5c40dae497dc8c8'
REVISION = ROOT / 'runs/software-benchmark-v055/native-host-revision-r9/revision.json'
REVISION_SHA = 'ecb60e422eb856527112bb66452f03aa28097b5ede79fb58648feeb5d7638bf2'


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=20, **kwargs)


def show():
    out = command(['systemctl', '--user', 'show', UNIT,
        '--property=LoadState,ActiveState,SubState,MainPID,InvocationID,KillMode,FragmentPath']).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


def main():
    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA
    assert hashlib.sha256(REVISION.read_bytes()).hexdigest() == REVISION_SHA
    assert not (OUT / 'handoff-intent.json').exists()
    before = show()
    assert before['KillMode'] == 'process'
    definition = command(['systemctl', '--user', 'cat', UNIT]).stdout
    assert str(ENTRY) in definition and REVISION_SHA in definition
    unit_file = OUT / UNIT
    with unit_file.open('x') as stream:
        stream.write(definition)
    pid = int(before['MainPID'])
    stopped = False
    frozen = False
    try:
        if before['ActiveState'] == 'active':
            assert pid > 0
            argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
            assert str(ENTRY).encode() in argv and REVISION_SHA.encode() in argv
            deadline = time.monotonic() + 45
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError('No safe manager sleep boundary; no handoff')
                if (Path('/proc') / str(pid) / 'wchan').read_text().strip() != 'hrtimer_nanosleep':
                    time.sleep(.1)
                    continue
                raw = STATE.read_bytes()
                assert show() == before
                os.kill(pid, signal.SIGSTOP)
                frozen = True
                process_state = (Path('/proc') / str(pid) / 'status').read_text().split('State:', 1)[1].splitlines()[0]
                if STATE.read_bytes() == raw and 'T' in process_state:
                    break
                os.kill(pid, signal.SIGCONT)
                frozen = False
        else:
            assert before['ActiveState'] in {'inactive', 'failed'} and pid == 0
            raw = STATE.read_bytes()
        with (OUT / 'state-before-stop.json').open('xb') as stream:
            stream.write(raw)
        write(OUT / 'handoff-intent.json', {
            'utc': now(), 'manager_before': before,
            'state_before_sha256': hashlib.sha256(raw).hexdigest(),
            'unit_definition_sha256': hashlib.sha256(definition.encode()).hexdigest(),
            'same_exact_service_definition_linked_for_reliable_restart': True,
            'worker_services_signalled': 0, 'gpu_services_signalled': 0,
            'formal_tasks_replayed': 0, 'plan_sha256': PLAN_SHA,
        })
        if pid:
            command(['systemctl', '--user', 'stop', UNIT])
            frozen = False
        stopped = True
        assert show()['MainPID'] == '0'
        linked = command(['systemctl', '--user', 'link', '--runtime', str(unit_file)])
        command(['systemctl', '--user', 'daemon-reload'])
        inactive = show()
        assert inactive['MainPID'] == '0' and inactive['KillMode'] == 'process'
        assert Path(inactive['FragmentPath']).resolve() == unit_file.resolve()
        write(OUT / 'same-definition-linked.json', {'utc': now(), 'unit': inactive,
            'stdout': linked.stdout, 'stderr': linked.stderr})
        env = dict(os.environ)
        env['PYTHONPATH'] = str(ROOT / 'src') + ':' + str(ROOT / 'tools')
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B',
            str(ROOT / 'tools/repair_partial_export_v055_r1.py'), 'register',
            '--plan', str(PLAN), '--sha256', PLAN_SHA], cwd=ROOT, env=env,
            text=True, capture_output=True, timeout=45)
        write(OUT / 'registration-command.json', {'utc': now(), 'returncode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError('Registration failed; preserve evidence and resume original manager')
    finally:
        if frozen:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        current = show()
        if stopped or ((OUT / 'handoff-intent.json').exists() and current['MainPID'] == '0'):
            fragment = current.get('FragmentPath')
            if not fragment or Path(fragment).resolve() != unit_file.resolve():
                command(['systemctl', '--user', 'link', '--runtime', str(unit_file)])
                command(['systemctl', '--user', 'daemon-reload'])
            result = command(['systemctl', '--user', 'start', UNIT])
            write(OUT / 'same-manager-restarted.json', {'utc': now(), 'unit': show(),
                'stdout': result.stdout, 'stderr': result.stderr,
                'worker_services_signalled': 0, 'gpu_services_signalled': 0})
    print(json.dumps({'utc': now(), 'status': 'registered_and_original_manager_restarted'}))


if __name__ == '__main__':
    main()
