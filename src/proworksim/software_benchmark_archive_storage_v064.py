"""Exact streaming archives and immutable baseline deduplication.

The zstd producer never saves a raw tar. Its input/output SHA receipts become
round-trip proof only after a consumer fully verifies the decompressed stream.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import gzip
import hashlib
import io
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import json_bytes

VERSION = "v064-lossless-transport-storage-r1"
BLOCK = 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
CODEC_ROOT = ROOT / "runs/software-benchmark-v064/archive-codec"
CODEC_BINARY = CODEC_ROOT / "zstd"
CODEC_MANIFEST = CODEC_ROOT / "manifest.json"
CODEC_VERSION = "v064-owned-zstd-codec-r1"
CODEC_SOURCE = Path("/usr/bin/zstd")
COMPRESSION_ARGUMENTS = ("--long=27", "-3", "-T1", "-q", "-c")
DECOMPRESSION_ARGUMENTS = ("-d", "--long=27", "-q", "-c")
MAXIMUM_RAW_BYTES = 256 * 1024**3
MAXIMUM_COMPRESSED_BYTES = 16 * 1024**3
CODEC_ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


class ArchiveLimitExceeded(ValueError):
    """No complete storage receipt is produced when a declared bound is hit."""


def prepare_zstd_codec():
    """Copy one installed ordinary binary into this batch; never install/change it."""
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Prepare the archive codec only as the ordinary project user")
    if CODEC_MANIFEST.exists():
        value = reference(CODEC_MANIFEST)
        _checked_codec(value)
        return value
    if CODEC_ROOT.is_symlink():
        raise ValueError("The owned codec directory cannot be a symlink")
    CODEC_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = stream_reference(CODEC_SOURCE)
    if CODEC_BINARY.is_symlink():
        raise ValueError("The owned codec binary cannot be a symlink")
    if not CODEC_BINARY.exists():
        sha, size = hashlib.sha256(), 0
        with CODEC_SOURCE.open("rb") as input_stream, CODEC_BINARY.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            for chunk in iter(lambda: input_stream.read(BLOCK), b""):
                sha.update(chunk)
                size += len(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
            if sha.hexdigest() != source["sha256"] or size != source["bytes"]:
                raise ValueError("Installed codec changed while copying; do not execute the copy")
            os.fchmod(output.fileno(), 0o700)
    binary = stream_reference(CODEC_BINARY)
    if (any(binary[key] != source[key] for key in ("sha256", "bytes"))
            or CODEC_BINARY.stat().st_uid != os.getuid() or not os.access(CODEC_BINARY, os.X_OK)):
        raise ValueError("Existing owned codec is not the same executable bytes as its source")
    result = subprocess.run([str(CODEC_BINARY), "--version"], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=10, check=True, env=CODEC_ENVIRONMENT)
    version = result.stdout.decode("utf-8", "strict").strip()
    if "v1.4.8," not in version:
        raise ValueError("Only the reviewed zstd 1.4.8 codec is prepared")
    return write_new(CODEC_MANIFEST, {
        "version": CODEC_VERSION, "source": source, "binary": binary,
        "version_output": version, "compression_arguments": list(COMPRESSION_ARGUMENTS),
        "decompression_arguments": list(DECOMPRESSION_ARGUMENTS),
        "maximum_raw_bytes": MAXIMUM_RAW_BYTES, "maximum_compressed_bytes": MAXIMUM_COMPRESSED_BYTES,
        "ordinary_user_copy": True, "system_installation_changed": False,
        "model_calls": 0, "docker_operations": 0, "network_operations": 0,
    })


def _checked_codec(manifest_ref):
    """Only the fixed copied binary may execute; storage cannot supply commands."""
    if manifest_ref.get("path") != str(CODEC_MANIFEST.resolve()) or CODEC_ROOT.is_symlink():
        raise ValueError("Archive codec must be the fixed owned batch copy")
    import json
    value = json.loads(checked(manifest_ref).read_bytes())
    binary = value.get("binary", {})
    source = value.get("source", {})
    if (value.get("version") != CODEC_VERSION or binary.get("path") != str(CODEC_BINARY.resolve())
            or CODEC_BINARY.is_symlink() or source.get("path") != str(CODEC_SOURCE.resolve())
            or any(binary.get(key) != source.get(key) for key in ("sha256", "bytes"))
            or "v1.4.8," not in value.get("version_output", "")
            or value.get("compression_arguments") != list(COMPRESSION_ARGUMENTS)
            or value.get("decompression_arguments") != list(DECOMPRESSION_ARGUMENTS)
            or value.get("maximum_raw_bytes") != MAXIMUM_RAW_BYTES
            or value.get("maximum_compressed_bytes") != MAXIMUM_COMPRESSED_BYTES
            or value.get("ordinary_user_copy") is not True
            or value.get("system_installation_changed") is not False
            or CODEC_BINARY.stat().st_uid != os.getuid()
            or not os.access(CODEC_BINARY, os.X_OK)
            or stream_reference(CODEC_BINARY) != binary):
        raise ValueError("Frozen owned archive codec identity or arguments changed")
    return CODEC_BINARY


def _stop_owned_codec(process):
    """Only this Popen child is signalled; no namespace or process-tree scans."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _codec_error(stderr):
    stderr.seek(0, os.SEEK_END)
    stderr.seek(max(0, stderr.tell() - 65536))
    return stderr.read().decode("utf-8", "backslashreplace")


def export_compressed_stream(chunks, target, *, allowed_root, codec_manifest=None,
                             maximum_raw_bytes=MAXIMUM_RAW_BYTES,
                             maximum_compressed_bytes=MAXIMUM_COMPRESSED_BYTES):
    """Consume bytes once, stream zstd to an exclusive new target, and bind both SHAs.

    ``chunks`` is a caller-owned bounded producer such as Docker get_archive.
    No Docker/API operation is performed here. A failed export raises and keeps
    only its incomplete new compressed file; it never fabricates missing usage.
    The returned receipt is not round-trip proof until open_verified_archive
    exits successfully, normally during the caller's required selective extract.
    """
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Archive export must run as the ordinary project user")
    if (type(maximum_raw_bytes) is not int or not 0 < maximum_raw_bytes <= MAXIMUM_RAW_BYTES
            or type(maximum_compressed_bytes) is not int
            or not 0 < maximum_compressed_bytes <= MAXIMUM_COMPRESSED_BYTES):
        raise ValueError("Archive bounds may only tighten the 256-GiB raw/16-GiB compressed limits")
    path, scope = Path(target), Path(allowed_root).resolve()
    if path.is_symlink():
        raise ValueError("New archive target must not be a symlink")
    path = path.resolve()
    if not path.is_relative_to(scope) or path.suffix != ".zst" or not path.parent.is_dir():
        raise ValueError("A new .zst target must stay in an existing owned output directory")
    codec_ref = codec_manifest or prepare_zstd_codec()
    binary = _checked_codec(codec_ref)
    raw_sha, packed_sha = hashlib.sha256(), hashlib.sha256()
    raw_size = packed_size = count = 0
    process = None
    iterator = iter(chunks)
    complete = False
    started = time.monotonic()
    try:
        with path.open("xb") as output, tempfile.TemporaryFile() as stderr:
            os.fchmod(output.fileno(), 0o600)
            process = subprocess.Popen([str(binary), *COMPRESSION_ARGUMENTS], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=stderr, env=CODEC_ENVIRONMENT, close_fds=True)
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            pending = memoryview(b"")
            input_closed = output_closed = False
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while not output_closed:
                    if not pending and not input_closed:
                        try:
                            chunk = next(iterator)
                        except StopIteration:
                            process.stdin.close()
                            input_closed = True
                        else:
                            if not isinstance(chunk, bytes):
                                raise TypeError("Archive producers must yield raw bytes")
                            if raw_size + len(chunk) > maximum_raw_bytes:
                                raise ArchiveLimitExceeded("Raw archive exceeds its 256-GiB-or-lower declared bound")
                            raw_sha.update(chunk)
                            raw_size += len(chunk)
                            count += 1
                            pending = memoryview(chunk)
                            if pending:
                                selector.register(process.stdin, selectors.EVENT_WRITE)
                            else:
                                continue
                    events = selector.select(timeout=1)
                    if not events and process.poll() is not None:
                        raise RuntimeError("Archive codec exited before complete input/output transfer: " + _codec_error(stderr))
                    for key, _ in events:
                        if key.fileobj is process.stdout:
                            chunk = os.read(process.stdout.fileno(), BLOCK)
                            if not chunk:
                                selector.unregister(process.stdout)
                                output_closed = True
                                break
                            if packed_size + len(chunk) > maximum_compressed_bytes:
                                raise ArchiveLimitExceeded("Compressed archive exceeds its 16-GiB-or-lower declared bound")
                            output.write(chunk)
                            packed_sha.update(chunk)
                            packed_size += len(chunk)
                        else:
                            try:
                                written = os.write(process.stdin.fileno(), pending[:BLOCK])
                            except BlockingIOError:
                                continue
                            if written <= 0:
                                raise RuntimeError("Archive codec stopped accepting its original stream")
                            pending = pending[written:]
                            if not pending:
                                selector.unregister(process.stdin)
            if not input_closed or pending:
                raise RuntimeError("Archive codec ended before the entire raw stream was sent")
            if process.wait(timeout=10) != 0:
                raise RuntimeError("Archive compression failed: " + _codec_error(stderr))
            output.flush()
            os.fsync(output.fileno())
            fd_stat, path_stat = os.fstat(output.fileno()), path.stat()
            if (fd_stat.st_dev, fd_stat.st_ino, fd_stat.st_size) != (path_stat.st_dev, path_stat.st_ino, packed_size):
                raise ValueError("Owned compressed archive changed while being written")
            complete = True
    finally:
        _stop_owned_codec(process)
        if process is not None:
            for pipe in (process.stdin, process.stdout):
                if pipe is not None:
                    pipe.close()
        if not complete:
            closer = getattr(iterator, "close", None)
            if closer is not None:
                closer()
    return {"version": VERSION, "encoding": "zstd", "codec_manifest": codec_ref,
            "blob": {"path": str(path), "sha256": packed_sha.hexdigest(), "bytes": packed_size},
            "decompressed_bytes": raw_size, "decompressed_sha256": raw_sha.hexdigest(),
            "raw_archive_materialized": False, "raw_transport_removed": False,
            "streaming_export_complete": True, "round_trip_verified": False,
            "verification_required": "open_verified_archive must successfully drain and verify the full raw stream",
            "limits": {"maximum_raw_bytes": maximum_raw_bytes,
                       "maximum_compressed_bytes": maximum_compressed_bytes},
            "producer_chunks": count, "wall_seconds": time.monotonic() - started,
            "candidate_or_call_records_changed": False}


def stream_reference(path):
    path = Path(path).resolve()
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": size}


class MeasuredReader(io.RawIOBase):
    def __init__(self, stream, maximum):
        self.stream, self.maximum = stream, maximum
        self.digest, self.size = hashlib.sha256(), 0

    def readable(self):
        return True

    def read(self, size=-1):
        value = self.stream.read(size)
        self.size += len(value)
        if self.size > self.maximum:
            raise ValueError("Archive expands beyond its sealed original byte count")
        self.digest.update(value)
        return value

    def readinto(self, buffer):
        value = self.read(len(buffer))
        buffer[:len(value)] = value
        return len(value)


@contextmanager
def _decompressed_stream(storage):
    if storage["encoding"] == "gzip":
        with gzip.open(storage["blob"]["path"], "rb") as stream:
            yield stream
        return
    binary = _checked_codec(storage["codec_manifest"])
    process = None
    try:
        with Path(storage["blob"]["path"]).open("rb") as source, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen([str(binary), *DECOMPRESSION_ARGUMENTS],
                stdin=source, stdout=subprocess.PIPE, stderr=stderr,
                env=CODEC_ENVIRONMENT, close_fds=True)
            yield process.stdout
            if process.wait(timeout=10) != 0:
                raise ValueError("Compressed zstd archive failed decoding: " + _codec_error(stderr))
    finally:
        _stop_owned_codec(process)
        if process is not None and process.stdout is not None:
            process.stdout.close()


@contextmanager
def open_verified_archive(storage):
    """Yield a sequential raw-tar stream; verify full bytes even after early reads."""
    if (storage.get("version") != VERSION or storage.get("encoding") not in {"gzip", "zstd"}
            or type(storage.get("decompressed_bytes")) is not int
            or storage["decompressed_bytes"] < 0):
        raise ValueError("Unrecognized exact archive storage")
    if storage["encoding"] == "zstd":
        limits = storage.get("limits", {})
        maximum_raw, maximum_compressed = (limits.get(key) for key in
                                          ("maximum_raw_bytes", "maximum_compressed_bytes"))
        if (type(maximum_raw) is not int or not 0 < maximum_raw <= MAXIMUM_RAW_BYTES
                or storage["decompressed_bytes"] > maximum_raw
                or type(maximum_compressed) is not int
                or not 0 < maximum_compressed <= MAXIMUM_COMPRESSED_BYTES
                or type(storage.get("blob", {}).get("bytes")) is not int
                or not 0 < storage["blob"]["bytes"] <= maximum_compressed):
            raise ValueError("Zstd archive exceeds its fixed raw/compressed storage bounds")
    if stream_reference(storage["blob"]["path"]) != storage["blob"]:
        raise ValueError("Compressed transport archive changed")
    with _decompressed_stream(storage) as compressed:
        reader = MeasuredReader(compressed, storage["decompressed_bytes"])
        try:
            yield reader
        finally:
            while reader.read(BLOCK):
                pass
            if (reader.size != storage["decompressed_bytes"]
                    or reader.digest.hexdigest() != storage["decompressed_sha256"]):
                raise ValueError("Decompressed archive differs from the original exact transfer")


def compress_transport_archive(path, expected, *, allowed_root):
    """Remove only the redundant own raw tar, after a complete verified roundtrip."""
    if Path(path).is_symlink():
        raise ValueError("A temporary archive must be an ordinary owned file")
    path, allowed_root = Path(path).resolve(), Path(allowed_root).resolve()
    if (not path.is_relative_to(allowed_root) or path.suffix != ".tar"
            or expected.get("path") != str(path) or path.is_symlink()):
        raise ValueError("Only this new batch's exact temporary tar may be compacted")
    target = path.with_suffix(".tar.gz")
    digest, size = hashlib.sha256(), 0
    with target.open("xb") as output:
        os.chmod(target, 0o600)
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", compresslevel=3, mtime=0) as packed:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(BLOCK), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    packed.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError("Original archive changed during compression; retain it for diagnosis")
    result = {"version": VERSION, "encoding": "gzip", "blob": stream_reference(target),
              "decompressed_bytes": size, "decompressed_sha256": digest.hexdigest(),
              "raw_transport_removed": True, "round_trip_verified": True,
              "candidate_or_call_records_changed": False}
    with open_verified_archive(result):
        pass
    path.unlink()
    return result


def retain_baseline(bundle, target, store):
    """Only byte-identical baseline JSON shares an inode; task paths stay intact."""
    target, store = Path(target), Path(store)
    raw = json_bytes(bundle)
    sha = hashlib.sha256(raw).hexdigest()
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    shared = store / (sha + ".json")
    with (store / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if shared.exists():
            if shared.read_bytes() != raw:
                raise ValueError("Immutable baseline content address differs")
        else:
            write_new(shared, raw)
        os.link(shared, target, follow_symlinks=False)
    return reference(target)
