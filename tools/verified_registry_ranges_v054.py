"""Bounded shared CDN range pool for already pinned Verified image blobs.

Credentials and signed URLs remain in memory. Completed bytes survive pauses;
the authoritative verification is one complete SHA256 during final assembly.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse

try:
    from . import domestic_asset_download as asset
    from .domestic_registry_blob import POLICY, USER_AGENT
    from .verified_image_metadata_v054 import Metadata
except ImportError:
    import domestic_asset_download as asset
    from domestic_registry_blob import POLICY, USER_AGENT
    from verified_image_metadata_v054 import Metadata


def now():
    return datetime.now(timezone.utc).isoformat()


def checked_range(response, start, end, size):
    if response.getcode() != 206:
        raise asset.DownloadPaused("Range request did not return HTTP 206")
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
    if match is None or tuple(map(int, match.groups())) != (start, end, size):
        raise asset.DownloadPaused("Range Content-Range differs from pinned interval")
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise asset.DownloadPaused("Range transport content encoding changed")
    if response.headers.get("Content-Length") not in (None, str(end - start + 1)):
        raise asset.DownloadPaused("Range Content-Length differs from pinned interval")


class RangePool:
    def __init__(self, workers=16, chunk_bytes=4 * 1024 * 1024):
        if not 1 <= workers <= 32 or not 1024 * 1024 <= chunk_bytes <= 8 * 1024 * 1024:
            raise ValueError("invalid bounded range pool")
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="v054-cdn")
        self.slots = threading.BoundedSemaphore(workers)
        self.stop = threading.Event()
        self.chunk_bytes = chunk_bytes
        self.workers = workers

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)

    def download(self, image, digest, output, *, expected_bytes):
        output = Path(output)
        if not re.fullmatch(r"swebench/[a-z0-9][a-z0-9_.-]*", image):
            raise asset.DownloadPaused("Invalid pinned image name")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or expected_bytes <= 0:
            raise asset.DownloadPaused("Invalid pinned blob identity")
        output.parent.mkdir(parents=True, exist_ok=True)
        policy, policy_sha = asset.load_policy(POLICY)
        source = f"https://docker.1ms.run/v2/{image}/blobs/{digest}"
        receipt_path = output.with_name(output.name + ".verified.json")
        directory = output.with_name(output.name + ".ranges")
        directory.mkdir(exist_ok=True)
        ledger_path = directory / "ledger.json"
        lock_path = output.with_name(output.name + ".download.lock")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if output.exists():
                reused = asset.verified_file(
                    output, receipt_path, expected_sha256=digest.split(":")[1],
                    expected_bytes=expected_bytes, chunk_bytes=1024 * 1024)
                return {"status": "existing_verified", "path": str(output),
                        "bytes": expected_bytes, "verification": reused}
            identity = {
                "schema": "proworksim.verified-range-ledger.v054", "source_url": source,
                "sha256": digest.split(":")[1], "bytes": expected_bytes,
                "chunk_bytes": self.chunk_bytes, "policy_sha256": policy_sha,
            }
            if ledger_path.exists():
                ledger = json.loads(ledger_path.read_bytes())
                if any(ledger.get(key) != value for key, value in identity.items()):
                    raise asset.DownloadPaused("Range ledger identity changed")
            else:
                ledger = {**identity, "created_at_utc": now(), "events": [], "segments": {}}
            ledger_lock = threading.Lock()

            def event(kind, **values):
                clean = {}
                for key, value in values.items():
                    if key.endswith("url"):
                        parsed = urllib.parse.urlsplit(value)
                        clean[key] = urllib.parse.urlunsplit(
                            (parsed.scheme, parsed.netloc, parsed.path, "", ""))
                    else:
                        clean[key] = value
                with ledger_lock:
                    ledger["events"].append({"event": kind, "at_utc": now(), **clean})
                    asset.atomic_json(ledger_path, ledger)

            event("resume", global_cdn_limit=self.workers, proxy_used=False)
            prefix_path = output.with_name(output.name + ".part")
            prefix_bytes = 0
            if prefix_path.exists():
                saved = json.loads(prefix_path.with_name(prefix_path.name + ".json").read_bytes())
                prefix_bytes = prefix_path.stat().st_size
                permitted_prefix_sources = {
                    source, f"https://docker.apiba.cn/v2/{image}/blobs/{digest}",
                }
                if (saved.get("source_url") not in permitted_prefix_sources
                        or saved.get("version") != "domestic-asset-download-v1"
                        or saved.get("expected_bytes") != expected_bytes
                        or saved.get("expected_sha256") != digest.split(":")[1]
                        or saved.get("partial_bytes") != prefix_bytes
                        or asset.file_hasher(prefix_path, 1024 * 1024).hexdigest()
                        != saved.get("partial_sha256")):
                    raise asset.DownloadPaused("Existing sequential prefix verification failed")
                event("reuse_sequential_prefix", bytes=prefix_bytes,
                      original_source_url=saved["source_url"],
                      original_partial_sha256=saved["partial_sha256"])
            intervals = [
                (start, min(start + self.chunk_bytes, expected_bytes) - 1)
                for start in range(prefix_bytes, expected_bytes, self.chunk_bytes)]
            if any(start < 0 or end < start for start, end in intervals):
                raise asset.DownloadPaused("Invalid missing-byte ranges")

            def segment_path(start, end):
                return directory / f"{start:014d}-{end:014d}.part"

            def segment_offset(start, end):
                path = segment_path(start, end)
                length = path.stat().st_size if path.exists() else 0
                if length > end - start + 1:
                    raise asset.DownloadPaused("Existing range segment exceeds pinned length")
                return start + length

            def transfer(start, end, url, headers):
                if self.stop.is_set():
                    raise asset.DownloadPaused("Range pool stopped after public fault")
                offset = segment_offset(start, end)
                if offset > end:
                    return url
                response = None
                try:
                    with self.slots:
                        response, final_url = asset.open_response(
                            asset.direct_opener(), url,
                            {"User-Agent": USER_AGENT, "Accept": "application/octet-stream",
                             "Accept-Encoding": "identity", "Range": f"bytes={offset}-{end}",
                             **headers}, policy, event)
                        checked_range(response, offset, end, expected_bytes)
                        original_offset = offset
                        with segment_path(start, end).open("ab") as stream:
                            while offset <= end:
                                block = response.read(min(1024 * 1024, end - offset + 1))
                                if not block:
                                    raise asset.DownloadPaused("Range body ended before declared interval")
                                stream.write(block)
                                offset += len(block)
                            if response.read(1):
                                raise asset.DownloadPaused("Range body exceeds declared interval")
                            stream.flush()
                            os.fsync(stream.fileno())
                        with ledger_lock:
                            ledger["segments"][str(start)] = {
                                "start": start, "end": end, "bytes": end - start + 1,
                                "last_received_bytes": offset - original_offset,
                                "file_identity": asset.file_identity(segment_path(start, end)),
                            }
                            asset.atomic_json(ledger_path, ledger)
                        return final_url
                except Exception as error:
                    cause = error.__cause__
                    retry_after = (cause.headers.get("Retry-After")
                                   if isinstance(cause, urllib.error.HTTPError) else None)
                    event("range_paused", start=start, end=end,
                          saved_bytes=segment_offset(start, end) - start,
                          error_type=type(error).__name__,
                          http_status=getattr(cause, "code", None),
                          retry_after=retry_after[:200] if retry_after else None)
                    self.stop.set()
                    raise
                finally:
                    if response is not None:
                        response.close()

            missing = [(start, end) for start, end in intervals if segment_offset(start, end) <= end]
            futures = []
            try:
                if missing:
                    # One registry authentication and redirect resolution per blob.
                    token = Metadata("mirror").token(image)
                    first_start, first_end = missing[0]
                    cdn_url = transfer(
                        first_start, first_end, source, {"Authorization": "Bearer " + token})
                    if urllib.parse.urlsplit(cdn_url).hostname != "cloudfront-docker-cf.mrs.1ms.run":
                        raise asset.DownloadPaused("Range pool requires the approved CDN delivery host")
                    token = None
                    futures = [self.executor.submit(transfer, start, end, cdn_url, {})
                               for start, end in missing[1:]]
                    for future in as_completed(futures):
                        future.result()
            except Exception:
                self.stop.set()
                for future in futures:
                    future.cancel()
                # Retain running ranges until their bounded current request closes.
                for future in futures:
                    if not future.cancelled():
                        try:
                            future.result()
                        except Exception:
                            pass
                raise
            assembling = output.with_name(output.name + ".assembling")
            if assembling.exists():
                assembling.unlink()
            hasher = hashlib.sha256()
            with assembling.open("xb") as target:
                sources = ([prefix_path] if prefix_bytes else []) + [
                    segment_path(start, end) for start, end in intervals]
                for path in sources:
                    with path.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            hasher.update(block)
                            target.write(block)
                target.flush()
                os.fsync(target.fileno())
            if assembling.stat().st_size != expected_bytes or hasher.hexdigest() != digest.split(":")[1]:
                event("complete_hash_mismatch", observed_bytes=assembling.stat().st_size)
                self.stop.set()
                raise asset.DownloadPaused("Assembled blob SHA256 or size differs from official manifest")
            os.replace(assembling, output)
            asset.atomic_json(receipt_path, {
                "version": "domestic-asset-complete-verification-v1",
                "expected_sha256": digest.split(":")[1], "expected_bytes": expected_bytes,
                "file_identity": asset.file_identity(output), "verified_at_utc": now(),
                "verification": "range_assembly_complete_sha256", "range_ledger": str(ledger_path),
            })
            event("complete_verified", bytes=expected_bytes, sha256=digest.split(":")[1])
            # Only this transfer's temporary byte segments are removed; evidence remains.
            for start, end in intervals:
                segment_path(start, end).unlink()
            if prefix_bytes:
                prefix_path.unlink()
            return {"status": "download_complete", "path": str(output), "bytes": expected_bytes,
                    "sha256": digest.split(":")[1], "range_ledger": str(ledger_path)}
