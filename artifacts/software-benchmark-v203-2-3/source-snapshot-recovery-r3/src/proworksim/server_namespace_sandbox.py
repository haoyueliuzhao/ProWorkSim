"""Filesystem confinement for servers without Landlock ABI 3.

This trusted, single-threaded worker initializer changes the current process in
place. It neither forks nor executes another interpreter, so registered process
identity and pre-established fixture sockets survive. The caller must install
its seccomp filter immediately afterwards and abort on any exception; this is
not a context manager and namespace changes cannot be rolled back.

Only declared roots enter a fresh tmpfs root, through nonrecursive bind mounts.
No host procfs or sysfs enters it. The empty host staging directory is returned
for the trusted parent to remove after reaping the worker.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import os
from pathlib import Path
import platform
import re
import stat
import tempfile

VERSION = "v1-user-mount-namespace-minimal-root"

_CLONE_NEWNS = 0x00020000
_CLONE_NEWUSER = 0x10000000
_MS_RDONLY = 1
_MS_NOSUID = 2
_MS_NODEV = 4
_MS_NOEXEC = 8
_MS_REMOUNT = 32
_MS_BIND = 4096
_MS_REC = 16384
_MS_PRIVATE = 1 << 18


def _path(value):
    if (not isinstance(value, str) or not value.startswith("/")
            or value == "/" or "\x00" in value or "\\" in value
            or any(ord(character) < 32 for character in value)
            or os.path.normpath(value) != value or value.startswith("//")
            or any(part in (".", "..") for part in value.split("/"))):
        raise ValueError("Sandbox paths must be normalized, non-root absolute paths")
    return value


def _below(path, parent):
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _check_reserved(path):
    if path == "/" or any(_below(path, root) for root in ("/proc", "/sys", "/dev")):
        raise ValueError("Sandbox declarations may not expose host root/proc/sys/dev")


def _symlinks(path):
    """Retain pathname aliases, without granting their target any extra access."""
    result = {}
    pending = path.split("/")[1:]
    current = "/"
    followed = 0
    while pending:
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            current = os.path.dirname(current)
            continue
        candidate = os.path.join(current, part)
        try:
            target = os.readlink(candidate)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOENT, errno.ENOTDIR):
                raise
            current = candidate
            continue
        followed += 1
        if followed > 40:
            raise ValueError("Too many symlink indirections in sandbox declaration")
        result[candidate] = target
        pending = target.split("/") + pending
        if target.startswith("/"):
            current = "/"
    return result


def _inherited_fds(spec):
    allowed = {0, 1, 2}
    runtime_devices = []
    rows = spec.get("loopback_fds", [])
    if not isinstance(rows, list):
        raise ValueError("loopback_fds must be a list of explicit socket fixtures")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("clients"), list):
            raise ValueError("Invalid inherited socket fixture declaration")
        for descriptor in [row.get("listener"), *row["clients"]]:
            if type(descriptor) is not int or descriptor < 3 or descriptor in allowed:
                raise ValueError("Fixture descriptors must be distinct integers greater than 2")
            if not stat.S_ISSOCK(os.fstat(descriptor).st_mode):
                raise ValueError("Only explicitly declared socket descriptors may be inherited")
            allowed.add(descriptor)
    for name in os.listdir("/proc/self/fd"):
        descriptor = int(name)
        try:
            metadata = os.fstat(descriptor)
            mode = metadata.st_mode
        except OSError as error:
            # listdir's own directory descriptor has already been closed.
            if error.errno == errno.EBADF:
                continue
            raise
        if descriptor not in allowed and stat.S_ISCHR(mode):
            flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
            if (metadata.st_rdev == os.makedev(1, 9)
                    and flags & os.O_ACCMODE == os.O_RDONLY and not flags & os.O_PATH):
                # CPython 3.10 can cache a readonly urandom handle. This is the
                # same exact device already admitted at /dev/urandom, not an
                # additional filesystem or socket grant.
                runtime_devices.append(descriptor)
                continue
        if descriptor not in allowed or stat.S_ISDIR(mode):
            target = os.readlink(f"/proc/self/fd/{descriptor}")
            raise ValueError(f"Unauthorized inherited descriptor: {descriptor} "
                             f"(mode={oct(mode)}, target={target!r})")
    return {"fixture_fds": sorted(allowed - {0, 1, 2}),
            "runtime_readonly_device_fds": sorted(runtime_devices)}


def validate_spec(spec):
    """Read-only preflight; no namespace, credentials or filesystem mutation."""
    worktree_declared = _path(spec["worktree"])
    _check_reserved(worktree_declared)
    worktree = str(Path(worktree_declared).resolve(strict=True))
    _check_reserved(worktree)
    if not Path(worktree).is_dir():
        raise ValueError("Sandbox worktree must be a directory")
    writable = spec.get("worktree_writable", True)
    if type(writable) is not bool:
        raise ValueError("worktree_writable must be a boolean")
    declarations = spec["readonly_paths"]
    if not isinstance(declarations, list):
        raise ValueError("readonly_paths must be a list")
    readonly, missing = [], []
    aliases = _symlinks(worktree_declared)
    for declaration in declarations:
        declaration = _path(declaration)
        resolved = str(Path(declaration).resolve())
        _check_reserved(declaration)
        _check_reserved(resolved)
        if _below(worktree, resolved) or _below(resolved, worktree):
            raise ValueError("Readonly paths and worktree must not overlap")
        try:
            mode = os.stat(resolved).st_mode
        except FileNotFoundError:
            missing.append(declaration)
            continue
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError("Readonly paths must be regular files or directories")
        aliases.update(_symlinks(declaration))
        readonly.append(resolved)
    # These are pathname aliases only. For example /lib points to the new
    # /usr/lib scaffold; it does not make the host /usr/lib tree visible.
    for alias in ("/bin", "/sbin", "/lib", "/lib64"):
        if os.path.islink(alias):
            aliases.update(_symlinks(alias))
    roots = []
    for path in sorted(set(readonly), key=lambda value: (len(value), value)):
        if not any(_below(path, root) for root in roots):
            roots.append(path)
    if len(os.listdir("/proc/self/task")) != 1:
        raise RuntimeError("Namespace confinement must start in a single-threaded worker")
    return {"worktree": worktree, "worktree_writable": writable,
            "readonly_paths": roots, "missing_readonly_paths": missing,
            "aliases": aliases, **_inherited_fds(spec)}


def _mount_table():
    def unescape(value):
        return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)

    result = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        result.append({"path": unescape(fields[4]), "options": fields[5].split(","),
                       "propagation": fields[6:fields.index("-")]})
    return result


def _validate_mounts(mounts, paths):
    for path in paths:
        for mount in mounts:
            if mount["path"] != path and _below(mount["path"], path):
                raise ValueError(f"Declared sandbox root contains a nested mount: {path}")


def _source_flags(descriptor):
    # A chroot inside a filesystem need not have a '/' mountinfo entry. The
    # actual opened source mount supplies its locked VFS flags without guessing
    # from pathname ancestry, including when mounts are stacked.
    flags = os.fstatvfs(descriptor).f_flag
    pairs = (("ST_RDONLY", _MS_RDONLY), ("ST_NOSUID", _MS_NOSUID),
             ("ST_NODEV", _MS_NODEV), ("ST_NOEXEC", _MS_NOEXEC),
             ("ST_NOATIME", 1024), ("ST_NODIRATIME", 2048),
             ("ST_RELATIME", 1 << 21))
    return sum(mount_flag for name, mount_flag in pairs
               if flags & getattr(os, name, 0))


class _Linux:
    def __init__(self):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                                   ctypes.c_ulong, ctypes.c_char_p]
        self.libc.mount.restype = ctypes.c_int
        self.libc.unshare.argtypes = [ctypes.c_int]
        self.libc.unshare.restype = ctypes.c_int
        self.libc.prctl.restype = ctypes.c_int

    def check(self, result, operation):
        if result < 0:
            raise OSError(ctypes.get_errno(), operation)
        return result

    def mount(self, source, target, kind=None, flags=0, data=None):
        def encode(value):
            return os.fsencode(value) if value is not None else None

        self.check(self.libc.mount(encode(source), encode(target), encode(kind), flags,
                                   encode(data)), "mount:" + target)

    def prctl(self, operation, value=0, extra=0):
        return self.check(self.libc.prctl(operation, value, extra, 0, 0),
                          f"prctl:{operation}")


def _enter_namespaces(linux, uid, gid):
    def mappings(path):
        return [tuple(map(int, line.split())) for line in Path(path).read_text().splitlines()]

    uid_map = mappings("/proc/self/uid_map")
    gid_map = mappings("/proc/self/gid_map")
    # The server's private runtime is already chrooted in a user namespace.
    # Linux rejects another NEWUSER there. Reuse only a positively identified
    # single-ID namespace, never an arbitrary failed-unshare fallback.
    restricted = (len(uid_map) == len(gid_map) == 1
                  and uid_map[0][0] == uid and uid_map[0][2] == 1
                  and gid_map[0][0] == gid and gid_map[0][2] == 1)
    if restricted:
        for capability in (8, 18, 21):  # SETPCAP, SYS_CHROOT, SYS_ADMIN
            if linux.prctl(23, capability) != 1:
                raise RuntimeError("Outer user namespace lacks required capability bounding rights")
        # unshare is also the effective CAP_SYS_ADMIN check: failure aborts.
        linux.check(linux.libc.unshare(_CLONE_NEWNS), "unshare:private mount namespace")
        mounts = _mount_table()
        if any(any(field.startswith(("shared:", "master:", "propagate_from:"))
                   for field in mount["propagation"]) for mount in mounts):
            raise RuntimeError("Outer private runtime has shared/slave mount propagation")
        if not any(_below("/tmp", mount["path"]) for mount in mounts):
            raise RuntimeError("Cannot prove that the staging /tmp mount is private")
        return "reused_single_id_user_namespace", mounts
    linux.check(linux.libc.unshare(_CLONE_NEWUSER | _CLONE_NEWNS),
                "unshare:user+mount (unprivileged namespaces must be available)")
    Path("/proc/self/setgroups").write_text("deny\n")
    Path("/proc/self/uid_map").write_text(f"{uid} {uid} 1\n")
    Path("/proc/self/gid_map").write_text(f"{gid} {gid} 1\n")
    linux.mount(None, "/", flags=_MS_REC | _MS_PRIVATE)
    return "created_single_id_user_namespace", _mount_table()


def _drop_capabilities(linux, last_cap):
    class Header(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class Data(ctypes.Structure):
        _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32),
                    ("inheritable", ctypes.c_uint32)]

    # Lock NOROOT and NO_SETUID_FIXUP, including when an outer private runtime
    # mapped this worker to uid 0. Later exec must not restore root capabilities.
    linux.prctl(28, 0x0F)  # PR_SET_SECUREBITS
    linux.prctl(47, 4)  # PR_CAP_AMBIENT / PR_CAP_AMBIENT_CLEAR_ALL
    for capability in range(last_cap + 1):
        linux.prctl(24, capability)  # PR_CAPBSET_DROP
    linux.prctl(38, 1)  # PR_SET_NO_NEW_PRIVS
    header, data = Header(0x20080522, 0), (Data * 2)()
    linux.check(linux.libc.capset(ctypes.byref(header), ctypes.byref(data)), "capset")
    linux.check(linux.libc.capget(ctypes.byref(header), ctypes.byref(data)), "capget")
    if any(row.effective or row.permitted or row.inheritable for row in data):
        raise RuntimeError("Capability drop did not remove all process capabilities")
    if any(linux.prctl(23, capability) != 0 for capability in range(last_cap + 1)):
        raise RuntimeError("Capability bounding set is not empty")
    if linux.prctl(39) != 1 or linux.prctl(27) != 0x0F:
        raise RuntimeError("Privilege-restoration protections are not installed")


def install_filesystem(spec):
    """Install the filesystem boundary in place; every failure aborts admission."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Namespace sandbox requires Linux x86_64")
    plan = validate_spec(spec)
    linux = _Linux()
    uid, gid = os.getuid(), os.getgid()
    if (os.geteuid(), os.getegid()) != (uid, gid):
        raise RuntimeError("Sandbox does not accept setuid/setgid worker credentials")
    last_cap = int(Path("/proc/sys/kernel/cap_last_cap").read_text())
    if not 0 <= last_cap <= 63:
        raise RuntimeError("Unsupported kernel capability range")
    sources = [(plan["worktree"], not plan["worktree_writable"], False)]
    sources += [(path, True, False) for path in plan["readonly_paths"]]
    sources += [("/dev/null", False, True), ("/dev/urandom", True, True)]
    opened = []
    staging = None
    entered = False
    try:
        user_namespace, mounts = _enter_namespaces(linux, uid, gid)
        # Opening after unshare pins paths in this mount namespace. Descriptors
        # from its predecessor cannot be bind-mounted through procfs magic links.
        for path, readonly, device in sources:
            descriptor = os.open(path, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
            opened.append((path, readonly, device, descriptor))
            mode = os.fstat(descriptor).st_mode
            if device:
                expected = os.makedev(1, 3 if path == "/dev/null" else 9)
                if not stat.S_ISCHR(mode) or os.fstat(descriptor).st_rdev != expected:
                    raise ValueError("Required device is not the expected Linux character device")
            elif not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("Sandbox source changed type before admission")

        _validate_mounts(mounts, [path for path, _, device, _ in opened if not device])
        if plan["worktree_writable"] and os.statvfs(plan["worktree"]).f_flag & os.ST_RDONLY:
            raise ValueError("Writable sandbox worktree resides on a readonly source mount")
        staging = tempfile.mkdtemp(prefix="proworksim-ns-", dir="/tmp")
        linux.mount("tmpfs", staging, "tmpfs", _MS_NOSUID | _MS_NODEV | _MS_NOEXEC,
                    "size=16m,nr_inodes=8192,mode=0755")
        root = Path(staging)

        # Build all mount targets before any bind can hide a scaffold or expose
        # a host directory. Mount destinations themselves are canonical paths.
        for path, _, _, descriptor in opened:
            destination = root / path.lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                destination.mkdir(exist_ok=True)
            else:
                destination.touch(exist_ok=False)
        for path, target in sorted(plan["aliases"].items(), key=lambda item: len(item[0])):
            destination = root / path.lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(destination):
                raise ValueError("Symlink alias collides with a sandbox mount target")
            destination.symlink_to(target)

        for path, readonly, device, descriptor in opened:
            destination = str(root / path.lstrip("/"))
            linux.mount(f"/proc/self/fd/{descriptor}", destination, flags=_MS_BIND)
            flags = _source_flags(descriptor) | _MS_NOSUID
            if not device:
                flags |= _MS_NODEV
            if readonly:
                flags |= _MS_RDONLY
            linux.mount(None, destination, flags=_MS_REMOUNT | _MS_BIND | flags)
        linux.mount(None, staging, flags=_MS_REMOUNT | _MS_RDONLY | _MS_NOSUID
                    | _MS_NODEV | _MS_NOEXEC)
        os.chroot(staging)
        entered = True
        os.chdir(plan["worktree"])
        # No old-root, source-directory or procfs descriptor survives the chroot.
        for _, _, _, descriptor in opened:
            os.close(descriptor)
        opened.clear()
        _drop_capabilities(linux, last_cap)
        return {"version": VERSION, "namespace_backend_version": VERSION,
                "filesystem_backend": "user_mount_namespace", "user_namespace": user_namespace,
                "landlock_enforced": False, "root": "minimal_readonly_tmpfs",
                "worktree_writable": plan["worktree_writable"],
                "readonly_paths": plan["readonly_paths"],
                "missing_readonly_paths": plan["missing_readonly_paths"],
                "mount_propagation": "private", "bind_mounts": "nonrecursive",
                "host_proc_sys_visible": False, "capabilities": "all_dropped_and_locked",
                "no_new_privs": True, "fixture_fds_preserved": plan["fixture_fds"],
                "runtime_readonly_device_fds": plan["runtime_readonly_device_fds"],
                "process_identity": "unchanged", "uid": uid, "gid": gid,
                "host_staging_directory": staging}
    finally:
        for _, _, _, descriptor in opened:
            os.close(descriptor)
        if staging is not None and not entered:
            # A failing initializer never falls back to unrestricted execution.
            # Before chroot, clean up its own temporary mount where possible.
            linux.libc.umount2(os.fsencode(staging), 2)  # MNT_DETACH
            try:
                os.rmdir(staging)
            except OSError:
                pass
