#!/usr/bin/env python3
"""Audit fixed SWE-smith image tags using official metadata only.

No image/config/layer blobs are fetched. Anonymous pull tokens stay in memory.
The offline option verifies cached manifests without claiming a current remote
check. This utility does not update deployment or experiment identities.
"""
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

AUTH = "https://auth.docker.io/token"
REGISTRY = "https://registry-1.docker.io"
IMAGE_PATTERN = re.compile(r"swebench/swesmith\.x86_64\.[a-z0-9][a-z0-9_.-]*")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_TYPES = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}
INDEX_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}
ACCEPT = ", ".join(sorted(IMAGE_TYPES | INDEX_TYPES))
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_TOKEN_BYTES = 64 * 1024
REQUEST_TIMEOUT_SECONDS = 20
TOTAL_TIMEOUT_SECONDS = 420
WORKERS = 4


class AuditError(Exception):
    """A fixed, non-sensitive error code safe to put in an audit report."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def valid_digest(value: object) -> str:
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        raise AuditError("invalid_sha256_descriptor")
    return value


def bounded_local_read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise AuditError("local_metadata_exceeds_limit")
    return content


def load_inventory(path: Path) -> tuple[bytes, list[dict]]:
    content = bounded_local_read(path, 128 * 1024)
    value = json.loads(content)
    rows = value["images"]
    if value["platform"] != {"os": "linux", "architecture": "amd64"}:
        raise AuditError("inventory_platform_must_be_linux_amd64")
    if not isinstance(rows, list) or len(rows) != 32:
        raise AuditError("inventory_requires_exactly_32_images")
    names = set()
    for row in rows:
        name = row["image_name"]
        if not isinstance(name, str) or not IMAGE_PATTERN.fullmatch(name):
            raise AuditError("unexpected_image_name")
        if name in names or row["tag"] != "latest":
            raise AuditError("duplicate_image_or_unexpected_tag")
        names.add(name)
        for key in ("cached_top_manifest_digest", "cached_manifest_digest", "cached_config_digest"):
            valid_digest(row[key])
    return content, rows


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuditError("metadata_redirect_not_allowed")


class OfficialMetadata:
    """Only official anonymous auth and manifest endpoints; never blob URLs."""

    def __init__(self, deadline: float):
        self.deadline = deadline
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), RejectRedirects())

    def request(self, url: str, limit: int, headers: dict) -> tuple[bytes, dict]:
        parsed = urllib.parse.urlsplit(url)
        auth_request = parsed.hostname == "auth.docker.io" and parsed.path == "/token"
        manifest_request = (
            parsed.hostname == "registry-1.docker.io"
            and re.fullmatch(
                r"/v2/swebench/swesmith\.x86_64\.[a-z0-9_.-]+/manifests/"
                r"(latest|sha256:[0-9a-f]{64})", parsed.path) is not None
            and not parsed.query)
        if (parsed.scheme != "https" or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.fragment
                or not (auth_request or manifest_request)):
            raise AuditError("request_endpoint_not_allowed")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AuditError("overall_metadata_deadline")
        request = urllib.request.Request(
            url, headers={"Accept-Encoding": "identity",
                          "User-Agent": "ProWorkSim-v053-metadata-audit/1", **headers},
            method="GET")
        try:
            with self.opener.open(
                    request, timeout=min(REQUEST_TIMEOUT_SECONDS, remaining)) as response:
                if response.status != 200:
                    raise AuditError(f"http_status_{response.status}")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > limit):
                    raise AuditError("metadata_content_length_exceeds_limit")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise AuditError("unexpected_metadata_content_encoding")
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= self.deadline:
                        raise AuditError("overall_metadata_deadline")
                    block = response.read1(min(64 * 1024, limit + 1 - size))
                    if not block:
                        break
                    chunks.append(block)
                    size += len(block)
                    if size > limit:
                        raise AuditError("metadata_body_exceeds_limit")
                digests = response.headers.get_all("Docker-Content-Digest", [])
                if not auth_request and len(digests) != 1:
                    raise AuditError("require_one_docker_content_digest_header")
                return b"".join(chunks), {
                    "docker_content_digest": digests[0] if digests else None,
                    "date": response.headers.get("Date"),
                    "content_type": response.headers.get("Content-Type"),
                    "content_length": length,
                }
        except urllib.error.HTTPError as error:
            raise AuditError(f"http_status_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AuditError("metadata_transport_error") from None

    def token(self, image_name: str) -> str:
        query = urllib.parse.urlencode({
            "service": "registry.docker.io", "scope": f"repository:{image_name}:pull"})
        body, _ = self.request(AUTH + "?" + query, MAX_TOKEN_BYTES, {"Accept": "application/json"})
        try:
            value = json.loads(body)
            token = value.get("token") or value.get("access_token")
        except (ValueError, TypeError, AttributeError):
            raise AuditError("invalid_anonymous_token_response") from None
        if (not isinstance(token, str) or not 1 <= len(token) <= MAX_TOKEN_BYTES
                or "\r" in token or "\n" in token):
            raise AuditError("invalid_anonymous_pull_token")
        return token

    def manifest(self, name: str, reference: str, token: str) -> tuple[bytes, dict]:
        body, headers = self.request(
            f"{REGISTRY}/v2/{name}/manifests/{reference}", MAX_MANIFEST_BYTES,
            {"Accept": ACCEPT, "Authorization": "Bearer " + token})
        if token.encode() in body:
            raise AuditError("sensitive_token_reflected_in_response")
        return body, headers


def parse_manifest(body: bytes, headers: dict, expected_digest: str | None = None) -> dict:
    if len(body) > MAX_MANIFEST_BYTES:
        raise AuditError("manifest_exceeds_limit")
    actual = digest_bytes(body)
    if actual != valid_digest(headers["docker_content_digest"]):
        raise AuditError("manifest_header_digest_mismatch")
    if expected_digest is not None and actual != expected_digest:
        raise AuditError("selected_manifest_digest_mismatch")
    try:
        value = json.loads(body)
    except ValueError:
        raise AuditError("invalid_manifest_json") from None
    if not isinstance(value, dict) or value.get("schemaVersion") != 2:
        raise AuditError("unsupported_manifest_schema")
    if value.get("mediaType") not in IMAGE_TYPES | INDEX_TYPES:
        raise AuditError("unsupported_manifest_media_type")
    return value


def amd64_descriptor(index: dict) -> dict:
    choices = [row for row in index.get("manifests", [])
               if isinstance(row, dict)
               and row.get("platform", {}).get("os") == "linux"
               and row.get("platform", {}).get("architecture") == "amd64"
               and row.get("platform", {}).get("variant") in (None, "")]
    if len(choices) != 1:
        raise AuditError("linux_amd64_manifest_missing_or_ambiguous")
    descriptor = choices[0]
    valid_digest(descriptor.get("digest"))
    if (type(descriptor.get("size")) is not int
            or not 0 < descriptor["size"] <= MAX_MANIFEST_BYTES
            or descriptor.get("mediaType") not in IMAGE_TYPES):
        raise AuditError("invalid_linux_amd64_manifest_descriptor")
    return descriptor


def image_descriptors(manifest: dict) -> tuple[dict, list[dict]]:
    if manifest.get("mediaType") not in IMAGE_TYPES:
        raise AuditError("selected_result_is_not_image_manifest")
    config, layers = manifest.get("config"), manifest.get("layers")
    if not isinstance(config, dict) or not isinstance(layers, list) or len(layers) > 4096:
        raise AuditError("invalid_image_descriptor_structure")
    for descriptor in [config, *layers]:
        if not isinstance(descriptor, dict):
            raise AuditError("invalid_image_descriptor")
        valid_digest(descriptor.get("digest"))
        if type(descriptor.get("size")) is not int or descriptor["size"] < 0:
            raise AuditError("invalid_image_descriptor_size")
    return config, layers


def cached_manifests(index_path: Path) -> dict:
    """The offline index maps names to body/header paths; it is never used online."""
    value = json.loads(bounded_local_read(index_path, 128 * 1024))
    return value["images"]


def offline_response(reference: dict) -> tuple[bytes, dict]:
    return (
        bounded_local_read(Path(reference["body_path"]), MAX_MANIFEST_BYTES),
        {"docker_content_digest": reference["docker_content_digest"],
         "date": reference.get("date"), "content_type": reference.get("content_type")},
    )


def audit_one(row: dict, output: Path, deadline: float, offline: dict | None) -> dict:
    name, observed_at = row["image_name"], utc_now()
    result = {"image_name": name, "tag": row["tag"], "observed_at_utc": observed_at,
              "cached_top_manifest_digest": row["cached_top_manifest_digest"],
              "cached_manifest_digest": row["cached_manifest_digest"],
              "cached_config_digest": row["cached_config_digest"]}
    try:
        client = OfficialMetadata(deadline) if offline is None else None
        token = client.token(name) if client is not None else None
        top_body, top_headers = (
            client.manifest(name, "latest", token) if client is not None
            else offline_response(offline[name]["top"]))
        top = parse_manifest(top_body, top_headers)
        selected_body, selected_headers, selected = top_body, top_headers, top
        platform_evidence = "single_manifest_platform_not_independently_read"
        if top["mediaType"] in INDEX_TYPES:
            descriptor = amd64_descriptor(top)
            selected_body, selected_headers = (
                client.manifest(name, descriptor["digest"], token) if client is not None
                else offline_response(offline[name]["platform"]))
            if len(selected_body) != descriptor["size"]:
                raise AuditError("selected_manifest_size_mismatch")
            selected = parse_manifest(selected_body, selected_headers, descriptor["digest"])
            platform_evidence = "unique_linux_amd64_index_descriptor"
        config, layers = image_descriptors(selected)
        stem = name.replace("/", "__")
        top_path, selected_path = f"manifests/{stem}.top.json", f"manifests/{stem}.image.json"
        (output / top_path).write_bytes(top_body)
        (output / selected_path).write_bytes(selected_body)
        top_digest, selected_digest = digest_bytes(top_body), digest_bytes(selected_body)
        matches = {
            "top_manifest": top_digest == row["cached_top_manifest_digest"],
            "image_manifest": selected_digest == row["cached_manifest_digest"],
            "config": config["digest"] == row["cached_config_digest"],
        }
        result.update(
            status=("cache_verified_offline" if offline is not None else
                    "unchanged" if all(matches.values()) else "changed"),
            current_official_head_checked=offline is None,
            top_manifest_digest=top_digest, manifest_digest=selected_digest,
            config_digest=config["digest"], config_descriptor=config, layers=layers,
            requested_platform={"os": "linux", "architecture": "amd64"},
            platform_evidence=platform_evidence, config_body_fetched=False,
            matches_cached=matches,
            top_manifest_response=top_headers, image_manifest_response=selected_headers,
            raw_top_manifest=top_path, raw_image_manifest=selected_path,
        )
    except AuditError as error:
        result.update(status="unknown", current_official_head_checked=False, error_code=str(error))
    except Exception as error:
        # Do not print server payloads, token values, URLs from exceptions, or tracebacks.
        result.update(status="unknown", current_official_head_checked=False,
                      error_code="metadata_processing_error", error_type=type(error).__name__)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("config/v053-docker-image-inventory.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--offline-cache-index", type=Path,
                        help="Verify cached small manifests only; never checks the current registry.")
    args = parser.parse_args()
    inventory_content, rows = load_inventory(args.inventory)
    offline = cached_manifests(args.offline_cache_index) if args.offline_cache_index else None
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "manifests").mkdir()
    started, deadline = utc_now(), time.monotonic() + TOTAL_TIMEOUT_SECONDS
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda row: audit_one(row, args.output_dir, deadline, offline), rows))
    report = {
        "version": "official-docker-manifest-audit-v1", "started_at_utc": started,
        "finished_at_utc": utc_now(), "mode": "offline_cache_validation" if offline is not None else "official_registry",
        "inventory_sha256": hashlib.sha256(inventory_content).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "image_count": len(results), "workers": WORKERS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "overall_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
        "max_manifest_response_bytes": MAX_MANIFEST_BYTES,
        "proxy_enabled": False, "redirects_allowed": False, "layer_or_config_blobs_fetched": 0,
        "model_calls": 0, "gpu_operations": 0, "deployment_modified": False,
        "unknown_count": sum(row["status"] == "unknown" for row in results),
        "changed_count": sum(row["status"] == "changed" for row in results),
        "results": results,
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    compact_keys = (
        "image_name", "status", "top_manifest_digest", "manifest_digest",
        "config_digest", "matches_cached", "error_code",
    )
    compact = {
        key: report[key] for key in (
            "version", "started_at_utc", "finished_at_utc", "mode",
            "inventory_sha256", "unknown_count", "changed_count")
    }
    compact["results"] = [{key: row[key] for key in compact_keys if key in row} for row in results]
    encoded = json.dumps(compact, separators=(",", ":"))
    (args.output_dir / "compact-results.json").write_text(encoded + "\n")
    print("OFFICIAL_DOCKER_MANIFEST_AUDIT=" + encoded, flush=True)
    return 2 if report["unknown_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
