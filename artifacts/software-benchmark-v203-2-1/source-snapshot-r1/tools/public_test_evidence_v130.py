"""Process-local framework observers; never infer test counts from stdout.

This stdlib helper is copied into a temporary directory for a single command.
Same-UID test code can access it; this is not an anti-forgery security boundary.
Its sitecustomize hook also reaches SymPy's normal
hash-randomization subprocess. It does not change argv, seeds, or test results.
"""
import importlib.machinery
import json
import os
import sys

VERSION = 'v130-public-framework-count-observer-r1'
_installed = False
_pytest_reports = {}
_pytest_collection_errors = 0
_pytest_collection_skips = 0


def emit(framework, counts):
    path = os.environ.get('PWS_TEST_OBSERVER_REPORT')
    token = os.environ.get('PWS_TEST_OBSERVER_TOKEN')
    if not path or not token:
        return
    row = {'version': VERSION, 'token': token, 'framework': framework,
           'pid': os.getpid(), 'pgid': os.getpgrp(), 'counts': counts}
    raw = (json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


def pytest_collectreport(report):
    global _pytest_collection_errors, _pytest_collection_skips
    if report.failed:
        _pytest_collection_errors += 1
    elif report.skipped:
        _pytest_collection_skips += 1


def pytest_runtest_logreport(report):
    _pytest_reports[(report.nodeid, report.when)] = report


def pytest_sessionfinish(session, exitstatus):
    del exitstatus
    counts = dict(collected=session.testscollected, passed=0, failed=0,
                  errors=_pytest_collection_errors, skipped=_pytest_collection_skips,
                  xfailed=0, xpassed=0)
    for (_nodeid, when), report in _pytest_reports.items():
        if when != 'call':
            if report.failed:
                counts['errors'] += 1
            elif report.skipped:
                counts['skipped'] += 1
            continue
        if getattr(report, 'wasxfail', None) is not None:
            counts['xfailed' if report.skipped else 'xpassed'] += 1
        elif report.passed:
            counts['passed'] += 1
        elif report.failed:
            counts['failed'] += 1
        elif report.skipped:
            counts['skipped'] += 1
    emit('pytest', counts)


def _install_unittest():
    import unittest
    original = unittest.TextTestRunner.run

    def run(self, test):
        result = original(self, test)
        failed = len(result.failures)
        errors = len(result.errors)
        skipped = len(getattr(result, 'skipped', []))
        xfailed = len(getattr(result, 'expectedFailures', []))
        xpassed = len(getattr(result, 'unexpectedSuccesses', []))
        emit('django', dict(collected=result.testsRun,
            passed=result.testsRun-failed-errors-skipped-xfailed-xpassed,
            failed=failed, errors=errors, skipped=skipped, xfailed=xfailed, xpassed=xpassed))
        return result

    unittest.TextTestRunner.run = run


def _install_sympy(module):
    cls = getattr(module, 'PyTestReporter', None)
    if cls is None or getattr(cls, '_pws_v130_observed', False):
        return
    original = cls.finish

    def finish(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        counts = dict(collected=None, passed=self._passed, skipped=self._skipped,
            failed=len(self._failed)+len(getattr(self, '_failed_doctest', [])),
            errors=len(self._exceptions), xfailed=self._xfailed, xpassed=len(self._xpassed))
        emit('sympy', counts)
        return result

    cls.finish = finish
    cls._pws_v130_observed = True


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
