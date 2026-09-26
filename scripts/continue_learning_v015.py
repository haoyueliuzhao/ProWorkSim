"""Wait for complete fixed screening, select mechanically, launch one bounded pilot.

A new output directory is mandatory. This observer never restarts an attempted
screen or pilot. Its downstream pilot owns the fixed N0/N1/software stage graph.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts.learning_report_v015 import build_report, write_report
from scripts.learning_resources_v015 import resource_report
from scripts.run_candidate_screen_v015 import read, write, pid_record
from scripts.select_candidate_v015 import choose, ref, validated_readiness


def after_screen(config, supervisor, output):
    """No model action before all immutable screening measurements are present."""
    if supervisor['status'] != 'complete' or any(j['status'] != 'complete' for j in supervisor['jobs']):
        raise ValueError('Screening incomplete; no missing condition is assigned a score')
    report = build_report(config['study_manifest'], project_root=config['project'], source_root=supervisor['config']['source'])
    resources = resource_report(config['launch_directory'])
    selection = choose(report, resources, validated_readiness(supervisor, report))
    selection['inputs'] = {'supervisor': ref(config['screen_supervisor']), 'study_manifest': ref(config['study_manifest'])}
    destination = output/'selection'
    write_report(report, destination)
    write(destination/'resources.json', resources)
    selection.update(report=ref(destination/'report.json'), resources=ref(destination/'resources.json'))
    write(destination/'selection.json', selection)
    if selection['status'] != 'selected':
        return None, selection
    candidate = selection['selected']['candidate_id']
    original = next(j for j in supervisor['config']['candidates'] if j['name'] == candidate)
    declared = read(selection['selected']['screen_protocol']['path'])
    count = declared['runtime']['profile']['devices']
    # A100 physical indices are explicit and identical in device count across
    # the two conditions. No other process is signalled, displaced or stopped.
    lanes = {'mc': [0], 'rtg': [1]} if count == 1 else {'mc': [0, 1, 2], 'rtg': [3, 4, 5]} if count == 3 else None
    if lanes is None:
        raise ValueError('Unregistered resource topology')
    pilot = {key: config[key] for key in ('project', 'source', 'source_commit', 'python', 'launcher_python', 'launcher', 'environment')}
    pilot.update(version='learning-pilot-queue-config-v0.15',
        selected_screen_protocol=selection['selected']['screen_protocol']['path'],
        selection_record=str(destination/'selection.json'), model_path=original['model_path'],
        weight_manifest=original['weight_manifest'], physical_gpus=lanes, poll_seconds=30)
    return pilot, selection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    config = read(args.config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=config['source'], text=True).strip()
    if head != config['source_commit'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=config['source'], text=True).strip():
        raise ValueError('Continuation source must be the declared clean frozen commit')
    wait_budget = config['screen_wait_seconds']
    if type(wait_budget) not in (int, float) or not 0 < wait_budget <= 7*86400:
        raise ValueError('Declare a bounded wait of at most seven days')
    state = {'version': 'learning-continuation-v0.15', 'status': 'waiting_screen', 'started_at': time.time(),
             'config': config, 'source_commit': head, 'pilot_attempted': False,
             'scope': 'No extension/retry of samples or numerical gates. Future stages start only from predeclared immutable evidence.'}
    write(output/'state.json', state)
    try:
        while True:
            supervisor = read(config['screen_supervisor'])
            status = (supervisor or {}).get('status')
            state.update(observed_at=time.time(), screen_status=status)
            if status == 'complete':
                pilot, selection = after_screen(config, supervisor, output)
                state['selection_status'] = selection['status']
                if pilot is None:
                    state['status'] = 'no_training_ready_candidate'
                    return 1
                pilot_path = output/'pilot-config.json'
                write(pilot_path, pilot)
                command = [config['launcher_python'], '-m', 'scripts.run_learning_pilot_v015',
                           '--config', str(pilot_path), '--output', str(output/'pilot')]
                state.update(status='pilot_launch_intent', pilot_attempted=True, pilot_command=command,
                             pilot_config_sha256=hashlib.sha256(pilot_path.read_bytes()).hexdigest())
                write(output/'state.json', state)
                environment = {**os.environ, **config['environment'], 'PYTHONPATH': str(Path(config['source'])/'src')}
                with (output/'pilot-observer.log').open('x') as log:
                    child = subprocess.Popen(command, cwd=config['source'], env=environment,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                state.update(status='pilot_started', pilot_pid=child.pid, pilot_process=pid_record(child.pid),
                             followup_state=str(output/'pilot/scheduler.json'))
                # The downstream observer and its own persisted queue now own
                # progression; this process does not monitor or recreate it.
                return 0
            if status in {'finished_with_incomplete_jobs', 'observer_error', 'observer_detached'}:
                state.update(status='screen_not_complete', stop_reason=status)
                return 1
            if time.time()-state['started_at'] >= wait_budget:
                state['status'] = 'screen_wait_timeout'
                return 1
            write(output/'state.json', state)
            time.sleep(30)
    except (Exception, KeyboardInterrupt) as error:
        state.update(status='observer_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        state['last_written_at'] = time.time()
        write(output/'state.json', state)


if __name__ == '__main__':
    sys.exit(main())
