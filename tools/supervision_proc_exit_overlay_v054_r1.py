"""Bounded retry of the registered /proc identity exit race, in a new host layer.

Original supervision sources and their scope/timeout checks are never edited.
Only a pre-stop identity read that names the registered main PID is retried.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
KERNEL = ROOT / 'runs/software-benchmark-v054/kernel-optimization-r1/revision-root-r6'
VERSION = 'v054-supervision-registered-proc-exit-overlay-r1'
TOOL = ROOT / 'tools/supervision_proc_exit_overlay_v054_r1.py'
ENTRY = ROOT / 'tools/run_benchmark_episode_supervision_v054_r1.py'
HOST = ROOT / 'tools/run_qwen_supervision_v054_r7.py'
MAX_ATTEMPTS = 3
RETRY_WINDOW_SECONDS = 0.25
ROOTS = {'canonical': ROOT, 'kernel': KERNEL}
ENTRIES = {'canonical': ROOT / 'tools/run_benchmark_episode_ref_handoff_v054_r1.py',
           'kernel': KERNEL / 'tools/run_benchmark_episode_v054.py'}


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def checked(ref):
    if reference(ref['path']) != ref:
        raise ValueError('Supervision overlay evidence changed: ' + ref['path'])
    return Path(ref['path'])


def write_new(path, value):
    path = Path(path)
    with path.open('xb') as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
    return reference(path)


def source_refs():
    return {name: {'root': str(root), 'entry': reference(ENTRIES[name]),
        'supervision': reference(root / 'src/proworksim/software_benchmark_supervision_v054.py')}
        for name, root in ROOTS.items()}


def validate(ref):
    value = json.loads(checked(ref).read_bytes())
    if (value.get('version') != VERSION or value.get('maximum_attempts') != MAX_ATTEMPTS
            or value.get('retry_window_seconds') != RETRY_WINDOW_SECONDS
            or value.get('full_original_quiet_checks_retained') is not True
            or value.get('original_stop_seconds_unchanged') is not True
            or value.get('model_calls') != 0 or value.get('sources') != source_refs()):
        raise ValueError('Unknown bounded supervision overlay')
    if value.get('files') != [reference(x) for x in (TOOL, ENTRY, HOST)]:
        raise ValueError('Supervision wrapper or host source changed')
    return value


def bounded_stop(original, scope, *, clock=time.monotonic):
    """Re-enter only before the original stop/poll phase; never assert quiet here.

The admitted original sources raise this exact FileNotFoundError only while
reading MainPID before issuing stop. Their assert_quiet already handles a
vanished PID, so an error after the stop/poll boundary is not retried here.
No original stop_seconds, watchdog deadline or polling timeout is changed.
"""
    pid = scope.get('main', {}).get('pid')
    if type(pid) is not int or pid <= 0:
        return original(scope)
    expected = f'/proc/{pid}/stat'
    started, failures = clock(), []
    for attempt in range(MAX_ATTEMPTS):
        try:
            result = original(scope)
            if failures:
                result = {**result, 'proc_exit_identity_retry': {
                    'version': VERSION, 'attempts': attempt + 1,
                    'failures': failures, 'full_original_stop_and_quiet_checks': True}}
            return result
        except FileNotFoundError as error:
            if error.errno != errno.ENOENT or error.filename != expected:
                raise
            failures.append({'type': type(error).__name__, 'errno': error.errno,
                             'filename': error.filename, 'attempt': attempt + 1})
            # No sleep, no exception swallowing: retry admission closes after
            # 250 ms, and at most two extra pre-stop observations are possible.
            if attempt + 1 >= MAX_ATTEMPTS or clock() - started >= RETRY_WINDOW_SECONDS:
                raise
    raise AssertionError('Bounded loop fell through')


def original_module(mode, overlay):
    source = overlay['sources'][mode]
    root = Path(source['root'])
    sys.path[:0] = [str(root / 'src'), str(root)]
    module = importlib.import_module('proworksim.software_benchmark_supervision_v054')
    if reference(module.__file__) != source['supervision']:
        raise ValueError('Selected original supervision module crossed source roots')
    return module


def install_parent(ref, mode):
    overlay = validate(ref)
    if any(name in sys.modules for name in (
            'proworksim.software_benchmark_runner_v054', 'proworksim.software_benchmark_episode_v054')):
        raise ValueError('Install the sealed host overlay before importing the original runner')
    module = original_module(mode, overlay)
    original_stop = module.stop_owned
    module.stop_owned = lambda scope: bounded_stop(original_stop, scope)

    def start_watchdog(spec, directory):
        directory = Path(directory)
        spec_path, receipt = directory / 'watchdog-spec.json', directory / 'quiescence.json'
        write_new(spec_path, spec)
        write_new(directory / 'watchdog-supervision-overlay-r1.json', {
            'version': VERSION, 'overlay': ref, 'source_mode': mode,
            'original_supervision': overlay['sources'][mode]['supervision'],
            'scope_inventory_unchanged': True, 'original_hard_deadline_unchanged': True,
            'model_calls': 0})
        process = subprocess.Popen([
            sys.executable, '-B', str(TOOL), 'watch', '--overlay', ref['path'],
            '--sha256', ref['sha256'], '--source', mode, '--watch', str(spec_path),
            '--receipt', str(receipt)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=(directory / 'watchdog.stderr').open('xb'), start_new_session=True)
        return process, receipt

    module.start_watchdog = start_watchdog
    return overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['watch'])
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--source', choices=sorted(ROOTS), required=True)
    parser.add_argument('--watch', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    ref = reference(args.overlay)
    if ref['sha256'] != args.sha256:
        raise ValueError('Child supervision overlay SHA differs')
    overlay = validate(ref)
    module = original_module(args.source, overlay)
    original_stop = module.stop_owned
    module.stop_owned = lambda scope: bounded_stop(original_stop, scope)
    result = module.watchdog(args.watch, args.receipt)
    return 0 if result['all_quiet'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
