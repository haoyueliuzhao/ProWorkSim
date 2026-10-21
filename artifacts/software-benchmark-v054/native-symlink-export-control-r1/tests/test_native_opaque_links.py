"""One native export control; no model, official task, Docker or GPU use."""
from pathlib import Path
import importlib.util
import json
import os
import sys

import pytest

from proworksim.repository_sources_v054 import RepositorySourceError, capture_repository, validate_tree
from proworksim.software_benchmark_candidates_v054 import materialize_tree, reference, write_new

STAGE = Path('/tmp/v054-native-symlink-export-r1')
NAME = 'proworksim.software_benchmark_native_artifact_v054'
spec = importlib.util.spec_from_file_location(NAME, STAGE / 'src/proworksim/software_benchmark_native_artifact_v054.py')
module = importlib.util.module_from_spec(spec)
sys.modules[NAME] = module
spec.loader.exec_module(module)


def test_native_opaque_links_preserve_exact_final_tree(tmp_path, monkeypatch):
    source = tmp_path / 'workspace'
    source.mkdir()
    (source / 'file.txt').write_bytes(b'original\n')
    (source / 'relative').symlink_to('file.txt')
    (source / '.gitignore').write_text('result_images/\n')
    identity = {'instance_id': 'synthetic-opaque', 'repo': 'synthetic/repo',
                'base_commit': 'synthetic-base', 'dataset_revision': 'synthetic-fixed'}
    initial = capture_repository(source, tmp_path / 'baseline', task_id=identity['instance_id'],
        problem_statement='Synthetic opaque symlink export only.', source_identity=identity)
    baseline = json.loads((initial.parent / 'initial-tree.json').read_text())
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = outside / 'unread-target.txt'
    target.write_bytes(b'THIS TARGET MUST NEVER BE READ BY EXPORT\n')
    (source / 'file.txt').write_bytes(b'final\n')
    (source / 'result_images').mkdir()
    links = {'absolute': os.fsencode(target), 'dangling': b'not-existing-anywhere',
             'outside': b'../outside/unread-target.txt', 'outside-directory': os.fsencode(outside),
             'result_images/absolute-ignored': b'/testbed/image-expected.png',
             'non-utf8-target': b'../outside/\xff'}
    for name, raw in links.items():
        os.symlink(raw, os.fsencode(source / name))
    def workspace_identity():
        rows = []
        for root, directories, files in os.walk(source, followlinks=False):
            for name in [*directories, *files]:
                p = Path(root) / name
                st = p.lstat()
                rows.append((str(p.relative_to(source)), st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns,
                             os.readlink(os.fsencode(p)) if p.is_symlink() else None))
        return rows
    before, target_before = workspace_identity(), target.stat()
    real_open = os.open
    observed_reads = []
    def no_target_read(path, flags, *args, **kwargs):
        actual = Path(os.fsdecode(path))
        if actual.is_relative_to(outside):
            raise AssertionError('Exporter followed a target outside the workspace')
        observed_reads.append(str(actual))
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', no_target_read)
    captured = module.capture_native_candidate(source, tmp_path / 'final',
        task_id=identity['instance_id'], problem_statement='Synthetic opaque symlink export only.',
        source_identity=identity)
    candidate = json.loads((captured.parent / 'initial-tree.json').read_text())
    receipt = module.export_native_git_patch(baseline, candidate, tmp_path / 'candidate.patch')
    assert receipt['round_trip_verified'] and receipt['symlink_targets_followed'] is False
    assert workspace_identity() == before and target.stat() == target_before
    assert 'result_images/absolute-ignored' in candidate['files']
    for name, raw in links.items():
        assert module.decode_native_entry(name, candidate['files'][name], candidate['entry_metadata'][name]) == raw
    assert module.decode_native_entry('relative', candidate['files']['relative'], candidate['entry_metadata']['relative']) == b'file.txt'
    # The same blob set remains inadmissible to PROJECT's existing provider.
    with pytest.raises(RepositorySourceError):
        validate_tree(candidate['files'], candidate['entry_metadata'])
    materialize_tree(baseline['files'], baseline['entry_metadata'], tmp_path / 'official-style-worktree')
    worktree = tmp_path / 'official-style-worktree'
    module._git(worktree, ['init', '--quiet', '--template='])
    module._git(worktree, ['add', '--force', '--all'])
    module._git(worktree, ['apply', '--check', '--binary', str(tmp_path / 'candidate.patch')])
    module._git(worktree, ['apply', '--binary', str(tmp_path / 'candidate.patch')])
    applied = module.snapshot_native_candidate(worktree)
    assert applied['tree'] == candidate['tree']
    for name, raw in links.items():
        assert os.readlink(os.fsencode(worktree / name)) == raw
    assert workspace_identity() == before and target.stat() == target_before
    write_new(STAGE / 'control-receipt.json', {'version': 'v054-native-opaque-link-CPU-control-r1',
        'passed': True, 'actual_model_calls': 0, 'GPU_loads': 0, 'official_grader_calls': 0,
        'absolute_dangling_outside_directory_and_nonUTF8_targets_exact': True,
        'relative_target_unchanged': True, 'targets_not_opened': True,
        'original_workspace_unchanged': True, 'gitignored_artifact_included': True,
        'bare_index_patch_round_trip': True, 'ordinary_git_apply_worktree_round_trip': True,
        'PROJECT_provider_still_rejects_unsafe_links': True,
        'new_source': reference(STAGE / 'src/proworksim/software_benchmark_native_artifact_v054.py'),
        'closure_source': reference(STAGE / 'src/proworksim/software_benchmark_native_closure_v054.py')})
