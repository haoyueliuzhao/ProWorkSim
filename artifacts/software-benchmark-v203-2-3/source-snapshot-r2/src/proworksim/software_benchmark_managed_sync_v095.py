"""Synchronize a private actor tree without chmod on untouched foreign inodes.

No chown, privilege change or permission bypass is used. Changed regular files
are written to owned temporary siblings, given their requested Git mode, and
atomically replaced; inaccessible parent directories still fail explicitly.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from .repository_sources_v054 import decode_entry, snapshot_repository, validate_tree
from .software_benchmark_gitlinks_v054 import check_gitlink_payload, checked_gitlinks

VERSION = 'v095-private-managed-atomic-tree-sync-r1'


def _parents(root, target):
    for parent in target.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Candidate ancestor is a symlink')
    target.parent.mkdir(parents=True, exist_ok=True)


def _replace_regular(target, raw, mode):
    descriptor, name = tempfile.mkstemp(prefix='.pws-sync-', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def synchronize_tree(root, candidate, *, gitlinks=()):
    """Keep exact contents/Git modes while avoiding unnecessary inode mutation."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Actor checkout must be an existing real directory')
    root = root.resolve()
    links = checked_gitlinks(list(gitlinks))
    files, metadata = candidate['files'], candidate['entry_metadata']
    validate_tree(files, metadata, candidate['file_policy'])
    check_gitlink_payload(files, links)
    controls = {'.git', *(item['path']+'/.git' for item in links)}
    for folder, dirs, leaves in os.walk(root, followlinks=False):
        parent = Path(folder)
        for name in list(dirs):
            path = parent/name
            relative = path.relative_to(root).as_posix()
            if relative in controls:
                dirs.remove(name)
            elif path.is_symlink():
                dirs.remove(name)
                leaves.append(name)
        for name in leaves:
            path = parent/name
            if path.relative_to(root).as_posix() not in controls | files.keys():
                path.unlink()
    unchanged, replaced, mode_changes = 0, 0, 0
    for relative in sorted(files):
        target = root/relative
        _parents(root, target)
        raw, desired = decode_entry(relative, files[relative], metadata[relative]), metadata[relative]
        if target.is_dir() and not target.is_symlink():
            target.rmdir()  # only an actually empty directory may become a file
        if desired['kind'] == 'symlink':
            if target.is_symlink() and os.readlink(target) == files[relative]:
                unchanged += 1
                continue
            # The temporary link is inside an owned private directory; replace
            # the destination itself, never follow its old or new link target.
            with tempfile.TemporaryDirectory(prefix='.pws-sync-link-', dir=target.parent) as temporary:
                link = Path(temporary)/'link'
                link.symlink_to(files[relative])
                os.replace(link, target)
            replaced += 1
            continue
        desired_exec = desired['mode'] == '100755'
        current = target.lstat() if target.exists() or target.is_symlink() else None
        regular = current is not None and stat.S_ISREG(current.st_mode)
        same_mode = regular and bool(current.st_mode & 0o111) == desired_exec
        if same_mode and target.read_bytes() == raw:
            unchanged += 1
            continue
        if regular and not same_mode:
            mode_changes += 1
        _replace_regular(target, raw, 0o755 if desired_exec else 0o644)
        replaced += 1
    # Empty pre-existing directories are not Git tree entries. Keep them unless
    # an actual requested file replacement required removing one above.
    observed = snapshot_repository(root, file_policy=candidate['file_policy'], gitlinks=links)
    if observed['tree']['tree_sha256'] != candidate['tree_sha256']:
        raise ValueError('Actor checkout failed the complete synchronized-tree comparison')
    return {'version': VERSION, 'tree_sha256': candidate['tree_sha256'],
            'exact_complete_tree': True, 'git_control_preserved': True, 'source_file_count': len(files),
            'unchanged_entries_preserved': unchanged, 'atomically_replaced_entries': replaced,
            'requested_mode_changes_applied': mode_changes, 'ownership_changes': 0}
