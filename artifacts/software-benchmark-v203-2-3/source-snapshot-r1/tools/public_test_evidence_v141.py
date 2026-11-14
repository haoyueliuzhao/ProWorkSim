"""Session-scoped public framework observation, including nested test runners.

The journal is command-bound observation, not a same-UID anti-forgery boundary.
It does not change test argv, expected outcomes, seeds, or exception handling.
"""
import fcntl
import hashlib
import importlib.machinery
import json
import os
import secrets
import sys
import threading

VERSION = 'v141-session-bound-framework-observer-r1'
COUNT_KEYS = ('collected', 'passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed')
_installed = False
_local = threading.local()
_PARENT = 'PWS_TEST_OBSERVER_PARENT_RUN'


def _stack():
    if getattr(_local, 'pid', None) != os.getpid():
        _local.pid, _local.stack = os.getpid(), []
    return _local.stack


def _write(row):
    path = os.environ.get('PWS_TEST_OBSERVER_REPORT')
    token = os.environ.get('PWS_TEST_OBSERVER_TOKEN')
    if not path or not token:
        return
    value = dict(row, version=VERSION, token=token)
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(raw)
        while view:
            size = os.write(fd, view)
            if not size:
                raise OSError('framework evidence write made no progress')
            view = view[size:]
    finally:
        os.close(fd)


def begin(framework):
    active = _stack()
    old_parent = os.environ.get(_PARENT)
    value = {'run_id': secrets.token_hex(16),
             'parent_run_id': active[-1]['run_id'] if active else old_parent,
             'framework': framework, 'pid': os.getpid(), 'pgid': os.getpgrp()}
    active.append(value)
    value['_old_parent'] = old_parent
    os.environ[_PARENT] = value['run_id']
    _write({key: val for key, val in dict(value, event='start').items()
            if not key.startswith('_')})
    return value


def abandon(value):
    active = _stack()
    if active and active[-1] is value:
        active.pop()
        previous = value.get('_old_parent')
        if previous is None:
            os.environ.pop(_PARENT, None)
        else:
            os.environ[_PARENT] = previous


def finish(value, counts, **details):
    try:
        _write({**{key: val for key, val in value.items() if not key.startswith('_')},
                'event': 'finish', 'counts': counts, **details})
    finally:
        abandon(value)


class PytestSessionObserver:
    """One object per Config: nested pytest.main calls cannot reset outer counts."""

    def __init__(self, config):
        self.config = config
        self.run = None
        self.reports = {}
        self.collection = {}
        self.invocations = {}
        self.current = {}
        self.duplicates = 0
        self.conflicts = []
        self.collection_finished = False

    def pytest_sessionstart(self, session):
        self.run = begin('pytest')

    def _retain(self, table, key, value):
        if key in table:
            if table[key] == value:
                self.duplicates += 1
            else:
                self.conflicts.append({'key': list(key), 'before': table[key], 'after': value})
        else:
            table[key] = value

    def pytest_collectreport(self, report):
        if report.failed or report.skipped:
            self._retain(self.collection, (report.nodeid,), report.outcome)

    def pytest_collection_finish(self, session):
        self.collection_finished = True

    def pytest_runtest_logstart(self, nodeid, location):
        del location
        self.invocations[nodeid] = self.invocations.get(nodeid, 0)+1
        self.current[nodeid] = self.invocations[nodeid]

    def pytest_runtest_logreport(self, report):
        invocation = self.current.get(report.nodeid, 0)
        key = (report.nodeid, invocation, report.when)
        value = {'outcome': report.outcome, 'wasxfail': hasattr(report, 'wasxfail')}
        if report.outcome not in ('passed', 'failed', 'skipped'):
            self.conflicts.append({'key': list(key), 'unsupported_outcome': report.outcome})
        self._retain(self.reports, key, value)

    def pytest_sessionfinish(self, session, exitstatus):
        if self.run is None:
            return
        counts = dict.fromkeys(COUNT_KEYS, 0)
        counts['collected'] = session.testscollected
        collection_errors = sum(value == 'failed' for value in self.collection.values())
        counts['errors'] = collection_errors
        counts['skipped'] = sum(value == 'skipped' for value in self.collection.values())
        for (_, _, phase), report in self.reports.items():
            outcome, xfail = report['outcome'], report['wasxfail']
            if phase != 'call':
                if outcome == 'failed':
                    counts['errors'] += 1
                elif outcome == 'skipped':
                    counts['xfailed' if xfail else 'skipped'] += 1
            elif xfail:
                if outcome == 'skipped':
                    counts['xfailed'] += 1
                elif outcome == 'passed':
                    counts['xpassed'] += 1
                else:
                    counts['failed'] += 1
            elif outcome in ('passed', 'failed', 'skipped'):
                counts[outcome] += 1
        test_reports = [dict(nodeid=node, invocation=invocation, phase=phase, **value)
                        for (node, invocation, phase), value in self.reports.items()]
        tests = {(node, invocation) for node, invocation, _ in self.reports}
        collect_only = bool(getattr(self.config.option, 'collectonly', False))
        partial = bool(not collect_only and counts['collected'] > len(tests))
        details = {'exitstatus': int(exitstatus), 'collection_errors': collection_errors,
                   'collection_complete': self.collection_finished, 'collect_only': collect_only,
                   'observed_test_invocations': len(tests), 'partial': partial,
                   'duplicate_reports_ignored': self.duplicates,
                   'report_conflicts': self.conflicts, 'test_reports': test_reports,
                   'test_reports_sha256': hashlib.sha256(json.dumps(
                       test_reports, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
        current, self.run = self.run, None
        finish(current, counts, **details)

    def pytest_unconfigure(self, config):
        del config
        if self.run is not None:
            abandon(self.run)


def pytest_configure(config):
    import pytest
    if getattr(config, '_pws_v141_observer', None) is not None:
        return
    # Begin before other startup hooks; finish after their nested runner work.
    pytest.hookimpl(tryfirst=True)(PytestSessionObserver.pytest_sessionstart)
    pytest.hookimpl(trylast=True)(PytestSessionObserver.pytest_sessionfinish)
    observer = PytestSessionObserver(config)
    config._pws_v141_observer = observer
    config.pluginmanager.register(observer, 'pws_v141_session_observer')


def _install_unittest():
    import unittest
    original = unittest.TextTestRunner.run

    def run(self, test):
        identity = begin('django')
        try:
            result = original(self, test)
            failed, errors = len(result.failures), len(result.errors)
            skipped = len(getattr(result, 'skipped', []))
            xfailed = len(getattr(result, 'expectedFailures', []))
            xpassed = len(getattr(result, 'unexpectedSuccesses', []))
            counts = dict(collected=result.testsRun,
                          passed=max(0, result.testsRun-failed-errors-skipped-xfailed-xpassed),
                          failed=failed, errors=errors, skipped=skipped,
                          xfailed=xfailed, xpassed=xpassed)
            finish(identity, counts, exitstatus=int(not result.wasSuccessful()),
                   collection_errors=0, collection_complete=True, partial=False,
                   observed_test_invocations=result.testsRun, report_conflicts=[])
            return result
        finally:
            abandon(identity)
    unittest.TextTestRunner.run = run


def _install_sympy(module):
    cls = getattr(module, 'PyTestReporter', None)
    if cls is None or getattr(cls, '_pws_v141_observed', False):
        return
    original_start, original_finish = cls.start, cls.finish

    def start(self, *args, **kwargs):
        self._pws_v141_run = begin('sympy')
        return original_start(self, *args, **kwargs)

    def finish_reporter(self, *args, **kwargs):
        identity = getattr(self, '_pws_v141_run', None)
        if identity is None:
            # The missing start remains explicit; the parser rejects this finish.
            identity = dict(run_id=secrets.token_hex(16), parent_run_id=None,
                            framework='sympy', pid=os.getpid(), pgid=os.getpgrp())
        try:
            result = original_finish(self, *args, **kwargs)
            counts = dict(collected=None, passed=self._passed, skipped=self._skipped,
                          failed=len(self._failed)+len(getattr(self, '_failed_doctest', [])),
                          errors=len(self._exceptions), xfailed=self._xfailed,
                          xpassed=len(self._xpassed))
            finish(identity, counts, exitstatus=int(bool(counts['failed'] or counts['errors'])),
                   collection_errors=0, collection_complete=True, partial=False,
                   observed_test_invocations=None, report_conflicts=[])
            return result
        finally:
            abandon(identity)
    cls.start, cls.finish = start, finish_reporter
    cls._pws_v141_observed = True


class ObserverLoader:
    def __init__(self, delegate):
        self.delegate = delegate

    def create_module(self, spec):
        create = getattr(self.delegate, 'create_module', None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.delegate.exec_module(module)
        _install_sympy(module)

    def __getattr__(self, name):
        return getattr(self.delegate, name)


class ObserverFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ('sympy.utilities.runtests', 'sympy.testing.runtests'):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and hasattr(spec.loader, 'exec_module'):
            spec.loader = ObserverLoader(spec.loader)
        return spec


def install():
    global _installed
    if _installed:
        return
    _installed = True
    framework = os.environ.get('PWS_TEST_OBSERVER_FRAMEWORK')
    if framework == 'django':
        _install_unittest()
    elif framework == 'sympy':
        sys.meta_path.insert(0, ObserverFinder())
