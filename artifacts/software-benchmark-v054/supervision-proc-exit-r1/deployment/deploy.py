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
OLD = 'proworksim-v054-formal-queue-three-volumes-r6.service'
NEW = 'proworksim-v054-formal-queue-supervision-r7.service'
OLD_ENTRY = ROOT / 'tools/run_qwen_three_volumes_v054_r6.py'
ENTRY = ROOT / 'tools/run_qwen_supervision_v054_r7.py'
STATE = ROOT / 'runs/software-benchmark-v054/formal-queue-r1/state.json'
REVISION = ROOT / 'runs/software-benchmark-v054/supervision-host-r7/revision.json'
SHA = 'a39b1b7c25794df9d12bd738dc90e78bd4423c9a466444bbf08238f2d5e4438f'


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=20)


def show(unit):
    out = command(['systemctl', '--user', 'show', unit,
        '--property=LoadState,ActiveState,SubState,MainPID,InvocationID,KillMode,FragmentPath']).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


def main():
    assert hashlib.sha256(REVISION.read_bytes()).hexdigest() == SHA
    assert not (OUT / 'handoff-intent.json').exists()
    assert show(NEW)['MainPID'] == '0'
    before = show(OLD)
    assert before['ActiveState'] == 'active' and before['KillMode'] == 'process'
    pid = int(before['MainPID'])
    argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
    assert str(OLD_ENTRY).encode() in argv
    old_definition = command(['systemctl', '--user', 'cat', OLD]).stdout
    (OUT / (OLD + '.retained')).write_text(old_definition)
    definition = ('[Unit]\nDescription=ProWorkSim Qwen future supervision host r7\n\n[Service]\n'
        'Type=simple\nRestart=no\nKillMode=process\n'
        f'WorkingDirectory={ROOT}\nEnvironment="PYTHONPATH={ROOT}/src:{ROOT}/tools:{ROOT}"\n'
        f'ExecStart={ROOT}/.venv/bin/python -B {ENTRY} run --revision {REVISION} --sha256 {SHA}\n')
    unit_file = OUT / NEW
    with unit_file.open('x') as stream:
        stream.write(definition)
    deadline = time.monotonic() + 45
    frozen = False
    stopped = False
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('No safe sleep boundary; old queue remains running')
            if (Path('/proc') / str(pid) / 'wchan').read_text().strip() != 'hrtimer_nanosleep':
                time.sleep(.1)
                continue
            raw = STATE.read_bytes()
            assert show(OLD) == before
            os.kill(pid, signal.SIGSTOP)
            frozen = True
            process_state = (Path('/proc') / str(pid) / 'status').read_text().split('State:', 1)[1].splitlines()[0]
            if STATE.read_bytes() == raw and 'T' in process_state:
                break
            os.kill(pid, signal.SIGCONT)
            frozen = False
        with (OUT / 'state-before-stop.json').open('xb') as stream:
            stream.write(raw)
        write(OUT / 'handoff-intent.json', {'utc': now(), 'old_unit': OLD, 'new_unit': NEW,
            'old_identity': before, 'state_before_sha256': hashlib.sha256(raw).hexdigest(),
            'revision_sha256': SHA, 'unit_definition_sha256': hashlib.sha256(definition.encode()).hexdigest(),
            'only_old_manager_signalled': True, 'worker_services_signalled': 0,
            'GPU_services_signalled': 0, 'entered_episodes_replayed': 0})
        command(['systemctl', '--user', 'stop', OLD])
        frozen = False
        stopped = True
        assert show(OLD)['MainPID'] == '0'
        command(['systemctl', '--user', 'link', '--runtime', str(unit_file)])
        command(['systemctl', '--user', 'daemon-reload'])
        loaded = show(NEW)
        assert loaded['MainPID'] == '0' and loaded['KillMode'] == 'process'
        assert Path(loaded['FragmentPath']).resolve() == unit_file.resolve()
        result = command(['systemctl', '--user', 'start', NEW])
        write(OUT / 'new-manager-started.json', {'utc': now(), 'unit': show(NEW),
            'stdout': result.stdout, 'stderr': result.stderr,
            'worker_services_signalled': 0, 'GPU_services_signalled': 0})
    except BaseException as error:
        if frozen:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        write(OUT / 'deployment-error.json', {'utc': now(), 'error': repr(error),
            'old_manager_stopped': stopped, 'new_manager': show(NEW),
            'no_blind_rollback_after_possible_new_host_adoption': True})
        raise
    print(json.dumps({'utc': now(), 'status': 'new_r7_manager_started', 'unit': NEW}))


if __name__ == '__main__':
    main()
