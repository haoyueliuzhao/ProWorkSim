from pathlib import Path
import subprocess

import pytest

from proworksim import software_benchmark_test_reset_v099 as reset


def git(root, *args):
    return subprocess.run(['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                           *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def fixture(root):
    git(root, 'init', '-q')
    (root / 'tests').mkdir()
    (root / 'tests/existing.py').write_bytes(b'original test\n')
    (root / 'production.py').write_bytes(b'original code\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'baseline')
    return git(root, 'rev-parse', 'HEAD').stdout.decode().strip()


def run_reset(root, commit):
    return subprocess.run(['/bin/bash', '-c', reset.reset_command(commit,
        ['tests/existing.py', 'tests/new.py'])], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_exact_new_target_residue_removed_and_production_byte_preserved(tmp_path):
    commit = fixture(tmp_path)
    (tmp_path / 'tests/existing.py').write_bytes(b'model changed test\n')
    (tmp_path / 'tests/new.py').write_bytes(b'conflicting preexisting candidate artifact\n')
    (tmp_path / 'production.py').write_bytes(b'unique candidate code\n')
    assert run_reset(tmp_path, commit).returncode == 0
    assert (tmp_path / 'tests/existing.py').read_bytes() == b'original test\n'
    assert not (tmp_path / 'tests/new.py').exists()
    assert (tmp_path / 'production.py').read_bytes() == b'unique candidate code\n'


def test_symlink_parent_and_directory_target_fail_without_recursive_deletion(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    commit = fixture(repo)
    (repo / 'tests/existing.py').unlink()
    (repo / 'tests').rmdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'existing.py').write_bytes(b'outside untouched\n')
    (repo / 'tests').symlink_to(outside, target_is_directory=True)
    assert run_reset(repo, commit).returncode != 0
    assert (outside / 'existing.py').read_bytes() == b'outside untouched\n'
    (repo / 'tests').unlink()
    (repo / 'tests/existing.py').mkdir(parents=True)
    (repo / 'tests/existing.py/keep').write_bytes(b'not recursively deleted')
    assert run_reset(repo, commit).returncode != 0
    assert (repo / 'tests/existing.py/keep').read_bytes() == b'not recursively deleted'


def test_bad_official_paths_and_missing_baseline_rejected(tmp_path):
    for patch in ['diff --git a/../outside b/../outside\n',
                  'diff --git a/.git/config b/.git/config\n',
                  'diff --git a/a b/a\ndiff --git a/a/b b/a/b\n']:
        with pytest.raises(ValueError):
            reset.test_paths(patch)
    fixture(tmp_path)
    before = (tmp_path / 'tests/existing.py').read_bytes()
    assert run_reset(tmp_path, '0' * 40).returncode != 0
    assert (tmp_path / 'tests/existing.py').read_bytes() == before


def test_official_patch_apply_failure_exits_before_tests(tmp_path):
    commit = fixture(tmp_path)
    patch = ('diff --git a/tests/existing.py b/tests/existing.py\n'
             '--- a/tests/existing.py\n+++ b/tests/existing.py\n'
             '@@ -1 +1 @@\n-incorrect official preimage\n+expected new test\n')
    script = ('#!/bin/bash\nset -uxo pipefail\n'
              f'git checkout {commit} tests/existing.py\n'
              "git apply -v - <<'EOF_123'\n" + patch + 'EOF_123\n'
              'touch TESTS_EXECUTED\n'
              f'git checkout {commit} tests/existing.py\n')
    value, provenance = reset.repair_eval_script({'instance_id': 'sphinx-doc__sphinx-11510',
        'base_commit': commit, 'test_patch': patch, 'eval_script': script})
    result = subprocess.run(['/bin/bash', '-c', value], cwd=tmp_path, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    assert result.returncode != 0 and not (tmp_path / 'TESTS_EXECUTED').exists()
    assert provenance['official_test_patch_changed'] is False
    assert Path(tmp_path / 'production.py').read_bytes() == b'original code\n'
