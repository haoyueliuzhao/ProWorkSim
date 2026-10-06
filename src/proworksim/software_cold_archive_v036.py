"""Lossless cold storage for closed P3 development/confirmation directories.

The caller must have joined the worker with exit code zero and stopped all
writers. This module also requires sibling report.json status=complete. Only
actual/{development,confirmation} is admitted; collection/support is excluded.

Archive creation hashes every relative file, writes and fsyncs a tar.gz, reads
every member back, then persists a manifest before quarantining the source.
The quarantined tree is checked again before its duplicate bytes are removed.
A pre-removal error retains source bytes, either live or in the named quarantine.
An interrupted cleanup remains recoverable from the already verified archive.
No historical data is processed by importing this module.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import uuid

VERSION = "closed-p3-cold-archive-v0.36"
ALLOWED_DIRECTORIES = frozenset({"development", "confirmation"})
CHUNK = 1024 * 1024


def _path(value):
    given = Path(value)
    if ".." in given.parts:
        raise ValueError("Parent traversal is not an archive path")
    value = Path(os.path.abspath(given))
    for part in (value, *value.parents):
        if part.is_symlink():
            raise ValueError("Symbolic links are not admitted")
    return value


def _file_digest(path):
    hasher = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _stamp(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _relative(name):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ValueError("Archive member has an unsafe relative path")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts) or PurePosixPath(name).is_absolute():
        raise ValueError("Archive member escapes its relative root")
    return name


def _inventory(root):
    root = _path(root)
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("Source must be an actual directory")
    entries = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        for name in names + filenames:
            path = Path(directory) / name
            before = path.lstat()
            relative = _relative(path.relative_to(root).as_posix())
            if before.st_dev != root_stat.st_dev:
                raise ValueError("Mounted external source trees are not admitted")
            if stat.S_ISDIR(before.st_mode):
                kind, size, checksum = "directory", 0, None
            elif stat.S_ISREG(before.st_mode) and before.st_nlink == 1:
                kind, size, checksum = "file", before.st_size, _file_digest(path)
            else:
                raise ValueError("Only ordinary directories and single-link regular files may be archived")
            if _stamp(before) != _stamp(path.lstat()):
                raise ValueError("Source changed while being enumerated")
            entries.append({"path": relative, "type": kind, "size": size, "sha256": checksum,
                            "mode": stat.S_IMODE(before.st_mode), "mtime_ns": before.st_mtime_ns})
    return sorted(entries, key=lambda row: row["path"])


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json_write(path, value, *, replace=False):
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_path(archive_path):
    path = _path(archive_path)
    return path.with_name(path.name + ".manifest.json")


def _manifest_entries(manifest):
    if manifest.get("version") != VERSION or manifest.get("source_kind") not in ALLOWED_DIRECTORIES:
        raise ValueError("Not a supported closed P3 archive manifest")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Missing archive member inventory")
    indexed = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid manifest member")
        name = _relative(entry.get("path"))
        if name in indexed or entry.get("type") not in {"file", "directory"}:
            raise ValueError("Duplicate or unsupported manifest member")
        if type(entry.get("size")) is not int or entry["size"] < 0:
            raise ValueError("Invalid member size")
        checksum = entry.get("sha256")
        if entry["type"] == "file" and (not isinstance(checksum, str) or len(checksum) != 64
                                         or any(char not in "0123456789abcdef" for char in checksum)):
            raise ValueError("Invalid member checksum")
        if entry["type"] == "directory" and (entry["size"] != 0 or checksum is not None):
            raise ValueError("Invalid directory inventory")
        if (type(entry.get("mode")) is not int or not 0 <= entry["mode"] <= 0o7777
                or type(entry.get("mtime_ns")) is not int or entry["mtime_ns"] < 0):
            raise ValueError("Invalid member metadata")
        indexed[name] = entry
    for name in indexed:
        for parent in PurePosixPath(name).parents:
            if str(parent) != "." and indexed.get(str(parent), {}).get("type") != "directory":
                raise ValueError("Every parent directory must be explicitly inventoried")
    return indexed


def _read_tar(archive_path, manifest, *, destination=None):
    indexed = _manifest_entries(manifest)
    seen = set()
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for info in archive:
            name = info.name[:-1] if info.isdir() and info.name.endswith("/") else info.name
            name = _relative(name)
            if name in seen or name not in indexed or not (info.isdir() or info.isreg()) or info.sparse:
                raise ValueError("Unexpected, duplicate, linked or unsupported tar member")
            seen.add(name)
            expected = indexed[name]
            if info.isdir() != (expected["type"] == "directory") or info.size != expected["size"]:
                raise ValueError("Tar member type/size differs from manifest")
            if info.isdir():
                if destination is not None:
                    (destination / name).mkdir(mode=0o700)
                continue
            hasher, size = hashlib.sha256(), 0
            target = (destination / name).open("xb") if destination is not None else None
            try:
                stream = archive.extractfile(info)
                if stream is None:
                    raise ValueError("Regular tar member has no bytes")
                with stream:
                    for chunk in iter(lambda: stream.read(CHUNK), b""):
                        hasher.update(chunk)
                        size += len(chunk)
                        if target is not None:
                            target.write(chunk)
                if target is not None:
                    target.flush()
                    os.fsync(target.fileno())
            finally:
                if target is not None:
                    target.close()
            if size != expected["size"] or hasher.hexdigest() != expected["sha256"]:
                raise ValueError("Tar member bytes differ from manifest")
    if seen != set(indexed):
        raise ValueError("Tar archive omitted inventoried paths")


def _verify(archive_path, manifest):
    before = archive_path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Archive must be an ordinary file")
    expected = manifest["archive"]
    if before.st_size != expected["size"] or _file_digest(archive_path) != expected["sha256"]:
        raise ValueError("Compressed archive checksum/size mismatch")
    _read_tar(archive_path, manifest)
    if _stamp(before) != _stamp(archive_path.lstat()):
        raise ValueError("Archive changed while being verified")


def verify_archive(archive_path):
    """Read-only compressed-file and every-member verification; never extracts."""
    archive_path = _path(archive_path)
    sidecar = manifest_path(archive_path)
    with sidecar.open("rb") as stream:
        manifest = json.load(stream)
    _verify(archive_path, manifest)
    return manifest


def archive_closed_directory(path, archive_path):
    """Archive one completed actual/development or actual/confirmation directory.

    Source writers must already have exited. Before removal, the archive has
    been read back byte-for-byte and its manifest fsynced. Unexpected changes
    leave recoverable originals in source or the manifest's quarantine_path.
    Existing archive/manifest targets are never overwritten.
    """
    source, archive_path = _path(path), _path(archive_path)
    actual = source.parent
    if (source.name not in ALLOWED_DIRECTORIES or actual.name != "actual"
            or archive_path.parent != actual or not archive_path.name.endswith(".tar.gz")):
        raise ValueError("Only sibling archives of actual/development or actual/confirmation are allowed")
    sidecar = manifest_path(archive_path)
    if archive_path.exists() or sidecar.exists():
        raise FileExistsError("Refusing to overwrite an archive or manifest")
    report_path = _path(actual / "report.json")
    report_bytes = report_path.read_bytes()
    if json.loads(report_bytes).get("status") != "complete":
        raise ValueError("Worker report must already be complete")
    source_stat = source.lstat()
    entries = _inventory(source)
    manifest = {"version": VERSION, "state": "verified_archive_source_present", "source_kind": source.name,
        "source_path": str(source), "worker_actual_path": str(actual),
        "closed_report": {"path": str(report_path), "sha256": hashlib.sha256(report_bytes).hexdigest()},
        "root_metadata": {"mode": stat.S_IMODE(source_stat.st_mode), "mtime_ns": source_stat.st_mtime_ns},
        "entries": entries, "file_count": sum(row["type"] == "file" for row in entries),
        "directory_count": sum(row["type"] == "directory" for row in entries),
        "original_file_bytes": sum(row["size"] for row in entries), "archive_verified": True,
        "source_removed": False,
        "scope": "Exact relative paths and bytes, plus modes and mtimes. Only closed P3 output; worker exit0/no-writers is a caller precondition, not inferred from report status alone."}
    descriptor, temporary_name = tempfile.mkstemp(prefix=".cold-archive-", suffix=".tar.gz", dir=actual)
    temporary = Path(temporary_name)
    quarantine = actual / ("." + source.name + ".cold-quarantine-" + uuid.uuid4().hex)
    manifest["quarantine_path"] = str(quarantine)
    sidecar_owned = quarantined = removal_started = source_removed = False
    try:
        with os.fdopen(descriptor, "wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for row in entries:
                        member = tarfile.TarInfo(row["path"])
                        member.type = tarfile.DIRTYPE if row["type"] == "directory" else tarfile.REGTYPE
                        member.size, member.mode = row["size"], row["mode"]
                        member.mtime = row["mtime_ns"] / 1_000_000_000
                        if row["type"] == "directory":
                            archive.addfile(member)
                        else:
                            with os.fdopen(os.open(source / row["path"], os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
                                archive.addfile(member, stream)
            output.flush()
            os.fsync(output.fileno())
        manifest["archive"] = {"path": str(archive_path), "size": temporary.stat().st_size,
                               "sha256": _file_digest(temporary)}
        _verify(temporary, manifest)
        os.link(temporary, archive_path)
        temporary.unlink()
        _sync_directory(actual)
        archive_stamp = _stamp(archive_path.lstat())
        _json_write(sidecar, manifest)
        sidecar_owned = True
        if _stamp(source.lstat()) != _stamp(source_stat):
            raise ValueError("Source root changed before quarantine")
        if quarantine.exists():
            raise FileExistsError("Quarantine name unexpectedly exists")
        os.rename(source, quarantine)
        quarantined = True
        _sync_directory(actual)
        manifest.update(state="quarantine_pending_verification", quarantine_path=str(quarantine))
        _json_write(sidecar, manifest, replace=True)
        if _inventory(quarantine) != entries or _stamp(archive_path.lstat()) != archive_stamp:
            raise ValueError("Source or verified archive changed before duplicate removal")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise RuntimeError("This platform lacks symlink-safe directory removal")
        removal_started = True
        shutil.rmtree(quarantine)
        source_removed = True
        _sync_directory(actual)
        manifest.update(state="archived", source_removed=True, quarantine_removed=True)
        _json_write(sidecar, manifest, replace=True)
        return manifest
    except BaseException as error:
        if sidecar_owned:
            retained = quarantine if quarantined else source
            manifest.update(state="cleanup_error_archive_verified" if removal_started else "source_retained_archive_verified",
                            source_removed=source_removed, duplicate_removal_started=removal_started,
                            retained_source_path=str(retained) if retained.exists() else None,
                            error={"type": type(error).__name__, "message": str(error)},
                            recovery="Verify the durable archive; retain any source/quarantine remainder. Restore only to a new directory.")
            _json_write(sidecar, manifest, replace=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def restore_archive(archive_path, destination):
    """Restore to an exclusively created new directory; never writes old paths."""
    archive_path, destination = _path(archive_path), _path(destination)
    if destination.exists():
        raise FileExistsError("Restore destination must not exist")
    if not destination.parent.is_dir():
        raise ValueError("Restore parent directory must already exist")
    manifest = verify_archive(archive_path)
    destination.mkdir(mode=0o700)
    _read_tar(archive_path, manifest, destination=destination)
    for row in reversed(manifest["entries"]):
        path = destination / row["path"]
        os.chmod(path, row["mode"])
        os.utime(path, ns=(row["mtime_ns"], row["mtime_ns"]))
        if row["type"] == "directory":
            _sync_directory(path)
    metadata = manifest["root_metadata"]
    os.chmod(destination, metadata["mode"])
    os.utime(destination, ns=(metadata["mtime_ns"], metadata["mtime_ns"]))
    _sync_directory(destination)
    _sync_directory(destination.parent)
    return {"version": VERSION, "restored": True, "destination": str(destination),
            "file_count": manifest["file_count"], "original_file_bytes": manifest["original_file_bytes"],
            "archive_sha256": manifest["archive"]["sha256"], "archive_preserved": True}
