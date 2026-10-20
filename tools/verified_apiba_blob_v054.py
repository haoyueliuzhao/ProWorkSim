"""Full pinned blob transfers through the tested APIBA registry endpoint.

This endpoint ignored Range in the recorded probe, so partials are preserved
and never restarted here. No redirects, proxies, origin fallback or retries.
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
import urllib.error
import urllib.parse
import urllib.request

try:
    from . import domestic_asset_download as asset
except ImportError:
    import domestic_asset_download as asset

HOST = "docker.apiba.cn"
USER_AGENT = "ProWorkSim-source-preparation/0.54"


def _get(url, headers):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment):
        raise asset.DownloadPaused("APIBA exact endpoint required")
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept-Encoding": "identity", **headers})
    try:
        response = asset.direct_opener().open(request, timeout=60)
    except urllib.error.HTTPError as error:
        error.close()
        raise asset.DownloadPaused(
            f"APIBA HTTP {error.code}; no redirect, retry or fallback") from error
    if response.getcode() != 200:
        response.close()
        raise asset.DownloadPaused("APIBA requires HTTP 200")
    return response


def download_blob(image, digest, output, *, expected_bytes):
    if (not re.fullmatch(r"swebench/[a-z0-9][a-z0-9_.-]*", image)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or type(expected_bytes) is not int or expected_bytes < 0):
        raise asset.DownloadPaused("Invalid pinned APIBA blob identity")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    source = f"https://{HOST}/v2/{image}/blobs/{digest}"
    receipt = output.with_name(output.name + ".verified.json")
    partial = output.with_name(output.name + ".part")
    partial_receipt = output.with_name(output.name + ".part.json")
    event_path = output.with_name(output.name + ".apiba.jsonl")
    identity = {"version": "domestic-asset-download-v1", "source_url": source,
                "expected_sha256": digest.split(":")[1], "expected_bytes": expected_bytes}

    def event(kind, **details):
        with event_path.open("a") as stream:
            stream.write(json.dumps({
                **identity, "event": kind, "at_utc": datetime.now(timezone.utc).isoformat(),
                "proxy_used": False, "redirects_followed": 0, **details,
            }, sort_keys=True) + "\n")

    with output.with_name(output.name + ".download.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if output.exists():
            reuse = asset.verified_file(
                output, receipt, expected_sha256=identity["expected_sha256"],
                expected_bytes=expected_bytes, chunk_bytes=1024 * 1024)
            return {"status": "existing_verified", "path": str(output), "verification": reuse}
        if partial.exists() and partial.stat().st_size:
            raise asset.DownloadPaused("APIBA Range unsupported; preserve existing partial without re-download")
        auth = f"https://{HOST}/token?" + urllib.parse.urlencode({
            "service": "registry.docker.io", "scope": f"repository:{image}:pull"})
        hasher, size, response = hashlib.sha256(), 0, None
        try:
            with _get(auth, {"Accept": "application/json"}) as token_response:
                body = token_response.read(128 * 1024 + 1)
                if len(body) > 128 * 1024:
                    raise asset.DownloadPaused("APIBA auth metadata exceeds bound")
                parsed = json.loads(body)
                token = parsed.get("token") or parsed.get("access_token")
                if (not isinstance(token, str) or not token
                        or any(ord(char) < 33 or ord(char) > 126 for char in token)):
                    raise asset.DownloadPaused("APIBA auth token invalid")
            event("authenticated", auth_response_body_retained=False)
            response = _get(source, {"Authorization": "Bearer " + token,
                                     "Accept": "application/octet-stream"})
            token = None
            asset.validate_response(response, offset=0, expected_bytes=expected_bytes)
            event("transfer_started", http_status=200, expected_bytes=expected_bytes)
            with partial.open("wb") as stream:
                while size < expected_bytes:
                    block = response.read(min(1024 * 1024, expected_bytes - size))
                    if not block:
                        raise asset.DownloadPaused("APIBA body ended before pinned size")
                    stream.write(block)
                    hasher.update(block)
                    size += len(block)
                    asset.atomic_json(partial_receipt, {
                        **identity, "status": "partial", "partial_bytes": size,
                        "partial_sha256": hasher.hexdigest(),
                    })
                if response.read(1):
                    raise asset.DownloadPaused("APIBA body exceeds pinned size")
                stream.flush()
                os.fsync(stream.fileno())
            if hasher.hexdigest() != identity["expected_sha256"]:
                raise asset.DownloadPaused("APIBA complete SHA256 differs from official manifest")
            os.replace(partial, output)
            asset.atomic_json(receipt, {
                "version": "domestic-asset-complete-verification-v1",
                "expected_sha256": identity["expected_sha256"], "expected_bytes": expected_bytes,
                "file_identity": asset.file_identity(output),
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "verification": "apiba_complete_download_incremental_sha256",
            })
            event("complete_verified", bytes=size, sha256=hasher.hexdigest())
            return {"status": "download_complete", "path": str(output), "bytes": size,
                    "sha256": hasher.hexdigest(), "source": HOST}
        except Exception as error:
            cause = error.__cause__
            event("paused", received_bytes=size, error_type=type(error).__name__,
                  http_status=getattr(cause, "code", None),
                  retry_after=getattr(cause, "headers", {}).get("Retry-After"))
            raise
        finally:
            if response is not None:
                response.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(download_blob(
        args.image, args.digest, args.output, expected_bytes=args.expected_bytes)))


if __name__ == "__main__":
    main()
