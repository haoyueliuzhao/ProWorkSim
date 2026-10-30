"""CPU permission regressions; no chown, root, containers or real repositories."""
import os
from pathlib import Path

import pytest

from proworksim.repository_sources_v054 import normalize_policy, tree_manifest
from proworksim.software_benchmark_candidates_v054 import _git
from proworksim.software_benchmark_managed_actor_v064 import synchronize_tree as old_sync
from proworksim.software_benchmark_managed_sync_v095 import synchronize_tree


def candidate(files, modes=None):
    modes = modes or {}
    metadata = {name: {'kind': 'file', 'encoding': 'utf-8', 'mode': modes.get(name, '100644')}
                for name in files}
    return {'files': files, 'entry_metadata': metadata, 'file_policy': normalize_policy(),
            'tree_sha256': tree_manifest(files, metadata)['tree_sha256']}


def test_unchanged_foreign_inode_no_longer_needs_chmod(tmp_path, monkeypatch):
    file = tmp_path/'build/freetype/CMakeLists.txt'
    file.parent.mkdir(parents=True)
    file.write_text('existing build input')
    original = os.chmod
    def chmod(path, *args, **kwargs):
        if Path(path) == file:
            raise PermissionError(1, 'simulated non-owner chmod', str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'chmod', chmod)
    value = candidate({'build/freetype/CMakeLists.txt': file.read_text()})
    before = file.stat().st_ino
    with pytest.raises(PermissionError):
        old_sync(tmp_path, value)
    receipt = synchronize_tree(tmp_path, value)
    assert file.stat().st_ino == before and receipt['atomically_replaced_entries'] == 0


def test_real_mode_change_uses_owned_replacement_and_is_not_swallowed(tmp_path, monkeypatch):
    file = tmp_path/'entry.py'
    file.write_text('unchanged bytes')
    before = file.stat().st_ino
    monkeypatch.setattr(os, 'chmod', lambda *_args, **_kw: (_ for _ in ()).throw(PermissionError('non-owner')))
    receipt = synchronize_tree(tmp_path, candidate({'entry.py': file.read_text()}, {'entry.py': '100755'}))
    assert file.stat().st_ino != before and file.stat().st_mode & 0o111
    assert receipt['requested_mode_changes_applied'] == 1


def test_changed_readonly_content_replaces_inode_and_preserves_git_controls(tmp_path):
    _git(tmp_path, ['init', '--quiet', '--template='])
    (tmp_path/'.git/fixture-control').write_text('private controls')
    file = tmp_path/'source.py'
    file.write_text('old')
    file.chmod(0o444)
    before = file.stat().st_ino
    (tmp_path/'removed').write_text('delete')
    receipt = synchronize_tree(tmp_path, candidate({'source.py': 'new', 'new.py': 'added'}))
    assert file.read_text() == 'new' and file.stat().st_ino != before
    assert (tmp_path/'.git/fixture-control').read_text() == 'private controls'
    assert not (tmp_path/'removed').exists() and receipt['exact_complete_tree']


def test_real_parent_permission_failure_remains_failure(tmp_path, monkeypatch):
    (tmp_path/'source.py').write_text('old')
    monkeypatch.setattr(os, 'replace', lambda *_: (_ for _ in ()).throw(PermissionError('no parent write')))
    with pytest.raises(PermissionError, match='no parent write'):
        synchronize_tree(tmp_path, candidate({'source.py': 'new'}))
    assert (tmp_path/'source.py').read_text() == 'old'
    assert list(tmp_path.glob('.pws-sync-*')) == []
