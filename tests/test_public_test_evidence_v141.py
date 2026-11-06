"""Real nested framework controls and conservative malformed-evidence cases."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import pytest

from proworksim.software_benchmark_public_test_evidence_v141 import (
    execute_public_entry, parse_test_evidence,
)


def run(argv, root, extra=None, timeout=20):
    env = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_PLUGINS': '',
           **(extra or {})}
    # pytester disables the user site in children. This CPU fixture uses the
    # already installed pytest explicitly; no dependency is installed/downloaded.
    env['PYTHONPATH'] = str(Path(pytest.__file__).resolve().parent.parent) + os.pathsep + env.get('PYTHONPATH', '')
    return execute_public_entry({'argv': argv}, root=root, environment=env,
                                timeout_seconds=timeout)


def pytest_run(root, name='test_outer.py', extra=None, args=()):
    return run([sys.executable, '-m', 'pytest', '-q', *args, name], root, extra)


def test_real_pytester_same_process_and_subprocess_keep_outer_result(tmp_path):
    (tmp_path/'test_outer.py').write_text('''pytest_plugins = ["pytester"]
def test_nested(pytester):
    pytester.makepyfile("def test_same_id(): assert False")
    first = pytester.runpytest_inprocess("-q")
    first.assert_outcomes(failed=1)
    second = pytester.runpytest_subprocess("-q")
    second.assert_outcomes(failed=1)
''')
    value = pytest_run(tmp_path)
    assert value['passed'], value['output']
    assert value['counts']['passed'] == 1 and value['counts']['failed'] == 0
    sessions = value['test_evidence']['sessions']
    assert len(sessions) == 3, value
    root = next(row for row in sessions if row['root'])
    children = [row for row in sessions if not row['root']]
    assert len({row['run_id'] for row in sessions}) == 3
    assert all(row['parent_run_id'] == root['run_id'] for row in children)
    assert all(row['counts']['failed'] == 1 for row in children)
    assert {row['pid'] == root['pid'] for row in children} == {True, False}
    child_ids = [[r['nodeid'] for r in row['test_reports'] if r['phase'] == 'call']
                 for row in children]
    assert child_ids[0] == child_ids[1]  # Same test ID, two independent sources.


def test_successful_child_cannot_mask_failed_root(tmp_path):
    (tmp_path/'test_outer.py').write_text('''import pytest
def test_outer(tmp_path):
    child = tmp_path / "test_child.py"
    child.write_text("def test_child(): assert True\\n")
    assert pytest.main(["-q", str(child)]) == 0
    assert False, "the top-level command still fails"
''')
    value = pytest_run(tmp_path)
    assert value['validation_status'] == 'failed' and not value['passed']
    assert value['counts']['failed'] == 1 and value['counts']['passed'] == 0
    assert value['test_evidence']['nested_report_count'] == 1
    child = next(row for row in value['test_evidence']['sessions'] if not row['root'])
    assert child['counts']['passed'] == 1


@pytest.mark.parametrize(('source', 'status'), [
    ('def test_ok(): assert True\n', 'verified'),
    ('print("999 passed")\n', 'no_tests'),
    ('import pytest\n@pytest.mark.skip(reason="fixture")\ndef test_skip(): pass\n', 'all_skipped_or_xfailed'),
    ('def test_bad(): assert False\n', 'failed'),
    ('raise ImportError("synthetic collection failure")\n', 'collection_failed'),
])
def test_real_root_statuses(tmp_path, source, status):
    (tmp_path/'test_outer.py').write_text(source)
    value = pytest_run(tmp_path)
    assert value['validation_status'] == status, value
    assert value['passed'] is (status == 'verified')
    assert value['test_evidence']['root_counts_only']
    assert value['test_evidence']['report_count'] == 1


def test_fail_fast_is_partial_and_never_verified(tmp_path):
    (tmp_path/'test_outer.py').write_text(
        'def test_a(): assert False\ndef test_b(): assert True\ndef test_c(): assert True\n')
    value = pytest_run(tmp_path, args=('-x',))
    assert not value['passed'] and value['validation_status'] == 'failed'
    assert value['test_evidence']['partial'] is True
    assert value['counts']['collected'] == 3 and value['counts']['failed'] == 1


def test_original_sitecustomize_preserved_and_stdout_not_evidence(tmp_path):
    support = tmp_path/'original_hook'
    support.mkdir()
    (support/'sitecustomize.py').write_text('import os\nos.environ["PWS_FIXTURE_ORIGINAL"]="kept"\n')
    (tmp_path/'test_outer.py').write_text(
        'import os\ndef test_original(): assert os.environ["PWS_FIXTURE_ORIGINAL"] == "kept"\n')
    good = pytest_run(tmp_path, extra={'PYTHONPATH': str(support)})
    assert good['passed'], good
    value = run([sys.executable, '-c', 'print("999 passed")'], tmp_path)
    assert value['returncode'] == 0 and not value['passed']
    assert value['validation_status'] == 'unknown_collection'


def test_real_nested_unittest_counts_only_parent(tmp_path):
    tests = tmp_path/'tests'
    tests.mkdir()
    (tests/'runtests.py').write_text('''import unittest, sys
class Inner(unittest.TestCase):
    def test_inner(self): self.fail("intentional nested failure")
class Outer(unittest.TestCase):
    def test_outer(self):
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Inner))
        self.assertEqual(len(result.failures), 1)
result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Outer))
sys.exit(not result.wasSuccessful())
''')
    value = run([sys.executable, 'tests/runtests.py', '--noinput', '--parallel', '1'], tmp_path)
    assert value['passed'] and value['counts']['passed'] == 1, value
    assert len(value['test_evidence']['sessions']) == 2
    assert sum(row['counts']['failed'] for row in value['test_evidence']['sessions']) == 1


def records(run='root', parent=None, pid=10, passed=1, failed=0):
    identity = dict(version='v141-session-bound-framework-observer-r1', token='command',
                    framework='pytest', pgid=10, pid=pid, run_id=run, parent_run_id=parent)
    return [dict(identity, event='start'), dict(identity, event='finish',
        counts=dict(collected=passed+failed, passed=passed, failed=failed, errors=0,
                    skipped=0, xfailed=0, xpassed=0),
        exitstatus=int(bool(failed)), collection_errors=0, collection_complete=True,
        partial=False, report_conflicts=[])]


def parse(rows, **kwargs):
    return parse_test_evidence(('\n'.join(json.dumps(row) for row in rows)+'\n').encode(),
        framework='pytest', token='command', process_group=10,
        returncode=kwargs.get('returncode', 0), timed_out=kwargs.get('timed_out', False))


def test_consistent_record_retransmission_is_deduplicated():
    root = records()
    value = parse([root[0], root[0], root[1], root[1]])
    assert value['passed'] and value['counts']['passed'] == 1
    assert value['test_evidence']['duplicate_journal_records_ignored'] == 2


@pytest.mark.parametrize('kind', [
    'missing_root_finish', 'missing_child_finish', 'orphan', 'multiple_roots',
    'wrong_token', 'wrong_pid', 'conflicting_duplicate', 'child_outside_parent',
    'bad_counts', 'bad_shape', 'no_start', 'conflicting_test_phase', 'missing_collection_count',
])
def test_ambiguous_or_incomplete_evidence_never_passes(kind):
    root, child = records(), records('child', 'root', 20)
    rows = [root[0], child[0], child[1], root[1]]
    if kind == 'missing_root_finish':
        rows.pop()
    elif kind == 'missing_child_finish':
        rows.pop(2)
    elif kind == 'orphan':
        child[0]['parent_run_id'] = child[1]['parent_run_id'] = 'missing'
    elif kind == 'multiple_roots':
        rows = root+records('second')
    elif kind == 'wrong_token':
        child[1]['token'] = 'different-command'
    elif kind == 'wrong_pid':
        root[0]['pid'] = root[1]['pid'] = 22
    elif kind == 'conflicting_duplicate':
        rows.append({**root[1], 'partial': True})
    elif kind == 'child_outside_parent':
        rows = root+child
    elif kind == 'bad_counts':
        root[1]['counts']['passed'] = True
    elif kind == 'bad_shape':
        rows = [True]
    elif kind == 'no_start':
        rows = [root[1]]
    elif kind == 'conflicting_test_phase':
        root[1]['report_conflicts'] = [{'same_test': 'different_outcome'}]
    elif kind == 'missing_collection_count':
        root[1]['counts']['collected'] = None
    value = parse(rows)
    assert not value['passed'] and value['validation_status'] == 'unknown_collection', value


def test_missing_root_collection_completion_is_not_success():
    rows = records()
    rows[1]['collection_complete'] = False
    value = parse(rows)
    assert not value['passed'] and value['validation_status'] == 'unknown_collection'


def test_test_id_dedup_is_scoped_to_run_invocation_and_phase(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]/'tools/public_test_evidence_v141.py'
    spec = importlib.util.spec_from_file_location('fixture_v141_observer', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path/'journal.jsonl'
    report.write_bytes(b'')
    monkeypatch.setenv('PWS_TEST_OBSERVER_REPORT', str(report))
    monkeypatch.setenv('PWS_TEST_OBSERVER_TOKEN', 'fixture')
    monkeypatch.delenv('PWS_TEST_OBSERVER_PARENT_RUN', raising=False)
    observer = module.PytestSessionObserver(SimpleNamespace(option=SimpleNamespace(collectonly=False)))
    session = SimpleNamespace(testscollected=2)
    observer.pytest_sessionstart(session)
    observer.pytest_collection_finish(session)
    item = SimpleNamespace(nodeid='test_file.py::test_x', when='call', outcome='passed')
    observer.pytest_runtest_logstart(item.nodeid, None)
    observer.pytest_runtest_logreport(item)
    observer.pytest_runtest_logreport(item)  # Duplicate delivery of same report.
    observer.pytest_runtest_logstart(item.nodeid, None)  # A real second invocation.
    observer.pytest_runtest_logreport(item)
    observer.pytest_sessionfinish(session, 0)
    finished = json.loads(report.read_text().splitlines()[-1])
    assert finished['counts']['passed'] == 2
    assert finished['duplicate_reports_ignored'] == 1
    assert [r['invocation'] for r in finished['test_reports']] == [1, 2]


def test_timeout_never_uses_stdout_as_success(tmp_path):
    value = run([sys.executable, '-c', 'import time; print("999 passed", flush=True); time.sleep(10)'],
                tmp_path, timeout=.15)
    assert not value['passed'] and value['validation_status'] == 'timed_out'


def test_managed_adapter_preserves_source_and_diagnostics(monkeypatch, tmp_path):
    from proworksim import software_benchmark_public_test_evidence_v141 as bridge
    from proworksim import software_benchmark_managed_actor_v064 as actor
    monkeypatch.setattr(actor, '_reap_private_children', lambda: None)
    fixture = {'passed': False, 'validation_status': 'collection_failed',
        'counts': {'errors': 1}, 'test_evidence': {'source': {'run_id': 'root'}},
        'argv': ['fixture'], 'returncode': 2, 'timed_out': False, 'wall_seconds': 0,
        'output_sha256': 'a'*64, 'output_bytes': 0, 'stdout_utf8_strict': True, 'output': ''}
    monkeypatch.setattr(bridge, 'execute_public_entry', lambda *args, **kwargs: fixture)
    value = bridge.run_public_entry({'timeout_seconds': 10}, root=tmp_path, environment={},
        request={'hard_deadline_monotonic': time.monotonic()+10,
                 'source_reference': {'object_id': 'fixture', 'version_id': 'v1'}},
        candidate_tree_sha256='b'*64)
    assert value['execution']['input_tree_sha256'] == 'b'*64
    assert value['test_evidence']['source']['run_id'] == 'root'
    assert value['verification_diagnostics'][0]['kind'] == 'collection_failed'
