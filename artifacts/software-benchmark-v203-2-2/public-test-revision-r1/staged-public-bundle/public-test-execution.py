"""Bounded public command execution with a parent/child framework session journal."""
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

VERSION = 'v141-session-bound-public-test-execution-r1'
DEPLOYMENT_REVISION = 'v175-deferred-pytest-plugin-import-r1'
OBSERVER_VERSION = 'v141-session-bound-framework-observer-r1'
MAX_OUTPUT_BYTES = 32*1024**2
MAX_EVIDENCE_BYTES = 4*1024**2
MAX_SESSIONS = 1024
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
    return packaged if packaged.is_file() else here/'public_test_evidence_v175.py'


def sitecustomize_source():
    return '''import importlib.machinery, importlib.util, os, sys
_pws_own_dir = os.path.realpath(os.path.dirname(__file__))
_pws_original_paths = [p for p in sys.path if os.path.realpath(p or os.curdir) != _pws_own_dir]
_pws_original_spec = importlib.machinery.PathFinder.find_spec("sitecustomize", _pws_original_paths)
if _pws_original_spec is not None:
    _pws_original_module = importlib.util.module_from_spec(_pws_original_spec)
    sys.modules["sitecustomize"] = _pws_original_module
    _pws_original_spec.loader.exec_module(_pws_original_module)
if os.environ.get('PWS_TEST_OBSERVER_FRAMEWORK') != 'pytest':
    import pws_public_test_evidence_v141 as _pws_observer
    _pws_observer.install()
'''


def _nonnegative(value):
    return type(value) is int and value >= 0


def _counts(row):
    counts = row.get('counts')
    if (not isinstance(counts, dict) or set(counts) != set(COUNT_KEYS)
            or any(not (key == 'collected' and value is None) and not _nonnegative(value)
                   for key, value in counts.items())):
        raise ValueError('framework counts are missing or invalid')
    return counts


def _session_tree(records, *, framework, token, process_group):
    starts, finishes, positions = {}, {}, {}
    duplicates = 0
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError('framework evidence record must be an object')
        if (row.get('version') != OBSERVER_VERSION or row.get('token') != token
                or row.get('framework') != framework or framework not in {'pytest', 'django', 'sympy'}
                or row.get('pgid') != process_group or type(row.get('pid')) is not int
                or row['pid'] <= 0 or type(process_group) is not int or process_group <= 0):
            raise ValueError('framework record does not belong to this command')
        run = row.get('run_id')
        parent = row.get('parent_run_id')
        if (not isinstance(run, str) or not run or len(run) > 128
                or (parent is not None and (not isinstance(parent, str) or not parent
                                           or len(parent) > 128))):
            raise ValueError('missing or malformed framework session identity')
        event = row.get('event')
        if event not in {'start', 'finish'}:
            raise ValueError('unknown framework evidence event')
        target = starts if event == 'start' else finishes
        if run in target:
            if target[run] != row:
                raise ValueError('conflicting duplicate framework session record')
            duplicates += 1
            continue
        target[run] = row
        positions[(run, event)] = index
        if len(starts) > MAX_SESSIONS or len(finishes) > MAX_SESSIONS:
            raise ValueError('framework session count exceeds its bound')
    if not starts or set(starts) != set(finishes):
        raise ValueError('missing framework start or complete finish report')
    roots = [run for run, row in starts.items() if row['parent_run_id'] is None]
    if len(roots) != 1:
        raise ValueError('expected exactly one command-root framework session')
    root = roots[0]
    if framework != 'sympy' and starts[root]['pid'] != process_group:
        raise ValueError('pytest/unittest root is not the launched command process')
    # SymPy's documented hash-randomization subprocess can hold the unique root.
    # No child is chosen by test count: one complete root is still mandatory.
    for run, start in starts.items():
        end = finishes[run]
        if any(start.get(key) != end.get(key) for key in (
                'run_id', 'parent_run_id', 'pid', 'pgid', 'framework', 'token', 'version')):
            raise ValueError('framework session changed identity before finishing')
        if positions[(run, 'start')] >= positions[(run, 'finish')]:
            raise ValueError('framework finish preceded its start')
        _counts(end)
        if framework in {'pytest', 'django'} and end['counts']['collected'] is None:
            raise ValueError('framework collection count is missing')
        if (not _nonnegative(end.get('collection_errors'))
                or type(end.get('collection_complete')) is not bool
                or type(end.get('partial')) is not bool
                or type(end.get('exitstatus')) is not int
                or not isinstance(end.get('report_conflicts'), list)
                or end['report_conflicts']):
            raise ValueError('incomplete or conflicting framework result evidence')
        parent = start['parent_run_id']
        seen = {run}
        ancestor = parent
        while ancestor is not None:
            if ancestor not in starts or ancestor in seen:
                raise ValueError('orphaned or cyclic framework parent identity')
            seen.add(ancestor)
            ancestor = starts[ancestor]['parent_run_id']
        if parent is not None and not (
                positions[(parent, 'start')] < positions[(run, 'start')]
                < positions[(run, 'finish')] < positions[(parent, 'finish')]):
            raise ValueError('child session falls outside its parent lifetime')
    return root, starts, finishes, duplicates


def parse_test_evidence(raw, *, framework, token, process_group, returncode, timed_out):
    counts = dict.fromkeys(COUNT_KEYS)
    source, problem, root = None, None, None
    records, starts, finishes = [], {}, {}
    duplicate_records = 0
    try:
        if len(raw) > MAX_EVIDENCE_BYTES:
            raise ValueError('framework evidence exceeds its bounded size')
        records = [json.loads(line) for line in raw.splitlines() if line]
        root, starts, finishes, duplicate_records = _session_tree(
            records, framework=framework, token=token, process_group=process_group)
        counts = _counts(finishes[root])
        source = {key: starts[root][key] for key in ('run_id', 'parent_run_id', 'pid')}
        source.update(process_group=process_group, framework=framework,
                      delegated_hash_process=framework == 'sympy' and source['pid'] != process_group)
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        problem = str(error)
    result = finishes.get(root, {}) if source else {}
    collection_errors = result.get('collection_errors', 0)
    partial = result.get('partial', False)
    if timed_out:
        status = 'timed_out'
    elif source is None:
        status = 'unknown_collection' if returncode == 0 else 'failed'
    elif collection_errors:
        status = 'collection_failed'
    elif returncode != 0 or result['exitstatus'] != 0:
        status = ('all_skipped_or_xfailed' if counts['skipped'] or counts['xfailed'] else 'no_tests') \
            if framework == 'pytest' and returncode == 5 and result['exitstatus'] == 5 else 'failed'
    elif not result['collection_complete']:
        status = 'unknown_collection'
        problem = 'root collection completion was not observed'
    elif partial and not result.get('collect_only', False):
        status = 'partial'
    elif counts['failed'] or counts['errors']:
        status = 'failed'
    elif counts['passed'] > 0:
        status = 'verified'
    elif counts['skipped'] or counts['xfailed'] or counts['xpassed']:
        status = 'all_skipped_or_xfailed'
    else:
        status = 'no_tests'
    counts = dict(counts, tests_run=None if source is None else
                  counts['passed']+counts['failed']+counts['xpassed'])
    sessions = []
    if source:
        sessions = [{key: row[key] for key in (
            'run_id', 'parent_run_id', 'pid', 'framework', 'counts', 'exitstatus',
            'collection_errors', 'collection_complete', 'partial')}
            | {'root': run == root, 'test_reports': row.get('test_reports', []),
               'test_reports_sha256': row.get('test_reports_sha256'),
               'duplicate_reports_ignored': row.get('duplicate_reports_ignored', 0)}
            for run, row in finishes.items()]
    return {'passed': status == 'verified', 'validation_status': status, 'counts': counts,
        'test_evidence': {'version': VERSION, 'framework': framework, 'source': source,
            'report_count': len(finishes), 'journal_record_count': len(records),
            'nested_report_count': max(0, len(finishes)-1) if source else None,
            'duplicate_journal_records_ignored': duplicate_records,
            'error': problem, 'partial': partial if source else None,
            'root_counts_only': True, 'nested_failures_are_diagnostic_not_summed': True,
            'sessions': sessions, 'evidence_sha256': hashlib.sha256(raw).hexdigest(),
            'stdout_used_for_verdict': False,
            'security_scope': 'framework observation, not a same-UID anti-forgery boundary',
            'public_verification_is_hidden_acceptance': False}}


def execute_public_entry(entry, *, root, environment, timeout_seconds):
    if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
        raise TimeoutError('No time remains for this public command')
    kind = frontend(entry)
    observer = helper_path().read_bytes()
    began = time.monotonic()
    timed_out = False
    token = secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix='pws-public-evidence-v141-') as scratch, tempfile.TemporaryFile() as log:
        scratch = Path(scratch)
        report = scratch/'counts.jsonl'
        report.write_bytes(b'')
        module = scratch/'pws_public_test_evidence_v141.py'
        module.write_bytes(observer)
        module.chmod(0o444)
        startup = scratch/'sitecustomize.py'
        startup.write_text(sitecustomize_source())
        startup.chmod(0o444)
        env = dict(environment)
        env.pop('PWS_TEST_OBSERVER_PARENT_RUN', None)
        env.update(PWS_TEST_OBSERVER_REPORT=str(report), PWS_TEST_OBSERVER_TOKEN=token,
                   PWS_TEST_OBSERVER_FRAMEWORK=kind, PYTHONDONTWRITEBYTECODE='1')
        env['PYTHONPATH'] = str(scratch)+os.pathsep+env.get('PYTHONPATH', '')
        if kind == 'pytest':
            plugins = [p for p in env.get('PYTEST_PLUGINS', '').split(',') if p]
            env['PYTEST_PLUGINS'] = ','.join([*plugins, 'pws_public_test_evidence_v141'])
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
        'deployment_revision': DEPLOYMENT_REVISION, 'only_own_process_group_signalled': True, 'hidden_evaluation': False,
        'arbitrary_command': False}
