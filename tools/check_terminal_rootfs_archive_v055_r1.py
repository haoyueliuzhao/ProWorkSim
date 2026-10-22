"""Necessary finite archive controls; every mutable path is explicit under /tmp."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-root', required=True, type=Path)
    args = parser.parse_args()
    base = args.fixture_root
    if (not base.is_absolute() or base.resolve() != base or base.parent != Path('/tmp')
            or not base.name.startswith('pws-terminal-archive-control-') or base.exists()):
        raise ValueError('An explicit new /tmp/pws-terminal-archive-control-* root is mandatory')
    base.mkdir(mode=0o700)
    tool = Path(__file__).resolve().with_name('archive_terminal_rootfs_v055_r1.py')
    spec = importlib.util.spec_from_file_location('pws_archive_fixture', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Fixture code cannot reach production plan, state, cleanup or restore paths.
    def forbidden(*args, **kwargs):
        raise AssertionError('Production operation is forbidden in fixture controls')
    for name in ('plan', 'load_plan', 'live_quiet', 'archive_one', 'release_one', 'restore_one', 'current_row'):
        setattr(module, name, forbidden)
    root = base / 'rootfs'
    root.mkdir()
    (root / 'sub').mkdir(mode=0o750)
    file = root / 'sub/file'
    file.write_bytes(b'original-content\x00\xff\n')
    os.chmod(file, 0o640)
    os.setxattr(file, 'user.binary-proof', b'\x00\xffproof')
    acl = ctypes.CDLL('libacl.so.1', use_errno=True)
    acl.acl_from_text.argtypes = [ctypes.c_char_p]
    acl.acl_from_text.restype = ctypes.c_void_p
    acl.acl_set_file.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    acl.acl_free.argtypes = [ctypes.c_void_p]
    pointer = acl.acl_from_text(b'user::rw-,user:12345:r--,group::r--,mask::r--,other::---')
    if not pointer or acl.acl_set_file(os.fsencode(file), 0x8000, pointer) != 0:
        raise OSError(ctypes.get_errno(), 'Fixture ACL setup failed')
    acl.acl_free(pointer)
    os.link(file, root / 'hardlink')
    os.symlink('sub/file', root / 'symlink')
    sparse = root / 'sparse'
    with sparse.open('wb') as stream:
        stream.seek(2 * 1024 * 1024)
        stream.write(b'sparse-end')
    os.utime(file, ns=(1700000000123456789, 1700000000123456789))
    rows = module.inventory(root, include_content=True)
    archive = base / 'rootfs.tar.zst'
    module.encode(root, archive, base / 'encode.stderr')
    verification = module.verify(archive, rows)
    module.unchanged(root, rows)
    restored = base / 'restored'
    restored.mkdir()
    subprocess.run(['/usr/bin/tar', '--zstd', '-xf', str(archive), '-C', str(restored), '--numeric-owner',
                    '--same-owner', '--same-permissions', '--acls', '--xattrs', '--xattrs-include=*', '--sparse', '--keep-old-files'], check=True)
    actual = module.inventory(restored / 'rootfs', include_content=True)
    def portable(value):
        return {n: {k: v for k, v in r.items() if k not in {'dev', 'ino', 'ctime_ns', 'allocated_bytes', 'size'}
                    or (k == 'size' and r['type'] == 'file')} for n, r in value.items()}
    if portable(rows) != portable(actual):
        raise AssertionError('Full fixture restored content/metadata differs')
    controls = ['complete_stream_readback_and_real_restore_with_binary_xattr_ACL_hardlink_symlink_sparse_and_ns_mtime']
    file.write_bytes(b'changed')
    try:
        module.unchanged(root, rows)
    except RuntimeError:
        controls.append('changed_source_refused_without_deletion')
    else:
        raise AssertionError('Changed source accepted')
    special = base / 'special'
    special.mkdir()
    os.mkfifo(special / 'fifo')
    try:
        module.inventory(special, include_content=True)
    except ValueError:
        controls.append('unsupported_fifo_refused')
    else:
        raise AssertionError('Special node accepted')
    external = base / 'external'
    external.mkdir()
    os.link(file, external / 'link')
    try:
        module.inventory(external, include_content=True)
    except ValueError:
        controls.append('external_hardlink_refused')
    else:
        raise AssertionError('External hardlink accepted')
    try:
        module.source_path(base / 'rootfs')
    except ValueError:
        controls.append('non_allowlisted_path_refused')
    else:
        raise AssertionError('Unregistered source accepted')
    bad = base / 'corrupt.tar.zst'
    raw = archive.read_bytes()
    bad.write_bytes(raw[:max(1, len(raw) // 2)])
    try:
        module.verify(bad, rows)
    except (ValueError, EOFError, OSError, Exception) as error:
        controls.append('truncated_archive_refused_' + type(error).__name__)
    else:
        raise AssertionError('Truncated archive accepted')
    receipt = {'version': 'v055-terminal-rootfs-archive-control-r1', 'passed': True,
               'fixture_root': str(base), 'source': module.ref(tool), 'controls': controls,
               'readback': verification, 'formal_rootfs_reads': 0, 'formal_deletions': 0, 'model_calls': 0}
    (base / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
