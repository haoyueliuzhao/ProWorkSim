"""Download one manifest-pinned SWE-smith blob through the documented 1ms route.

No latest lookup, image pull, model run, origin fallback or automatic retry.
Registry authentication stays in memory and never reaches a different origin.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

try:
    from . import domestic_asset_download as asset
except ImportError:  # Direct `python tools/domestic_registry_blob.py`.
    import domestic_asset_download as asset

HOST = "docker.1ms.run"
POLICY = Path(__file__).resolve().parents[1] / "config/domestic-registry-download-policy.json"
AUTH_BYTES_LIMIT = 128 * 1024
USER_AGENT = "ProWorkSim-domestic-asset/1"


def download_blob(image, digest, output, *, expected_bytes, log_path=None):
    if (not isinstance(image, str)
            or re.fullmatch(r"swebench/[a-z0-9]+(?:[._-][a-z0-9]+)*", image) is None):
        raise asset.DownloadPaused("Use a fixed swebench/<repository> image name without tag or digest")
    if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is None:
        raise asset.DownloadPaused("Provide the manifest-pinned sha256:<64 hex> blob digest")
    digest = digest.lower()
    url = f"https://{HOST}/v2/{image}/blobs/{digest}"
    auth_log = Path(output).absolute().with_name(Path(output).name + ".registry.jsonl")

    def authentication_headers():
        # asset.download invokes this only after its own policy, pin, cache and
        # partial verification, under the destination lock and only if needed.
        auth_url = f"https://{HOST}/openapi/v1/auth/token?" + urllib.parse.urlencode({
            "service": HOST, "scope": f"repository:{image}:pull",
        })
        record = {
            "event": "anonymous_registry_authentication",
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "registry": HOST, "image": image,
            "auth_endpoint": f"https://{HOST}/openapi/v1/auth/token",
            "environment_proxy_used": False, "automatic_redirects": False,
            "response_body_limit_bytes": AUTH_BYTES_LIMIT,
            "token_or_auth_response_retained": False,
        }
        try:
            request = urllib.request.Request(auth_url, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json",
                "Accept-Encoding": "identity",
            })
            try:
                response = asset.direct_opener().open(request, timeout=60)
            except urllib.error.HTTPError as error:
                record["http_status"] = error.code
                error.close()
                raise asset.DownloadPaused(
                    f"Registry authentication HTTP {error.code}; no redirect, retry or fallback") from None
            with response:
                record["http_status"] = response.getcode()
                if response.getcode() != 200:
                    raise asset.DownloadPaused("Registry authentication requires HTTP 200")
                if response.headers.get("Content-Encoding", "identity").lower().strip() != "identity":
                    raise asset.DownloadPaused("Registry authentication content encoding is unsupported")
                body = response.read(AUTH_BYTES_LIMIT)
                record["response_body_bytes"] = len(body)
                if len(body) == AUTH_BYTES_LIMIT:
                    raise asset.DownloadPaused("Registry authentication exceeded its metadata bound")
                data = json.loads(body)
                token = (data.get("token") or data.get("access_token")) if isinstance(data, dict) else None
                if (not isinstance(token, str) or not token
                        or any(ord(character) < 33 or ord(character) > 126 for character in token)):
                    raise asset.DownloadPaused("Registry authentication returned no valid bearer")
            record["status"] = "authenticated"
            return {"Authorization": "Bearer " + token}
        except Exception as error:
            # Never include a response body or parser excerpt in an exception.
            record["status"] = "paused"
            record["error_type"] = type(error).__name__
            if isinstance(error, asset.DownloadPaused):
                raise
            raise asset.DownloadPaused(
                f"Registry authentication {type(error).__name__}; no retry or fallback") from None
        finally:
            auth_log.parent.mkdir(parents=True, exist_ok=True)
            with auth_log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    return asset.download(
        url, output, expected_sha256=digest.split(":", 1)[1], expected_bytes=expected_bytes,
        policy_path=POLICY, log_path=log_path, request_headers=authentication_headers)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--expected-bytes", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--log")
    args = parser.parse_args(argv)
    try:
        result = download_blob(
            args.image, args.digest, args.output,
            expected_bytes=args.expected_bytes, log_path=args.log)
    except asset.DownloadPaused as error:
        print(json.dumps({"status": "paused", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
