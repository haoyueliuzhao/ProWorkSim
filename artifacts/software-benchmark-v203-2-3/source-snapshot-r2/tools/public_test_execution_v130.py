"""Shared, stdlib-only public command execution and structured test evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import tempfile
import time

VERSION = 'v130-public-test-execution-evidence-r1'
MAX_OUTPUT_BYTES = 32*1024**2
MAX_EVIDENCE_BYTES = 64*1024
COUNT_KEYS = ('collected', 'passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed')


def frontend(entry):
    argv = entry.get('argv', [])
    if argv[1:3] == ['-m', 'pytest']:
        return 'pytest'
    if argv[1:2] == ['bin/test']:
        return 'sympy'
    if argv[1:5] == ['tests/runtests.py', '--noinput', '--parallel', '1']:
        return 'django'
    return 'unknown'


def helper_path():
    here = Path(__file__).resolve().parent
    packaged = here/'public-test-evidence.py'
    return packaged if packaged.is_file() else here/'public_test_evidence_v130.py'


def sitecustomize_source():
    """Run the original hook in its original module before adding observation."""
    return '''import importlib.machinery, importlib.util, os, sys
_pws_own_dir = os.path.realpath(os.path.dirname(__file__))
_pws_original_paths = [p for p in sys.path if os.path.realpath(p or os.curdir) != _pws_own_dir]
_pws_original_spec = importlib.machinery.PathFinder.find_spec("sitecustomize", _pws_original_paths)
if _pws_original_spec is not None:
    _pws_original_module = importlib.util.module_from_spec(_pws_original_spec)
    sys.modules["sitecustomize"] = _pws_original_module
    _pws_original_spec.loader.exec_module(_pws_original_module)
import pws_public_test_evidence_v130 as _pws_observer
_pws_observer.install()
'''


def parse_test_evidence(raw, *, framework, token, process_group, returncode, timed_out):
    """Only a completed framework report counts; arbitrary stdout is not an input."""
    counts = {key: None for key in COUNT_KEYS}
    source = None
    records = []
    problem = None
    try:
        if len(raw) > MAX_EVIDENCE_BYTES:
            raise ValueError('framework evidence exceeds its bounded size')
        records = [json.loads(line) for line in raw.splitlines() if line]
        if len(records) != 1:
            raise ValueError('expected exactly one complete framework report')
        row = records[0]
        if not isinstance(row, dict):
            raise ValueError('framework report must be an object')
        if (row.get('version') != 'v130-public-framework-count-observer-r1'
                or row.get('token') != token or row.get('framework') != framework
                or row.get('pgid') != process_group or type(row.get('pid')) is not int
                or framework not in {'pytest', 'django', 'sympy'}):
            raise ValueError('framework report does not belong to this command')
        supplied = row.get('counts', {})
        if not isinstance(supplied, dict) or set(supplied) != set(COUNT_KEYS) or any(
                not (key == 'collected' and value is None) and (type(value) is not int or value < 0)
                for key, value in supplied.items()):
            raise ValueError('framework counts are missing or invalid')
        counts = supplied
        source = {'pid': row['pid'], 'process_group': process_group, 'framework': framework}
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        problem = str(error)
    if timed_out:
        status = 'timed_out'
    elif returncode != 0:
        status = ('all_skipped_or_xfailed' if counts['skipped'] or counts['xfailed'] else 'no_tests') \
            if framework == 'pytest' and returncode == 5 and source else 'failed'
    elif source is None:
        status = 'unknown_collection'
    elif counts['failed'] or counts['errors']:
        status = 'failed'
    elif counts['passed'] > 0:
        status = 'verified'
    elif counts['skipped'] or counts['xfailed'] or counts['xpassed']:
        status = 'all_skipped_or_xfailed'
    else:
        status = 'no_tests'
    counts = {**counts, 'tests_run': None if source is None else
              counts['passed']+counts['failed']+counts['xpassed']}
    return {'passed': status == 'verified', 'validation_status': status, 'counts': counts,
        'test_evidence': {'version': VERSION, 'framework': framework, 'source': source,
            'report_count': len(records), 'error': problem,
            'evidence_sha256': hashlib.sha256(raw).hexdigest(), 'stdout_used_for_verdict': False,
            'security_scope': 'framework observation, not a same-UID anti-forgery boundary',
            'public_verification_is_hidden_acceptance': False}}


def execute_public_entry(entry, *, root, environment, timeout_seconds):
    """Manage only this command's process group, never other actor children."""
    if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
        raise TimeoutError('No time remains for this public command')
    kind = frontend(entry)
    observer = helper_path().read_bytes()
    began = time.monotonic()
    timed_out = False
    token = secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix='pws-public-evidence-v130-') as scratch, tempfile.TemporaryFile() as log:
        scratch = Path(scratch)
        report = scratch/'counts.jsonl'
        report.write_bytes(b'')
        module = scratch/'pws_public_test_evidence_v130.py'
        module.write_bytes(observer)
        module.chmod(0o444)
        startup = scratch/'sitecustomize.py'
        startup.write_text(sitecustomize_source())
        startup.chmod(0o444)
        env = dict(environment)
        env.update(PWS_TEST_OBSERVER_REPORT=str(report), PWS_TEST_OBSERVER_TOKEN=token,
                   PWS_TEST_OBSERVER_FRAMEWORK=kind, PYTHONDONTWRITEBYTECODE='1')
        env['PYTHONPATH'] = str(scratch)+os.pathsep+env.get('PYTHONPATH', '')
        if kind == 'pytest':
            plugins = [p for p in env.get('PYTEST_PLUGINS', '').split(',') if p]
            env['PYTEST_PLUGINS'] = ','.join([*plugins, 'pws_public_test_evidence_v130'])
        process = subprocess.Popen(entry['argv'], cwd=root, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            end = began+timeout_seconds
            while True:
                observed = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if observed is not None:
                    break
                if time.monotonic() >= end:
                    timed_out = True
                    break
                time.sleep(min(.05, max(0, end-time.monotonic())))
        finally:
            # Keep the leader unreaped until signalling; do not risk PID reuse.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
        log.seek(0, os.SEEK_END)
        length = log.tell()
        if length > MAX_OUTPUT_BYTES:
            raise ValueError('Public-test output exceeds the existing 32-MiB feedback bound')
        log.seek(0)
        raw = log.read()
        with report.open('rb') as stream:
            evidence = stream.read(MAX_EVIDENCE_BYTES+1)
    validation = parse_test_evidence(evidence, framework=kind, token=token,
        process_group=process.pid, returncode=process.returncode, timed_out=timed_out)
    validation['test_evidence']['observer_sha256'] = hashlib.sha256(observer).hexdigest()
    return {**validation, 'version': VERSION, 'command_executed': True,
        'argv': list(entry['argv']), 'cwd': str(root), 'returncode': process.returncode,
        'timed_out': timed_out, 'wall_seconds': time.monotonic()-began,
        'output': raw.decode('utf-8', 'backslashreplace'),
        'output_sha256': hashlib.sha256(raw).hexdigest(), 'output_bytes': length,
        'stdout_utf8_strict': raw.decode('utf-8', 'backslashreplace').encode('utf-8') == raw,
        'only_own_process_group_signalled': True, 'hidden_evaluation': False,
        'arbitrary_command': False}
