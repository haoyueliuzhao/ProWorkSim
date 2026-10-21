"""One real CPU systemd exit/GC race and synthetic post-release ownership gates."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_resources_v054 import create_episode_resources, release_episode_resources


def load(name):
    spec = importlib.util.spec_from_file_location('proworksim.' + name + '_exit_control', HERE / 'src/proworksim' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supervision = load('software_benchmark_supervision_v054')
session_module = load('software_benchmark_resident_session_v054')
output = HERE / 'control'
output.mkdir(exist_ok=False)
claim_id = uuid.uuid4().hex
resources = create_episode_resources(claim_id, output)
trigger = output / 'allow-natural-exit'
process = None
receipt = {'version': 'v054-natural-cpu-sentinel-exit-control-r1', 'model_calls': 0,
           'GPU_loads': 0, 'formal_claims': 0, 'scope': 'one independent CPU sentinel only',
           'sources': [reference(HERE / 'src/proworksim' / (name + '.py')) for name in (
               'software_benchmark_supervision_v054', 'software_benchmark_resident_session_v054')]}
try:
    process, scope = supervision.launch_owned([
        '/usr/bin/python3', '-c',
        'from pathlib import Path; import time,sys; p=Path(sys.argv[1]); end=time.monotonic()+10\n'
        'while not p.exists() and time.monotonic()<end: time.sleep(.01)\n'
        'assert p.exists()', str(trigger)],
        claim_id=claim_id, role='model', resources=resources, runtime_seconds=20,
        stdin=subprocess.DEVNULL, stdout=(output / 'sentinel.stdout').open('xb'),
        stderr=(output / 'sentinel.stderr').open('xb'))
    raw_systemctl = supervision._systemctl
    witnessed = {}

    def expire_between_show_and_stop(*arguments, manager='user'):
        if arguments[:2] == ('stop', '--no-block') and arguments[2] == scope['unit']:
            witnessed['pre_stop_identity'] = supervision.properties(scope['unit'], manager=manager)
            assert int(witnessed['pre_stop_identity']['MainPID']) == scope['main']['pid']
            trigger.touch(exist_ok=False)
            assert process.wait(timeout=12) == 0
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = supervision.properties(scope['unit'], manager=manager)
                if state.get('LoadState') == 'not-found':
                    witnessed['after_natural_exit'] = state
                    break
                time.sleep(.02)
            assert witnessed.get('after_natural_exit', {}).get('LoadState') == 'not-found'
        return raw_systemctl(*arguments, manager=manager)

    supervision._systemctl = expire_between_show_and_stop
    quiet = supervision.stop_owned(scope)
    supervision.assert_outer_launcher_exited(scope)
    assert quiet['stop_returncode'] == 5 and quiet['registered_main_exited'] is True
    assert quiet['unit_garbage_collected'] is True and quiet['populated'] is False
    receipt['actual_exit_race'] = {'scope': scope, 'observed': witnessed, 'quiescence': quiet}
    supervision._systemctl = raw_systemctl

    # A current registered PID remains a refusal even if a service observation
    # says inactive/not-found. No second service or process is started.
    bad = {**scope, 'main': supervision.process_identity(os.getpid())}
    try:
        supervision.assert_quiet(bad)
    except RuntimeError:
        receipt['same_recorded_PID_still_alive_rejected'] = True
    else:
        raise AssertionError('Live registered PID accepted')

    logs = []
    healthy = {}

    class Client:
        def call(self, operation, **kwargs):
            logs.append(operation)
            if operation == 'status':
                return healthy
            if operation == 'poison':
                return {'inflight': 0, 'poisoned': True}
            raise AssertionError(operation)

    session_module.admin_client = lambda *a, **kw: Client()
    session_module.suspend_registered = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('No synthetic suspend permitted'))
    for mode in ('REF', 'MATCH_PROJECT'):
        directory = output / mode
        directory.mkdir()
        session = {'claim_id': uuid.uuid4().hex, 'session_root': str(directory),
                   'resident_declaration': {'mode': mode}, 'resident_ready': {
                       'host_process': supervision.process_identity(os.getpid())},
                   'admin_identity': {'synthetic': True}}
        (directory / 'session.json').write_text(json.dumps(session))
        if mode == 'REF':
            result = {'claim_id': session['claim_id'], 'released': True, 'quiescent': True,
                      'resident_still_loaded': True, 'engine_unfinished': 0,
                      'engine_paused': True, 'cache_reset': True, 'weights_unloaded': False}
            healthy = {'poisoned': False, 'phase': 'idle', 'active_claim': None, 'inflight': 0}
        else:
            result = {'claim_id': session['claim_id'], 'state': 'released', 'quiescence': {
                'owner_idle': True, 'model_busy': False, 'active_session': None,
                'learning_unchanged': True, 'rng_restored_exactly': True, 'weights_reloaded': False}}
            healthy = {'resident': True, 'poisoned': None, 'state': 'idle',
                       'active_claim': None, 'inflight': None}
        release = {'session': reference(directory / 'session.json'), 'result': result}
        (directory / 'release.json').write_text(json.dumps(release))
        before = len(logs)
        skipped = session_module.poison_session(session, 'synthetic administrative closure failure')
        assert skipped['poisoned'] is False and logs[before:] == ['status']
        assert not (directory / 'poison.json').exists()
        # A mismatched claimed release cannot use the exemption.
        release['result']['claim_id'] = 'f' * 32
        (directory / 'release.json').write_text(json.dumps(release))
        before = len(logs)
        refused = session_module.poison_session(session, 'synthetic mismatched release')
        assert refused['poisoned'] is True and logs[before:] == ['poison']
        receipt[mode + '_post_release_guard'] = {
            'exact_release_live_idle_skips_poison_and_STOP': True,
            'wrong_claim_release_fails_closed': True, 'model_requests': 0}
    receipt['passed'] = True
finally:
    if process is not None and process.poll() is None:
        trigger.touch(exist_ok=True)
        process.wait(timeout=12)
    receipt['resource_release'] = release_episode_resources(resources)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'passed': receipt.get('passed', False), 'receipt': reference(output / 'receipt.json')}))
