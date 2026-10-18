"""v052 shared CAL2 source/engine binding and one locked final code candidate.

The v051 P/raw model-visible provider contract remains unchanged. All new fields
are host evidence. The actual child is the immutable final r3 stdlib-only runner.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from .repository_sources_v051 import RepositorySources as OriginalSources
from .software_calibration_native_grade_v051 import canonical_grading_tree, _outcomes
from .storage import digest, json_bytes

VERSION = 'v052-shared-repository-test-binding-v1'
TASK_IDS = tuple(f'cal2-{repo}-{number}' for repo in ('boltons', 'parse', 'xmltodict') for number in (1, 2))
RUNNER_SHA = '68337e5ceb8ad4fffc691c4fcfd71937e6af8c886a2d80a24074d1abacb1644e'
HELPER_SHA = '10ca8ef7a301be723f4acda390020fe87f3e8b0886ea9de619ac9366aea14f48'
TARGETS = ('boltons', 'parse', 'xmltodict')


def ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'sha256': digest(data), 'bytes': len(data)}


def checked(reference):
    path = Path(reference['path'])
    if not path.is_absolute() or ref(path) != reference:
        raise ValueError('An intact absolute frozen reference is required')
    return path


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(json_bytes(value))


def ordered_files(files):
    return {name: files[name] for name in sorted(files)}


def tree_manifest(root):
    root = Path(root).resolve()
    return {str(path.relative_to(root)): {'sha256': digest(path.read_bytes()), 'symlink': str(path.resolve()) if path.is_symlink() else None}
            for path in sorted(root.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}


def runtime_binding(runtime_path):
    path = Path(runtime_path).resolve()
    runtime = json.loads(path.read_bytes())
    if runtime.get('version') != 'v052-final-r3-test-runtime-v1' or runtime.get('fixture_only') is not False:
        raise ValueError('Declare the final shared formal CPU runtime')
    if runtime['runner']['sha256'] != RUNNER_SHA or runtime['shell_helper']['sha256'] != HELPER_SHA:
        raise ValueError('Only the immutable final r3 child and socket/isolation implementation are admitted')
    checked(runtime['runner'])
    checked(runtime['shell_helper'])
    checked(runtime['python_executable'])
    if Path(runtime['shell_helper']['path']).parent != Path(runtime['runner']['path']).parent:
        raise ValueError('The r3 child must load its own frozen sibling helper')
    for root, expected in runtime['runtime_file_trees'].items():
        if tree_manifest(root) != expected:
            raise ValueError('Frozen interpreter/dependency source tree changed: ' + root)
    for site in runtime['site_packages']:
        for target in TARGETS:
            if (Path(site) / target).exists() or (Path(site) / (target + '.py')).exists():
                raise ValueError('A correct CAL2 target package cannot exist in the candidate interpreter')
    return runtime, ref(path)


def evaluation_identity(files, task):
    """Identity precedes results, and is independent of endpoint name/labels."""
    keys = ('nodeids', 'module', 'config_relative_path', 'cpu_python', 'loopback_fixture',
            'source_roots', 'frozen_test_hashes', 'initial_production_hashes', 'initial_file_paths',
            'accepted_new_production_paths', 'bridge_runtime_ref')
    payload = {'files': ordered_files(files), 'task': {key: task.get(key) for key in keys},
               'resource_policy': {'wall_seconds': 60, 'cpu_seconds': 55, 'memory_bytes': 4294967296,
                   'file_bytes': 8388608, 'uid_thread_margin': 32},
               'worktree_path_rule': '/tmp/v051c/<decimal_time_ns>', 'engine': RUNNER_SHA, 'helper': HELPER_SHA}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def run_repository_tests(*, files, task, run_root):
    """The sole entry shared by PS1, OH terminal qualification and final code."""
    runtime_path = checked(task['bridge_runtime_ref'])
    runtime, runtime_ref = runtime_binding(runtime_path)
    if task['cpu_python'] != runtime['python_invocation']:
        raise ValueError('The shared frozen interpreter invocation cannot be replaced')
    files = ordered_files(files)
    source = checked(runtime['runner'])
    spec = importlib.util.spec_from_file_location('v052_frozen_r3_repository_runner', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    execution = module.run_repository_tests(files=files, task=task, run_root=run_root)
    # Retain the underlying original result without rewriting its fields.
    result_ref = ref(Path(run_root) / 'result.json')
    proof = {'version': VERSION, 'execution_identity': evaluation_identity(files, task),
        'runtime_manifest': runtime_ref, 'r3_result': result_ref,
        'runner': runtime['runner'], 'shell_helper': runtime['shell_helper'],
        'input_files_sha256': digest(json_bytes(files)),
        'candidate_import_basis': {'fresh_isolated_child': True, 'candidate_root_and_src_prepend': True,
            'target_packages_absent_from_frozen_site_packages': True,
            'reference_trees_not_in_filesystem_allowlist': True,
            'scope': 'Source-bound cold interpreter/sys.path/allowlist proof, not an invented target __file__ observation'},
        'original_result_modified': False}
    write_new(Path(run_root) / 'bridge-binding.json', proof)
    return {**execution, 'bridge_binding': ref(Path(run_root) / 'bridge-binding.json'),
            'evaluation_identity': proof['execution_identity']}


class RepositorySources(OriginalSources):
    """Keep P/raw observation contract; bind new host-only runtime/terminal data."""
    def __init__(self, source_root, *, runtime_manifest, expected_manifest_sha256=None, runner=None):
        self.runtime, self.runtime_ref = runtime_binding(runtime_manifest)
        self._backend = runner or run_repository_tests
        self._authoritative = False
        self.authoritative_receipts = []
        super().__init__(source_root, runner=self._run, expected_manifest_sha256=expected_manifest_sha256)
        if self.case_ids != TASK_IDS or self.cpu_python != self.runtime['python_invocation']:
            raise ValueError('Retain the original six CAL2 tasks and shared CPU invocation')

    def runner_spec(self, case_id):
        task = super().runner_spec(case_id)
        task.update(bridge_runtime_ref=self.runtime_ref, initial_file_paths=sorted(self._entry(case_id)['files']),
                    accepted_new_production_paths=[])
        return task

    def _run(self, *, files, task, run_root):
        files = ordered_files(files)
        execution = self._backend(files=files, task=task, run_root=run_root)
        self._last_execution_binding = {'evaluation_identity': evaluation_identity(files, task),
            'authoritative_runner_receipt': ref(Path(run_root) / 'result.json'),
            'bridge_binding': execution.get('bridge_binding')}
        if self._authoritative:
            self.authoritative_receipts.append({'identity': evaluation_identity(files, task),
                'execution': copy.deepcopy(execution), 'source': ref(Path(run_root) / 'result.json')})
        return execution

    def _execute(self, case_id, files, *, run_root):
        tests, execution = super()._execute(case_id, ordered_files(files), run_root=run_root)
        execution.update(copy.deepcopy(self._last_execution_binding))
        return tests, execution

    def assess_files(self, case_id, files, *, run_root):
        previous, self._authoritative = self._authoritative, True
        try:
            result = super().assess_files(case_id, files, run_root=run_root)
            result.update(copy.deepcopy(self._last_execution_binding))
            return result
        finally:
            self._authoritative = previous


def lock_final_candidate(*, provider, task_id, candidate_files, run_root):
    """Call at episode close before evaluating either fixed or terminal tree."""
    if provider.authoritative_receipts:
        raise ValueError('Lock the sole terminal candidate before the fixed submission is scored')
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    case, task = provider.build_case(task_id), provider.runner_spec(task_id)
    raw = ordered_files(candidate_files)
    files, canonical = canonical_grading_tree(case['files'], case['editable_paths'], raw, module=task['module'])
    files = ordered_files(files)
    canonical = {**canonical, 'version': VERSION, 'grading_files_sha256': digest(json_bytes(files)),
                 'scope': 'v052 sole final production tree; original readonly tests/config/support restored, legitimate production additions/deletions retained'}
    task.update(initial_file_paths=sorted(case['files']), accepted_new_production_paths=canonical['accepted_new_production_paths'])
    write_new(root / 'raw-candidate-files.json', raw)
    write_new(root / 'grading-files.json', files)
    write_new(root / 'canonical-tree.json', canonical)
    write_new(root / 'task.json', task)
    lock = {'version': 'v052-final-candidate-lock-v1', 'task_id': task_id, 'endpoint': 'R_code',
        'raw_candidate': ref(root / 'raw-candidate-files.json'), 'grading_files': ref(root / 'grading-files.json'),
        'canonical_tree': ref(root / 'canonical-tree.json'), 'task': ref(root / 'task.json'),
        'execution_identity': evaluation_identity(files, task), 'lock_before_scoring_required': True,
        'candidate_selection_after_scoring': False}
    write_new(root / 'lock.json', lock)
    return ref(root / 'lock.json')


def grade_locked_candidate(*, provider, lock_reference, fixed_assessment=None):
    lock_path = checked(lock_reference)
    lock = json.loads(lock_path.read_bytes())
    root = lock_path.parent
    if lock.get('version') != 'v052-final-candidate-lock-v1' or (root / 'assessment.json').exists() or (root / 'entered.json').exists():
        raise ValueError('A locked terminal candidate is assessed at most once; never select another after scoring')
    files = json.loads(checked(lock['grading_files']).read_bytes())
    task = json.loads(checked(lock['task']).read_bytes())
    checked(lock['raw_candidate'])
    checked(lock['canonical_tree'])
    identity = evaluation_identity(files, task)
    if identity != lock['execution_identity'] or task != {**provider.runner_spec(lock['task_id']),
            'accepted_new_production_paths': task['accepted_new_production_paths']}:
        raise ValueError('Candidate or current shared evaluation identity changed after lock')
    write_new(root / 'entered.json', {'version': VERSION, 'identity': identity, 'automatic_retry': False})
    reused = bool(fixed_assessment and fixed_assessment.get('submitted') is True
                  and fixed_assessment.get('evaluation_identity') == identity)
    if reused:
        reused_source = fixed_assessment['authoritative_runner_receipt']
        execution = json.loads(checked(reused_source).read_bytes())
        binding = json.loads(checked(fixed_assessment['bridge_binding']).read_bytes())
        if (binding['execution_identity'] != identity or binding['r3_result'] != reused_source
                or binding['runtime_manifest'] != task['bridge_runtime_ref']):
            raise ValueError('Same-tree reuse requires the full frozen evaluation binding')
    else:
        execution = provider._backend(files=files, task=task, run_root=root / 'execution')
        reused_source = None
    score = _outcomes(execution, files=files, task=task)
    result = {'version': VERSION, 'task_id': lock['task_id'], 'endpoint': 'terminal_working_tree_code_correctness',
        'lock': lock_reference, **score, 'execution': execution, 'same_identity_authoritative_receipt_reused': reused_source,
        'host_final_test_executions': int(not reused and execution.get('command_executed') is True),
        'host_final_evaluation_attempts': 0 if reused else 1,
        'new_evaluation_attempts': 0 if reused else 1,
        'new_test_executions': int(not reused and execution.get('command_executed') is True),
        'fixed_submission_present': bool(fixed_assessment and fixed_assessment.get('submitted')),
        'reused_same_fixed_tree_assessment': reused, 'fixed_submission_R_unchanged': True,
        'files_sha256': digest(json_bytes(files)), 'observed_pass_fraction': score['Q_task'],
        'assessment': {'executed': score['executed'], 'passed': score['R_code'] == 1 if score['executed'] else None,
            'evaluation_identity': identity, 'independent_acceptance': {'checks': score['checks'], 'execution': execution}},
        'new_model_calls': 0, 'old_HOLD_candidate': False}
    write_new(root / 'assessment.json', result)
    return result


def run_native_public_tests(*, provider, task_id, candidate_files, run_root):
    """OH's disclosed bridge_run_tests command: same original-test executor.

    This is a public test opportunity, not a terminal candidate selection or a
    reusable fixed-delivery assessment. Native arbitrary shell commands remain
    separately logged and are not declared equivalent to this command.
    """
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    case, task = provider.build_case(task_id), provider.runner_spec(task_id)
    files, canonical = canonical_grading_tree(case['files'], case['editable_paths'], candidate_files, module=task['module'])
    files = ordered_files(files)
    task.update(initial_file_paths=sorted(case['files']), accepted_new_production_paths=canonical['accepted_new_production_paths'])
    write_new(root / 'raw-candidate.json', ordered_files(candidate_files))
    write_new(root / 'grading-files.json', files)
    write_new(root / 'canonical-tree.json', {**canonical, 'grading_files_sha256': digest(json_bytes(files))})
    return provider._backend(files=files, task=task, run_root=root / 'execution')
