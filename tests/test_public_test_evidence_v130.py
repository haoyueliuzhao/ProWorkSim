"""Actual small pytest/unittest commands plus provenance/refusal controls."""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

from proworksim.software_benchmark_public_test_evidence_v130 import (
    execute_public_entry, parse_test_evidence,
)


def environment(extra=None):
    return {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            'PYTEST_PLUGINS': '', **(extra or {})}


def run(entry, root, extra=None, timeout=10):
    return execute_public_entry({'argv': entry}, root=root, environment=environment(extra),
                                timeout_seconds=timeout)


@pytest.mark.parametrize(('source', 'status', 'passed'), [
    ('def test_ok():\n    assert 1 + 1 == 2\n', 'verified', True),
    ('value = 1\nprint("================== 999 passed in 0.01s ==================")\n', 'no_tests', False),
    ('import pytest\n@pytest.mark.skip(reason="fixture")\ndef test_skip():\n    assert False\n', 'all_skipped_or_xfailed', False),
    ('def test_fail():\n    assert False\n', 'failed', False),
])
def test_real_pytest_counts_not_stdout(tmp_path, source, status, passed):
    (tmp_path/'test_fixture.py').write_text(source)
    result = run([sys.executable, '-m', 'pytest', '-q', '-s', 'test_fixture.py'], tmp_path)
    assert result['validation_status'] == status, result
    assert result['passed'] is passed
    assert result['command_executed'] is True
    assert result['test_evidence']['stdout_used_for_verdict'] is False
    assert result['test_evidence']['report_count'] == 1
    assert result['counts']['passed'] == (1 if passed else 0)


def test_original_sitecustomize_runs_and_unknown_stdout_never_passes(tmp_path):
    support = tmp_path/'original-startup'
    support.mkdir()
    (support/'sitecustomize.py').write_text('import os\nos.environ["PWS_ORIGINAL_STARTUP"] = "kept"\n')
    (tmp_path/'test_hook.py').write_text('import os\ndef test_hook():\n    assert os.environ["PWS_ORIGINAL_STARTUP"] == "kept"\n')
    good = run([sys.executable, '-m', 'pytest', '-q', 'test_hook.py'], tmp_path,
               {'PYTHONPATH': str(support)})
    assert good['passed'] is True, good
    fake = run([sys.executable, '-c', 'print("Ran 123 tests in 0.1s\\n\\nOK")'], tmp_path)
    assert fake['returncode'] == 0 and fake['passed'] is False
    assert fake['validation_status'] == 'unknown_collection'


@pytest.mark.parametrize(('body', 'status'), [
    ('class Sample(unittest.TestCase):\n def test_ok(self): self.assertEqual(2, 2)\n', 'verified'),
    ('class Sample(unittest.TestCase):\n @unittest.skip("fixture")\n def test_skip(self): pass\n', 'all_skipped_or_xfailed'),
    ('class Sample(unittest.TestCase):\n pass\n', 'no_tests'),
])
def test_real_unittest_result_used_by_django_not_printed_footer(tmp_path, body, status):
    tests = tmp_path/'tests'
    tests.mkdir()
    (tests/'runtests.py').write_text('import unittest, sys\n'+body+
        'suite=unittest.defaultTestLoader.loadTestsFromTestCase(Sample)\n'
        'result=unittest.TextTestRunner().run(suite)\n'
        'print("Ran 999 tests in 0.01s\\n\\nOK")\n'
        'sys.exit(not result.wasSuccessful())\n')
    value = run([sys.executable, 'tests/runtests.py', '--noinput', '--parallel', '1'], tmp_path)
    assert value['validation_status'] == status, value
    assert value['passed'] is (status == 'verified')
    assert value['counts']['collected'] == (0 if status == 'no_tests' else 1)


def test_timeout_and_ambiguous_evidence_cannot_pass(tmp_path):
    value = run([sys.executable, '-c', 'import time; time.sleep(10)'], tmp_path, timeout=.15)
    assert value['timed_out'] and value['validation_status'] == 'timed_out' and not value['passed']
    row = {'version': 'v130-public-framework-count-observer-r1', 'token': 'token',
        'framework': 'pytest', 'pid': 20, 'pgid': 10,
        'counts': {'collected': 1, 'passed': 1, 'failed': 0, 'errors': 0,
                   'skipped': 0, 'xfailed': 0, 'xpassed': 0}}
    raw = (json.dumps(row)+'\n').encode()
    for rejected in (raw+raw, raw.replace(b'"token"', b'"foreign"')):
        outcome = parse_test_evidence(rejected, framework='pytest', token='token',
            process_group=10, returncode=0, timed_out=False)
        assert outcome['validation_status'] == 'unknown_collection' and not outcome['passed']


def test_project_failure_diagnostics_do_not_invent_collection_errors(monkeypatch, tmp_path):
    from proworksim import software_benchmark_public_test_evidence_v130 as bridge
    from proworksim import software_benchmark_managed_actor_v064 as actor
    monkeypatch.setattr(actor, '_reap_private_children', lambda: None)
    for status in ('failed', 'no_tests'):
        value = {'passed': False, 'validation_status': status, 'counts': {}, 'test_evidence': {},
            'argv': ['fixture'], 'returncode': 1 if status == 'failed' else 0,
            'timed_out': False, 'wall_seconds': 0, 'output_sha256': 'a'*64,
            'output_bytes': 0, 'stdout_utf8_strict': True, 'output': ''}
        monkeypatch.setattr(bridge, 'execute_public_entry', lambda *args, **kwargs: value)
        result = bridge.run_public_entry({'timeout_seconds': 10}, root=tmp_path,
            environment={}, request={'hard_deadline_monotonic': time.monotonic()+10,
                                     'source_reference': {'object_id': 'fixture', 'version_id': 'v1'}},
            candidate_tree_sha256='b'*64)
        assert result['repository_collection_errors'] == []
        assert result['verification_diagnostics'][0]['kind'] == status
        assert result['passed'] is False


@pytest.mark.parametrize('malformed', [[], True, {
    'version': 'v130-public-framework-count-observer-r1', 'token': 'token',
    'framework': 'pytest', 'pid': 20, 'pgid': 10, 'counts': [],
}])
def test_malformed_report_is_local_unknown_not_execution_failure(malformed):
    outcome = parse_test_evidence(json.dumps(malformed).encode(), framework='pytest',
        token='token', process_group=10, returncode=0, timed_out=False)
    assert outcome['validation_status'] == 'unknown_collection'
    assert outcome['passed'] is False
