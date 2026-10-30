"""CPU-only original-patch/preimage Git controls; never execute official tests."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim import software_benchmark_test_reset_v099 as repair  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402


def git(repo, *args, input=None, check=True):
    env = {**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_AUTHOR_NAME': 'CPU fixture', 'GIT_AUTHOR_EMAIL': 'cpu@example.invalid',
           'GIT_COMMITTER_NAME': 'CPU fixture', 'GIT_COMMITTER_EMAIL': 'cpu@example.invalid'}
    return subprocess.run(['git', *args], cwd=repo, env=env, input=input,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def write(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode())


def manifest(repo, names):
    values = {}
    for name in names:
        path = repo / name
        values[name] = ({'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'mode': path.stat().st_mode & 0o777} if path.exists() else None)
    return values


def actual_spec_factory():
    """Execute only original pure TestSpec builder definitions, avoiding SDK imports."""
    site = ROOT / 'runs/software-benchmark-v054/scorer-venv/lib/python3.12/site-packages/swebench'
    spec = importlib.util.spec_from_file_location('v099_original_swebench_types', site / 'types.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    constants = ast.parse((site / 'harness/constants/__init__.py').read_bytes())
    wanted = {'END_TEST_OUTPUT', 'TEST_EXIT_CODE', 'TEST_EXIT_CODE_VAR'}
    env = {'TestSpec': module.TestSpec, 'json': json}
    for node in constants.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<original constants>', 'exec'), env)
    tree = ast.parse((site / 'harness/utils.py').read_bytes())
    names = {'parse_eval_script', 'record_test_exit_code', '_parse_image_assets', 'make_test_spec'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == 4
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<original pure TestSpec builder>', 'exec'), env)
    return env['make_test_spec'], [reference(site / 'types.py'), reference(site / 'harness/utils.py'),
                                 reference(site / 'harness/constants/__init__.py')]


def task_control(row, slot, root):
    episode = ROOT / 'runs/software-benchmark-v066/v064-continuation-r3/episodes' / str(slot)
    request = json.loads((episode.parent.parent / 'grading' / ('score-' + str(slot)) / 'request.json').read_bytes())
    lock = json.loads(checked(request['candidate_lock']).read_bytes())
    before = json.loads(checked(lock['baseline']).read_bytes())['files']
    candidate = json.loads(checked(lock['candidate']).read_bytes())['files']
    paths = repair.test_paths(row['test_patch'])
    # Include every changed non-test textual file from the original candidate,
    # not only a fabricated sentinel. Other unchanged paths are outside this
    # fixture projection; the reset command can touch only the fixed whitelist.
    other = sorted(name for name in set(before) | set(candidate)
                   if name not in paths and before.get(name) != candidate.get(name))
    repo = root / str(slot)
    repo.mkdir()
    git(repo, 'init', '-q')
    for name in paths + other:
        if name in before:
            write(repo, name, before[name])
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'actual original preimage projection')
    commit = git(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
    git(repo, 'apply', '-', input=row['test_patch'].encode())
    expected = manifest(repo, paths)
    git(repo, 'reset', '--hard', commit)
    git(repo, 'clean', '-fd')
    for name in paths + other:
        if name in candidate:
            write(repo, name, candidate[name])
        elif (repo / name).exists():
            (repo / name).unlink()
    non_test_before = manifest(repo, other)
    old_reset = next(line for line in row['eval_script'].splitlines() if line.startswith('git checkout '))
    original_paths = shlex.split(old_reset)[3:]
    old = git(repo, 'checkout', commit, *original_paths, check=False)
    old_apply = git(repo, 'apply', '--check', '-', input=row['test_patch'].encode(), check=False)
    assert old.returncode != 0 and old_apply.returncode != 0, 'Actual old failure was not reproduced'
    fixed = subprocess.run(['/bin/bash', '-c', repair.reset_command(commit, paths)], cwd=repo,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    git(repo, 'apply', '-', input=row['test_patch'].encode())
    assert manifest(repo, paths) == expected
    assert manifest(repo, other) == non_test_before
    # Also exercise the final reset: official postimages/new targets disappear
    # or return to baseline, without touching candidate non-test content.
    subprocess.run(['/bin/bash', '-c', repair.reset_command(commit, paths)], cwd=repo,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    assert manifest(repo, other) == non_test_before
    for name in paths:
        assert ((repo / name).read_bytes() if (repo / name).exists() else None) == (
            before[name].encode() if name in before else None)
    return {'slot_index': slot, 'instance_id': row['instance_id'], 'baseline': lock['baseline'],
        'original_candidate': lock['candidate'], 'candidate_patch': lock['patch_receipt']['patch'],
        'fixture_kind': 'isolated Git repo with exact original test preimages and changed text-file projection',
        'official_test_patch_sha256': repair.digest(row['test_patch']), 'test_paths': paths,
        'old_checkout_returncode': old.returncode, 'old_apply_check_returncode': old_apply.returncode,
        'old_checkout_error': old.stderr.decode(), 'old_apply_error': old_apply.stderr.decode(),
        'repair_reset_returncode': fixed.returncode, 'official_test_postimage_equals_clean_baseline_plus_patch': True,
        'post_test_reset_equals_original_baseline_paths': True,
        'candidate_non_test_text_files_checked': len(other), 'candidate_non_test_text_files_unchanged': True,
        'expected_test_manifest': expected, 'new_model_calls': 0, 'official_tests_executed': 0}


def main():
    dataset = ROOT / 'artifacts/software-benchmark-v054/source/trusted-evaluation.json'
    rows = [r for r in json.loads(dataset.read_bytes()) if r['instance_id'] in repair.TASKS]
    assert len(rows) == 2
    factory, sources = actual_spec_factory()
    observed = []
    delegate = SimpleNamespace(make_repaired_run_instance=lambda harness, directory:
        (lambda spec, *args, **kw: observed.append(spec), {'original_official_dispatch': True}))
    adapter = repair.diagnostics_adapter(delegate, rows)
    dispatch, provenance = adapter.make_repaired_run_instance(SimpleNamespace(make_test_spec=factory), None)
    for row in rows:
        spec = factory(row)
        old_script = spec.eval_script
        dispatch(spec)
        assert spec.eval_script == old_script
        assert observed[-1] is not spec and observed[-1].eval_script != old_script
        assert 'SWEB_TEST_EXIT_CODE' in observed[-1].eval_script or 'TEST_EXIT_CODE' in observed[-1].eval_script
    with tempfile.TemporaryDirectory(prefix='pws-v099-git-control-') as temp:
        results = [task_control(row, 1675 if row['instance_id'].startswith('sphinx') else 5530, Path(temp)) for row in rows]
    destination = ROOT / 'artifacts/software-benchmark-v099/test-reset-control-r1/summary.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_new(destination, {'version': repair.VERSION, 'CPU_controls_passed': True,
        'original_TestSpec_and_pure_builder_executed': True, 'TestSpec_property_adapter_passed': True,
        'installed_harness_modified': False, 'source': reference(repair.__file__), 'control_source': reference(__file__),
        'official_builder_sources': sources, 'dataset': reference(dataset), 'transform_provenance': provenance,
        'tasks': results, 'Docker_operations': 0, 'model_calls': 0, 'network_connections': 0,
        'original_artifacts_changed': False, 'runtime_qualified': False})
    print(json.dumps({'passed': True, 'tasks': len(results), 'summary': str(destination)}))


if __name__ == '__main__':
    main()
