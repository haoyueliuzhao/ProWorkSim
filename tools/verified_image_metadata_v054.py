#!/usr/bin/env python3
"""Pin SWE-bench Verified image manifests; never fetch image layers or use proxies."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from .audit_official_docker_manifests import (
        ACCEPT, INDEX_TYPES, AuditError, RejectRedirects, amd64_descriptor,
        image_descriptors, parse_manifest,
    )
except ImportError:
    from audit_official_docker_manifests import (
        ACCEPT, INDEX_TYPES, AuditError, RejectRedirects, amd64_descriptor,
        image_descriptors, parse_manifest,
    )

NAME = re.compile(r"swebench/sweb\.eval\.x86_64\.[a-z0-9][a-z0-9_.-]*")
MAX_BYTES = 2 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def write_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    with path.open("xb") as stream:
        stream.write(content)


def load_inventory(path):
    body = path.read_bytes()
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("inventory too large")
    value = json.loads(body)
    rows = value["images"]
    if len(rows) != 500 or len({row["instance_id"] for row in rows}) != 500:
        raise ValueError("require all 500 distinct Verified instances")
    for row in rows:
        if not NAME.fullmatch(row["image_name"]) or row["tag"] != "latest":
            raise ValueError("unexpected official Verified image reference")
        if not re.fullmatch(r"[0-9a-f]{40}", row["base_commit"]):
            raise ValueError("base commit must be complete")
    if value["platform"] != {"os": "linux", "architecture": "amd64"}:
        raise ValueError("require linux/amd64")
    return rows, hashlib.sha256(body).hexdigest()


class Metadata:
    def __init__(self, source):
        self.source = source
        self.host = "registry-1.docker.io" if source == "official" else "docker.1ms.run"
        self.auth = ("https://auth.docker.io/token" if source == "official"
                     else "https://docker.1ms.run/openapi/v1/auth/token")
        self.service = "registry.docker.io" if source == "official" else self.host
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), RejectRedirects())
        self.bytes = 0
        self.requests = 0

    def get(self, url, headers, *, auth=False):
        parsed = urllib.parse.urlsplit(url)
        valid = (url.startswith(self.auth + "?") if auth else
                 parsed.hostname == self.host
                 and re.fullmatch(
                     r"/v2/swebench/sweb\.eval\.x86_64\.[a-z0-9_.-]+/manifests/"
                     r"(latest|sha256:[0-9a-f]{64})", parsed.path)
                 and not parsed.query)
        if (not valid or parsed.scheme != "https" or parsed.username
                or parsed.password or parsed.fragment or parsed.port not in (None, 443)):
            raise AuditError("endpoint_not_allowed")
        self.requests += 1
        request = urllib.request.Request(url, headers={
            "User-Agent": "ProWorkSim-Verified-v054/1",
            "Accept-Encoding": "identity", **headers,
        })
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise AuditError(f"http_{response.status}")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise AuditError("encoded_metadata")
                body = response.read(MAX_BYTES + 1)
                self.bytes += len(body)
                if len(body) > MAX_BYTES:
                    raise AuditError("metadata_limit")
                return body, {
                    "docker_content_digest": response.headers.get("Docker-Content-Digest"),
                    "date": response.headers.get("Date"),
                    "content_type": response.headers.get("Content-Type"),
                }
        except urllib.error.HTTPError as error:
            raise AuditError(f"http_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AuditError("metadata_transport_error") from None

    def token(self, name):
        query = urllib.parse.urlencode({
            "service": self.service, "scope": f"repository:{name}:pull"})
        body, _ = self.get(self.auth + "?" + query, {"Accept": "application/json"}, auth=True)
        value = json.loads(body)
        token = value.get("token") or value.get("access_token")
        if (not isinstance(token, str) or not token or len(token) > 128 * 1024
                or any(ord(char) < 33 or ord(char) > 126 for char in token)):
            raise AuditError("invalid_bearer")
        return token

    def manifest(self, name, ref, token):
        return self.get(f"https://{self.host}/v2/{name}/manifests/{ref}", {
            "Accept": ACCEPT, "Authorization": "Bearer " + token})


def audit_one(row, output, source):
    client = Metadata(source)
    result = dict(row, source=source, observed_at_utc=now(), status="unknown")
    directory = output / "manifests" / row["instance_id"]
    try:
        token = client.token(row["image_name"])
        body, headers = client.manifest(row["image_name"], row["tag"], token)
        top = parse_manifest(body, headers)
        top_digest = "sha256:" + hashlib.sha256(body).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "top.json").write_bytes(body)
        write_once(directory / "top.headers.json", headers)
        if top["mediaType"] in INDEX_TYPES:
            descriptor = amd64_descriptor(top)
            body, headers = client.manifest(row["image_name"], descriptor["digest"], token)
            manifest = parse_manifest(body, headers, descriptor["digest"])
            if len(body) != descriptor["size"]:
                raise AuditError("selected_manifest_size_mismatch")
        else:
            manifest = top
        config, layers = image_descriptors(manifest)
        (directory / "selected.json").write_bytes(body)
        write_once(directory / "selected.headers.json", headers)
        result.update(status="manifest_verified", top_manifest_digest=top_digest,
                      manifest_digest="sha256:" + hashlib.sha256(body).hexdigest(),
                      config_digest=config["digest"], config=config, layers=layers,
                      manifest_file=f"manifests/{row['instance_id']}/selected.json",
                      platform_status="requires_config_check")
    except (AuditError, ValueError, KeyError, TypeError, OSError) as error:
        result["error"] = str(error) if isinstance(error, AuditError) else type(error).__name__
    result.update(response_body_bytes=client.bytes, requests=client.requests,
                  completed_at_utc=now())
    write_once(output / "items" / (row["instance_id"] + ".json"), result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=("official", "mirror"), default="official")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if not (0 <= args.shard_index < args.shard_count <= 16 and 1 <= args.workers <= 8):
        parser.error("invalid shard or worker count")
    all_rows, inventory_sha = load_inventory(args.inventory)
    rows = sorted(all_rows, key=lambda row: row["instance_id"])[
        args.shard_index::args.shard_count]
    args.output.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(
            lambda row: audit_one(row, args.output, args.source), rows))
    layers = {}
    for row in results:
        for layer in row.get("layers", []):
            prior = layers.setdefault(layer["digest"], layer["size"])
            if prior != layer["size"]:
                raise ValueError("same digest has different declared sizes")
    report = {
        "schema": "proworksim.verified-image-metadata.v054",
        "inventory_sha256": inventory_sha, "full_inventory_count": 500,
        "source": args.source, "shard_index": args.shard_index,
        "shard_count": args.shard_count, "image_count": len(rows),
        "verified_count": sum(row["status"] == "manifest_verified" for row in results),
        "response_body_bytes": sum(row["response_body_bytes"] for row in results),
        "unique_layer_count": len(layers), "unique_layer_compressed_bytes": sum(layers.values()),
        "proxy_used": False, "blob_requests": 0, "model_calls": 0,
        "wall_seconds": time.monotonic() - began, "images": results,
    }
    write_once(args.output / "summary.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "images"}))
    return 0 if report["verified_count"] == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
