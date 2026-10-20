"""Download one pinned asset through an explicit HTTPS mirror allowlist.

This independent entry does not alter a running experiment or its frozen code.
No origin fallback, automatic retry, proxy inheritance or unvalidated redirect
is permitted. Endpoint candidates are configured, not certified by this tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

VERSION = "domestic-asset-download-v1"
POLICY_VERSION = "domestic-asset-download-policy-v1"
HOST_CANDIDATES = frozenset({
    "modelscope.cn", "www.modelscope.cn", "cdn-lfs-cn-1.modelscope.cn", "hf-mirror.com",
})
DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "config/domestic-download-policy.json"
REDIRECTS = frozenset({301, 302, 303, 307, 308})


class DownloadPaused(RuntimeError):
    """Preserve files and stop; never silently retry or switch sources."""


class NoAutomaticRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def direct_opener():
    # Passing an explicit empty dict avoids getproxies()/proxy environment use.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoAutomaticRedirect())


def load_policy(path):
    content = Path(path).read_bytes()
    policy = json.loads(content)
    hosts = policy.get("allowed_https_hosts")
    if (policy.get("version") != POLICY_VERSION
            or not isinstance(hosts, list) or not hosts
            or not set(hosts) <= HOST_CANDIDATES
            or any(policy.get(key) is not False for key in
                   ("inherit_environment_proxy", "allow_origin_fallback", "allow_http"))
            or policy.get("endpoint_status") != "configuration_candidates_not_network_verified"):
        raise DownloadPaused("Policy must keep the exact candidate-host, HTTPS and direct-connection restrictions")
    for key, maximum in (("max_redirects", 10), ("socket_timeout_seconds", 300),
                         ("chunk_bytes", 8 * 1024 * 1024)):
        if type(policy.get(key)) is not int or not 1 <= policy[key] <= maximum:
            raise DownloadPaused("Invalid bounded policy value: " + key)
    return policy, hashlib.sha256(content).hexdigest()


def validate_url(url, policy):
    if not isinstance(url, str) or any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise DownloadPaused("URL must not contain control characters")
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (
            parsed.scheme == "https" and parsed.hostname in policy["allowed_https_hosts"]
            and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
            and not parsed.fragment
        )
    except ValueError as error:
        raise DownloadPaused("Invalid URL") from error
    if not valid:
        raise DownloadPaused("URL is outside the configured HTTPS candidate-host policy")
    return url


def file_hasher(path, chunk_bytes):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            hasher.update(block)
    return hasher


def atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".download-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def file_identity(path):
    stat = Path(path).stat()
    return {
        "dev": stat.st_dev, "ino": stat.st_ino, "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "ctime_ns": stat.st_ctime_ns,
    }


def verified_file(path, receipt_path, *, expected_sha256, expected_bytes, chunk_bytes):
    """Reuse completed content verification while its exact file identity holds."""
    before = file_identity(path)
    if not path.is_file() or before["size"] != expected_bytes:
        raise DownloadPaused("Existing destination does not match the pinned size; no overwrite")
    try:
        saved = json.loads(receipt_path.read_bytes())
    except (OSError, ValueError):
        saved = {}
    expected = {
        "version": "domestic-asset-complete-verification-v1",
        "expected_sha256": expected_sha256, "expected_bytes": expected_bytes,
        "file_identity": before,
    }
    if isinstance(saved, dict) and all(saved.get(key) == value for key, value in expected.items()):
        return "cached_file_identity"
    if file_hasher(path, chunk_bytes).hexdigest() != expected_sha256:
        raise DownloadPaused("Existing destination does not match the pinned SHA256; no overwrite")
    if file_identity(path) != before:
        raise DownloadPaused("Existing destination changed during its necessary hash verification")
    atomic_json(receipt_path, {**expected, "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                              "verification": "existing_file_full_sha256"})
    return "necessary_local_sha256"


def open_response(opener, url, headers, policy, emit):
    current = validate_url(url, policy)
    for redirect_count in range(policy["max_redirects"] + 1):
        emit("request", url=current, range=headers.get("Range"))
        request = urllib.request.Request(current, headers=headers, method="GET")
        try:
            response = opener.open(request, timeout=policy["socket_timeout_seconds"])
        except urllib.error.HTTPError as error:
            if error.code not in REDIRECTS:
                error.close()
                raise DownloadPaused(f"HTTP {error.code}; no retry or fallback") from error
            response = error
        code = response.getcode()
        if code not in REDIRECTS:
            return response, current
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise DownloadPaused("Redirect has no Location")
        target = urllib.parse.urljoin(current, location)
        try:
            validate_url(target, policy)
        except DownloadPaused:
            emit("redirect_refused", source_url=current, target_url=target)
            raise
        if redirect_count == policy["max_redirects"]:
            raise DownloadPaused("Redirect limit reached; no additional request")
        emit("redirect_allowed", source_url=current, target_url=target)
        current = target
    raise AssertionError("Unreachable redirect loop")


def validate_response(response, *, offset, expected_bytes):
    code = response.getcode()
    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise DownloadPaused("Transport content encoding differs from the pinned byte representation")
    remaining = expected_bytes - offset
    if offset:
        if code != 206:
            raise DownloadPaused("Server did not honor the resume Range; existing partial remains unchanged")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if (match is None or tuple(map(int, match.groups()))
                != (offset, expected_bytes - 1, expected_bytes)):
            raise DownloadPaused("Resume Content-Range does not exactly match the pinned remaining bytes")
    elif code != 200 or response.headers.get("Content-Range") is not None:
        raise DownloadPaused("A new transfer requires an ordinary complete HTTP 200 response")
    length = response.headers.get("Content-Length")
    if length is not None:
        try:
            valid_length = int(length) == remaining
        except ValueError:
            valid_length = False
        if not valid_length:
            raise DownloadPaused("Response Content-Length differs from the pinned remaining bytes")


def download(url, output, *, expected_sha256, expected_bytes, policy_path=DEFAULT_POLICY, log_path=None):
    policy, policy_sha256 = load_policy(policy_path)
    validate_url(url, policy)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise DownloadPaused("Provide a fixed 64-hex expected SHA256 before downloading")
    expected_sha256 = expected_sha256.lower()
    if type(expected_bytes) is not int or expected_bytes <= 0:
        raise DownloadPaused("Provide the fixed positive expected byte count before downloading")
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".part")
    checkpoint_path = output.with_name(output.name + ".part.json")
    complete_receipt_path = output.with_name(output.name + ".verified.json")
    log_path = Path(log_path or output.with_name(output.name + ".download.jsonl"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.with_name(output.name + ".download.lock")
    identity = {
        "version": VERSION, "source_url": url, "expected_sha256": expected_sha256,
        "expected_bytes": expected_bytes,
    }
    payload_bytes_received = 0

    def emit(event, **fields):
        record = {
            **identity, "event": event, "at_utc": datetime.now(timezone.utc).isoformat(),
            "policy_sha256": policy_sha256,
            "endpoint_status": policy["endpoint_status"], "environment_proxy_used": False,
            **fields,
        }
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def checkpoint(size, hasher, *, status):
        atomic_json(checkpoint_path, {
            **identity, "partial_bytes": size, "partial_sha256": hasher.hexdigest(), "status": status,
        })

    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DownloadPaused("Another writer owns this exact destination") from error
        try:
            if output.exists():
                verification = verified_file(
                    output, complete_receipt_path, expected_sha256=expected_sha256,
                    expected_bytes=expected_bytes, chunk_bytes=policy["chunk_bytes"])
                emit("existing_verified", bytes=expected_bytes, sha256=expected_sha256,
                     payload_bytes_received=0, verification=verification)
                return {"status": "existing_verified", "path": str(output),
                        "bytes": expected_bytes, "sha256": expected_sha256,
                        "payload_bytes_received": 0, "verification": verification}
            if output.is_symlink() or partial.is_symlink() or checkpoint_path.is_symlink():
                raise DownloadPaused("Refuse an unresolved destination or mutable partial/checkpoint symlink")
            offset, hasher = 0, hashlib.sha256()
            if partial.exists():
                if not partial.is_file() or not checkpoint_path.is_file():
                    raise DownloadPaused("Existing partial lacks its bound checkpoint; no automatic restart")
                saved = json.loads(checkpoint_path.read_bytes())
                if any(saved.get(key) != value for key, value in identity.items()):
                    raise DownloadPaused("Partial belongs to a different pinned source identity")
                offset = partial.stat().st_size
                if saved.get("partial_bytes") != offset or not 0 <= offset <= expected_bytes:
                    raise DownloadPaused("Partial size differs from its checkpoint; no append or restart")
                hasher = file_hasher(partial, policy["chunk_bytes"])
                if saved.get("partial_sha256") != hasher.hexdigest():
                    raise DownloadPaused("Partial hash differs from its checkpoint; no append or restart")
                emit("partial_verified", partial_bytes=offset, partial_sha256=hasher.hexdigest())
            if offset < expected_bytes:
                headers = {"Accept-Encoding": "identity"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                response, final_url = open_response(direct_opener(), url, headers, policy, emit)
                try:
                    validate_response(response, offset=offset, expected_bytes=expected_bytes)
                    with partial.open("ab" if partial.exists() else "xb") as stream:
                        checkpoint(offset, hasher, status="partial")
                        while True:
                            block = response.read(min(policy["chunk_bytes"], expected_bytes - offset + 1))
                            if not block:
                                break
                            payload_bytes_received += len(block)
                            if offset + len(block) > expected_bytes:
                                raise DownloadPaused("Response exceeds the pinned byte count; extra bytes not appended")
                            stream.write(block)
                            stream.flush()
                            os.fsync(stream.fileno())
                            hasher.update(block)
                            offset += len(block)
                            checkpoint(offset, hasher, status="partial")
                finally:
                    response.close()
                emit("response_closed", final_url=final_url, partial_bytes=offset,
                     payload_bytes_received=payload_bytes_received)
            if offset != expected_bytes:
                raise DownloadPaused("Response ended early; the verified partial is retained for explicit resume")
            if hasher.hexdigest() != expected_sha256:
                checkpoint(offset, hasher, status="hash_mismatch")
                raise DownloadPaused("Complete bytes failed the pinned SHA256; preserved without automatic redownload")
            # Same-directory hard link publishes without replacing a destination
            # another process may have created while this transfer was running.
            os.link(partial, output)
            partial.unlink()
            checkpoint(offset, hasher, status="complete")
            atomic_json(complete_receipt_path, {
                "version": "domestic-asset-complete-verification-v1",
                "expected_sha256": expected_sha256, "expected_bytes": expected_bytes,
                "file_identity": file_identity(output),
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "verification": "complete_download_incremental_sha256",
            })
            emit("download_complete", bytes=offset, sha256=expected_sha256,
                 payload_bytes_received=payload_bytes_received)
            return {"status": "download_complete", "path": str(output), "bytes": offset,
                    "sha256": expected_sha256, "payload_bytes_received": payload_bytes_received}
        except Exception as error:
            emit("paused", error_type=type(error).__name__, reason=str(error),
                 partial_bytes=partial.stat().st_size if partial.is_file() else 0,
                 payload_bytes_received=payload_bytes_received)
            if isinstance(error, DownloadPaused):
                raise
            raise DownloadPaused(f"{type(error).__name__}: {error}; no retry or fallback") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--log")
    args = parser.parse_args(argv)
    try:
        result = download(
            args.url, args.output, expected_sha256=args.expected_sha256,
            expected_bytes=args.expected_bytes, policy_path=args.policy, log_path=args.log)
    except DownloadPaused as error:
        print(json.dumps({"status": "paused", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
