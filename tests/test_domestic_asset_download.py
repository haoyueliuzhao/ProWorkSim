"""Offline transport controls only; no endpoint, model or daemon is contacted."""
from email.message import Message
import hashlib
from http.client import responses
import io
import json
import urllib.response

import pytest

from tools import domestic_asset_download as download


URL = "https://modelscope.cn/models/example/resolve/fixed/file.bin"
CONTENT = b"abcdef"
SHA = hashlib.sha256(CONTENT).hexdigest()


def offline_https(monkeypatch, replies):
    calls, streams = [], []
    original = download.urllib.request.HTTPSHandler

    class Body(io.BytesIO):
        reads = 0

        def read(self, size=-1):
            self.reads += 1
            return super().read(size)

    class OfflineHTTPS(original):
        def https_open(self, request):
            calls.append({
                "url": request.full_url, "host": request.host,
                "proxy": request.has_proxy(), "range": request.get_header("Range"),
            })
            if not replies:
                pytest.fail("Unexpected additional network request")
            code, values, content = replies.pop(0)
            headers = Message()
            for key, value in values.items():
                headers[key] = value
            body = Body(content)
            streams.append(body)
            response = urllib.response.addinfourl(body, headers, request.full_url, code)
            response.msg = responses[code]
            return response

    monkeypatch.setattr(download.urllib.request, "HTTPSHandler", OfflineHTTPS)
    return calls, streams


def test_proxy_environment_is_ignored_and_verified_existing_file_uses_no_network(tmp_path, monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, "http://must-not-be-contacted.invalid:9999")

    def forbidden_environment_lookup():
        pytest.fail("Proxy environment must never be consulted")

    monkeypatch.setattr(download.urllib.request, "getproxies", forbidden_environment_lookup)
    calls, _ = offline_https(monkeypatch, [(200, {"Content-Length": "6"}, CONTENT)])
    output = tmp_path / "asset"
    result = download.download(URL, output, expected_sha256=SHA, expected_bytes=6)
    assert result["status"] == "download_complete" and output.read_bytes() == CONTENT
    assert calls == [{"url": URL, "host": "modelscope.cn", "proxy": False, "range": None}]
    result = download.download(URL, output, expected_sha256=SHA, expected_bytes=6)
    assert result["status"] == "existing_verified" and result["payload_bytes_received"] == 0
    assert result["verification"] == "cached_file_identity"
    assert len(calls) == 1
    events = [json.loads(line) for line in (tmp_path / "asset.download.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "existing_verified" and events[-1]["sha256"] == SHA
    assert all(event["environment_proxy_used"] is False for event in events)
    # An existing file without a completion receipt is hashed exactly once.
    existing = tmp_path / "preexisting"
    existing.write_bytes(CONTENT)
    original_hasher, hash_calls = download.file_hasher, []

    def counted_hasher(path, chunk_bytes):
        hash_calls.append(path)
        return original_hasher(path, chunk_bytes)

    monkeypatch.setattr(download, "file_hasher", counted_hasher)
    result = download.download(URL, existing, expected_sha256=SHA, expected_bytes=6)
    assert result["verification"] == "necessary_local_sha256" and len(hash_calls) == 1

    def forbidden_rehash(*args):
        pytest.fail("An unchanged verified complete file must not be hashed again")

    monkeypatch.setattr(download, "file_hasher", forbidden_rehash)
    mirror_url = "https://hf-mirror.com/example/resolve/fixed/file.bin"
    result = download.download(mirror_url, existing, expected_sha256=SHA, expected_bytes=6)
    assert result["verification"] == "cached_file_identity" and len(calls) == 1
    # Even equal bytes in a replacement inode require a fresh local verification.
    replacement = tmp_path / "replacement"
    replacement.write_bytes(CONTENT)
    replacement.replace(existing)
    monkeypatch.setattr(download, "file_hasher", counted_hasher)
    result = download.download(mirror_url, existing, expected_sha256=SHA, expected_bytes=6)
    assert result["verification"] == "necessary_local_sha256" and len(hash_calls) == 2
    assert len(calls) == 1


@pytest.mark.parametrize("target", ["https://huggingface.co/origin/file", "http://modelscope.cn/file"])
def test_unapproved_redirect_is_refused_before_a_second_request(tmp_path, monkeypatch, target):
    calls, streams = offline_https(monkeypatch, [(302, {"Location": target}, b"not an asset")])
    with pytest.raises(download.DownloadPaused, match="HTTPS candidate-host"):
        download.download(URL, tmp_path / "asset", expected_sha256=SHA, expected_bytes=6)
    assert len(calls) == 1 and calls[0]["url"] == URL
    assert streams[0].reads == 0
    assert not (tmp_path / "asset").exists() and not (tmp_path / "asset.part").exists()


@pytest.mark.parametrize("response", [
    (200, {"Content-Length": "6"}, CONTENT),
    (206, {"Content-Length": "4", "Content-Range": "bytes 2-5/6"}, b"cdef"),
])
def test_bad_resume_never_appends_or_restarts_and_valid_resume_uses_only_remaining_bytes(tmp_path, monkeypatch, response):
    output, partial = tmp_path / "asset", tmp_path / "asset.part"
    checkpoint = tmp_path / "asset.part.json"
    partial.write_bytes(CONTENT[:3])
    download.atomic_json(checkpoint, {
        "version": download.VERSION, "source_url": URL, "expected_sha256": SHA, "expected_bytes": 6,
        "partial_bytes": 3, "partial_sha256": hashlib.sha256(CONTENT[:3]).hexdigest(), "status": "partial",
    })
    before = checkpoint.read_bytes()
    calls, streams = offline_https(monkeypatch, [
        response, (206, {"Content-Length": "3", "Content-Range": "bytes 3-5/6"}, b"def"),
    ])
    with pytest.raises(download.DownloadPaused, match="resume|Resume"):
        download.download(URL, output, expected_sha256=SHA, expected_bytes=6)
    assert partial.read_bytes() == b"abc" and checkpoint.read_bytes() == before
    assert not output.exists() and len(calls) == 1 and streams[0].reads == 0
    assert calls[0]["range"] == "bytes=3-"
    # A new explicit invocation may resume; the failed invocation did not retry.
    result = download.download(URL, output, expected_sha256=SHA, expected_bytes=6)
    assert result["payload_bytes_received"] == 3 and result["sha256"] == SHA
    assert output.read_bytes() == CONTENT and not partial.exists()
    assert len(calls) == 2 and calls[1]["range"] == "bytes=3-"
