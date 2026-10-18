"""Finite CPU contracts: no repository, SDK or model executions."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from proworksim.software_bridge_sources_v052 import (
    evaluation_identity, grade_locked_candidate, lock_final_candidate, ordered_files, ref, write_new,
)
from proworksim.software_calibration_repo_tests_v051 import VERSION as RUNNER_VERSION
from proworksim.storage import digest, json_bytes


class Provider:
    def __init__(self):
        self.authoritative_receipts = []
        self.calls = []
        self.files = {'parse.py': 'VALUE = 1\n', 'test_original.py': '# original readonly test\r\n'}
        self.task = {'module': 'parse', 'nodeids': ['test_original.py::test_value'],
            'source_roots': ['parse.py'], 'config_relative_path': None, 'cpu_python': '/synthetic/python',
            'loopback_fixture': None, 'frozen_test_hashes': {'test_original.py': digest(self.files['test_original.py'].encode())},
            'initial_production_hashes': {'parse.py': digest(self.files['parse.py'].encode())},
            'initial_file_paths': sorted(self.files), 'accepted_new_production_paths': [],
            'bridge_runtime_ref': {'path': '/synthetic/runtime.json', 'sha256': 'synthetic', 'bytes': 1}}

    def build_case(self, case_id):
        return {'files': self.files, 'editable_paths': ['parse.py']}

    def runner_spec(self, case_id):
        return copy.deepcopy(self.task)

    def _backend(self, *, files, task, run_root):
        self.calls.append(run_root)
        run_root = Path(run_root)
        result = {'version': RUNNER_VERSION, 'input_files_sha256': digest(json_bytes(files)),
            'original_nodeids_sha256': hashlib.sha256(json.dumps(task['nodeids'], ensure_ascii=False, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
            'executed': True, 'command_executed': True, 'worker_returncode': 0, 'timed_out': False,
            'source_unchanged': True, 'test_integrity': True, 'frozen_test_files_match': True,
            'unexpected_test_ids': [], 'missing_test_ids': [], 'returncode': 0,
            'tests': [{'nodeid': task['nodeids'][0], 'outcome': 'passed'}]}
        write_new(run_root / 'result.json', result)
        binding = {'evaluation_identity': evaluation_identity(files, task), 'r3_result': ref(run_root / 'result.json'),
                   'runtime_manifest': task['bridge_runtime_ref']}
        write_new(run_root / 'bridge-binding.json', binding)
        return {**result, 'bridge_binding': ref(run_root / 'bridge-binding.json')}


def test_terminal_lock_preserves_raw_and_production_deletion_and_rejects_reselection(tmp_path):
    provider = Provider()
    candidate = {'new_helper.py': 'def value(): return 2\n', 'test_original.py': '# tampered',
                 'conftest.py': 'raise RuntimeError()\n', 'pytest.ini': '[pytest]\n'}
    lock = lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=candidate, run_root=tmp_path / 'lock')
    value = json.loads(Path(lock['path']).read_bytes())
    raw = json.loads(Path(value['raw_candidate']['path']).read_bytes())
    grading = json.loads(Path(value['grading_files']['path']).read_bytes())
    assert raw == candidate and 'parse.py' not in grading and 'new_helper.py' in grading
    assert grading['test_original.py'] == provider.files['test_original.py']
    assert 'conftest.py' not in grading and 'pytest.ini' not in grading and provider.calls == []
    with pytest.raises(FileExistsError):
        lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=candidate, run_root=tmp_path / 'lock')
    provider.authoritative_receipts.append({'prior': 'synthetic scoring'})
    with pytest.raises(ValueError):
        lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=candidate, run_root=tmp_path / 'late-lock')
    # Reordering a complete serialized map does not create a new tree identity;
    # changing interpreter/config/test identity does.
    assert evaluation_identity(provider.files, provider.task) == evaluation_identity(dict(reversed(list(provider.files.items()))), provider.task)
    different = {**provider.task, 'cpu_python': '/different/python'}
    assert evaluation_identity(provider.files, provider.task) != evaluation_identity(provider.files, different)


def test_exact_fixed_receipt_reuse_and_different_tree_once(tmp_path):
    provider = Provider()
    files = ordered_files(provider.files)
    lock = lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=files, run_root=tmp_path / 'same')
    first = provider._backend(files=files, task=provider.task, run_root=tmp_path / 'fixed')
    fixed = {'submitted': True, 'evaluation_identity': evaluation_identity(files, provider.task),
        'authoritative_runner_receipt': ref(tmp_path / 'fixed/result.json'), 'bridge_binding': first['bridge_binding']}
    reused = grade_locked_candidate(provider=provider, lock_reference=lock, fixed_assessment=fixed)
    assert reused['R_code'] == 1 and reused['Q_task'] == 1
    assert reused['new_test_executions'] == reused['new_evaluation_attempts'] == 0
    assert reused['reused_same_fixed_tree_assessment'] and len(provider.calls) == 1
    with pytest.raises(ValueError):
        grade_locked_candidate(provider=provider, lock_reference=lock, fixed_assessment=fixed)
    changed = {**files, 'parse.py': 'VALUE = 2\n'}
    new_lock = lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=changed, run_root=tmp_path / 'different')
    distinct = grade_locked_candidate(provider=provider, lock_reference=new_lock, fixed_assessment=fixed)
    assert distinct['new_test_executions'] == distinct['new_evaluation_attempts'] == 1
    assert not distinct['reused_same_fixed_tree_assessment'] and len(provider.calls) == 2
    # Tampering with an already locked source cannot reach a test invocation.
    bad_lock = lock_final_candidate(provider=provider, task_id='synthetic', candidate_files=files, run_root=tmp_path / 'tampered')
    bad = json.loads(Path(bad_lock['path']).read_bytes())
    Path(bad['grading_files']['path']).write_text('{}')
    with pytest.raises(ValueError):
        grade_locked_candidate(provider=provider, lock_reference=bad_lock)
    assert len(provider.calls) == 2
