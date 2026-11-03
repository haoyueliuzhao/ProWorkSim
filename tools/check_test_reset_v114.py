"""Reproduce two exact old scoring failures in temporary Git trees, without tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from proworksim import software_benchmark_test_reset_v114 as reset  # noqa: E402
from proworksim import software_benchmark_grading_repairs_v114 as repair  # noqa: E402
from proworksim import software_benchmark_grading_v113 as grading  # noqa: E402
from proworksim.software_benchmark_native_artifact_v054 import decode_native_entry, validate_native_tree  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402

BATCH = ROOT/'runs/software-benchmark-v111/aligned-interface-r1'
SLOTS = {'sphinx-doc__sphinx-10614': 7232, 'pylint-dev__pylint-6528': 7283}
_fixture = None


def audit(event, args):
    if event == 'socket.getaddrinfo' or (event in {'socket.connect', 'socket.bind', 'socket.sendto'}
            and args and getattr(args[0], 'family', None) in (socket.AF_INET, socket.AF_INET6)):
        raise RuntimeError('No network in this local reset control')
    if event == 'subprocess.Popen':
        if (_fixture is None or args[0] not in ('/usr/bin/git', '/bin/bash')
                or not Path(args[2]).resolve().is_relative_to(_fixture)):
            raise RuntimeError('Only local Git/reset commands inside the new CPU fixture are permitted')


sys.addaudithook(audit)


def run(repo, command, *, input=None, check=True):
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_AUTHOR_NAME': 'CPU fixture', 'GIT_AUTHOR_EMAIL': 'cpu@example.invalid',
        'GIT_COMMITTER_NAME': 'CPU fixture', 'GIT_COMMITTER_EMAIL': 'cpu@example.invalid'}
    return subprocess.run(command, cwd=repo, env=environment, input=input,
        capture_output=True, check=check, timeout=30)


def git(repo, *args, **kwargs):
    return run(repo, ['/usr/bin/git', '-c', 'core.autocrlf=false', '-c', 'core.hooksPath=/dev/null', *args], **kwargs)


def materialize(root, bundle):
    validate_native_tree(bundle['files'], bundle['entry_metadata'])
    for name, text in sorted(bundle['files'].items()):
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = bundle['entry_metadata'][name]
        raw = decode_native_entry(name, text, metadata)
        if metadata['kind'] == 'symlink':
            os.symlink(raw, os.fsencode(target))
        else:
            target.write_bytes(raw)
            target.chmod(0o755 if metadata['mode'] == '100755' else 0o644)


def manifest(root):
    values = {}
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name != '.git']
        names = list(files)
        for name in list(directories):
            if (Path(folder)/name).is_symlink():
                directories.remove(name)
                names.append(name)
        for name in names:
            path = Path(folder)/name
            info = path.lstat()
            raw = os.readlink(os.fsencode(path)) if stat.S_ISLNK(info.st_mode) else path.read_bytes()
            values[path.relative_to(root).as_posix()] = {
                'sha256': hashlib.sha256(raw).hexdigest(),
                'mode': '120000' if stat.S_ISLNK(info.st_mode) else '100755' if info.st_mode & 0o111 else '100644'}
    return values


def task_control(row, root):
    slot = SLOTS[row['instance_id']]
    lock_ref = reference(BATCH/'episodes'/str(slot)/'candidate-lock.json')
    lock = json.loads(checked(lock_ref).read_bytes())
    baseline = json.loads(checked(lock['baseline']).read_bytes())
    patch_ref = lock['patch_receipt']['patch']
    patch = checked(patch_ref).read_bytes()
    grading_patch = next((BATCH/'grading'/f'score-{slot}'/'official-output/logs').rglob('patch.diff'))
    assert grading_patch.read_bytes() == patch
    repo = root/str(slot)
    repo.mkdir()
    materialize(repo, baseline)
    git(repo, 'init', '-q')
    git(repo, 'add', '-f', '-A')
    git(repo, 'commit', '-qm', 'exact original complete baseline bytes')
    commit = git(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
    tree = git(repo, 'write-tree').stdout.decode().strip()
    assert tree == lock['patch_receipt']['base_git_tree']
    paths = reset.test_paths(row['test_patch'])
    git(repo, 'apply', '-', input=row['test_patch'].encode())
    expected = {name: item for name, item in manifest(repo).items() if name in paths}
    git(repo, 'reset', '--hard', commit)
    git(repo, 'clean', '-fdx')
    git(repo, 'apply', '--binary', '-', input=patch)
    git(repo, 'add', '-f', '-A')
    assert git(repo, 'write-tree').stdout.decode().strip() == lock['patch_receipt']['candidate_git_tree']
    git(repo, 'reset', '--mixed', 'HEAD')
    non_test = {name: item for name, item in manifest(repo).items() if name not in paths}
    old_line = next(line for line in row['eval_script'].splitlines() if line.startswith('git checkout '))
    old = git(repo, 'checkout', commit, *shlex.split(old_line)[3:], check=False)
    failed_apply = git(repo, 'apply', '--check', '-', input=row['test_patch'].encode(), check=False)
    assert old.returncode != 0 and failed_apply.returncode != 0
    fixed = run(repo, ['/bin/bash', '-c', reset.reset_command(commit, paths)])
    git(repo, 'apply', '-', input=row['test_patch'].encode())
    actual = manifest(repo)
    assert {name: item for name, item in actual.items() if name in paths} == expected
    assert {name: item for name, item in actual.items() if name not in paths} == non_test
    run(repo, ['/bin/bash', '-c', reset.reset_command(commit, paths)])
    assert {name: item for name, item in manifest(repo).items() if name not in paths} == non_test
    assert hashlib.sha256(checked(patch_ref).read_bytes()).hexdigest() == patch_ref['sha256']
    return {'instance_id': row['instance_id'], 'slot_index': slot, 'candidate_lock': lock_ref,
        'original_candidate_patch': patch_ref, 'old_grader_received_identical_patch': True,
        'complete_original_baseline_git_tree_matches': True, 'complete_candidate_git_tree_matches': True,
        'original_checkout_exit_code': old.returncode, 'original_apply_check_exit_code': failed_apply.returncode,
        'original_checkout_error': old.stderr.decode(), 'original_apply_check_error': failed_apply.stderr.decode(),
        'repaired_reset_exit_code': fixed.returncode, 'official_test_patch_sha256': reset.digest(row['test_patch']),
        'exact_official_test_paths': paths,
        'baseline_present_test_paths': sorted(set(paths) & set(baseline['files'])),
        'baseline_absent_test_paths': sorted(set(paths)-set(baseline['files'])),
        'official_test_postimage_equals_clean_baseline_plus_official_patch': True,
        'all_non_test_candidate_entries_unchanged': True, 'non_test_candidate_entries_checked': len(non_test),
        'fixture_commit_substituted_only_for_temporary_git_repository': True,
        'expected_test_postimages': expected, 'official_tests_executed': 0}


def main():
    global _fixture
    dataset = ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json'
    rows = [row for row in json.loads(dataset.read_bytes()) if row['instance_id'] in reset.TASKS]
    assert len(rows) == 2
    spec = importlib.util.spec_from_file_location('v114_reused_pure_spec_control', ROOT/'tools/check_test_reset_v099.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    factory, sources = prior.actual_spec_factory()
    observed = []
    original = grading.scorer(SimpleNamespace(GRADING_ROOT=Path('/unused-cpu-fixture'),
        require_v066_allowed=lambda *_a, **_kw: None), manifest_provider=lambda: {'CPU_fixture': True})
    delegate = SimpleNamespace(make_repaired_run_instance=lambda harness, directory: (
        lambda test_spec, *args, **kwargs: observed.append(test_spec), {'scripted_official_dispatch': True}))
    original.diagnostics = original._score.__globals__['diagnostics'] = delegate
    bound = repair.bind_scorer(original, rows)
    actual = bound._score.__globals__['diagnostics']
    dispatch, provenance = actual.make_repaired_run_instance(SimpleNamespace(make_test_spec=factory), None)
    for row in rows:
        test_spec = factory(row)
        old_script = test_spec.eval_script
        dispatch(test_spec)
        assert test_spec.eval_script == old_script and observed[-1] is not test_spec
        repaired, _ = reset.repair_eval_script({**row, 'eval_script': old_script})
        assert observed[-1].eval_script == repaired
    assert original.diagnostics is delegate and bound._score.__code__ is original._score.__code__
    with tempfile.TemporaryDirectory(prefix='pws-v114-exact-git-control-') as temporary:
        _fixture = Path(temporary).resolve()
        results = [task_control(row, _fixture) for row in rows]
    _fixture = None
    output = ROOT/'artifacts/software-benchmark-v114/test-reset-control-r1/summary.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, {'version': reset.VERSION, 'passed': True, 'tasks': results,
        'actual_scorer_diagnostics_dispatch_exercised': True, 'original_TestSpec_builder_executed': True,
        'unchanged_official_builder_sources': sources, 'transform_provenance': provenance,
        'source': reference(reset.__file__), 'binding_source': reference(repair.__file__),
        'control_source': reference(__file__), 'dataset': reference(dataset),
        'official_tests_executed': 0, 'Docker_operations': 0, 'model_calls': 0,
        'network_connections': 0, 'old_artifacts_changed': False, 'runtime_qualified': False})
    print(json.dumps({'passed': True, 'tasks': len(results), 'summary': str(output)}))


if __name__ == '__main__':
    main()
