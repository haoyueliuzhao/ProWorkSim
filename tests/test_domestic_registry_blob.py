"""Registry authentication and resume controls with a real offline urllib chain."""
from email.message import Message
import hashlib
from http.client import responses
import io
import json
import urllib.response

import pytest

from tools import domestic_asset_download as asset
from tools import domestic_registry_blob as registry


IMAGE = "swebench/swesmith.x86_64.example_1776_repo.12345678"
CONTENT = b"abcdef"
DIGEST = "sha256:" + hashlib.sha256(CONTENT).hexdigest()
SOURCE = f"https://docker.1ms.run/v2/{IMAGE}/blobs/{DIGEST}"
CDN = "https://cloudfront-docker-cf.mrs.1ms.run/blob"


def offline_transport(monkeypatch, replies):
    calls = []
    original = asset.urllib.request.HTTPSHandler

    class OfflineHTTPS(original):
        def https_open(self, request):
            calls.append({
                "url": request.full_url, "proxy": request.has_proxy(),
                "authorization": request.get_header("Authorization"),
                "range": request.get_header("Range"),
                "user_agent": request.get_header("User-agent"),
                "accept": request.get_header("Accept"),
            })
            assert replies, "Unexpected request"
            code, values, content = replies.pop(0)
            headers = Message()
            for key, value in values.items():
                headers[key] = value
            response = urllib.response.addinfourl(
                io.BytesIO(content), headers, request.full_url, code)
            response.msg = responses[code]
            return response

    monkeypatch.setattr(asset.urllib.request, "HTTPSHandler", OfflineHTTPS)
    return calls


def auth_reply(token):
    body = json.dumps({"token": token}).encode()
    return 200, {"Content-Length": str(len(body))}, body


def test_auth_and_cross_origin_redirect_keep_bearer_private_and_cache_offline(tmp_path, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://must-not-be-used.invalid:9999")

    def forbidden(*args):
        pytest.fail("Complete cache must not hash, authenticate or open a connection")

    monkeypatch.setattr(asset.urllib.request, "getproxies", forbidden)
    calls = offline_transport(monkeypatch, [
        auth_reply("memory-secret-one"),
        (307, {"Location": CDN + "?signature=temporary-secret-one"}, b""),
        (200, {"Content-Length": "6"}, CONTENT),
    ])
    output = tmp_path / "blob"
    result = registry.download_blob(IMAGE, DIGEST, output, expected_bytes=6)
    assert result["status"] == "download_complete" and output.read_bytes() == CONTENT
    assert len(calls) == 3 and all(not call["proxy"] for call in calls)
    assert calls[0]["url"].startswith("https://docker.1ms.run/openapi/v1/auth/token?")
    assert calls[0]["authorization"] is None and calls[0]["accept"] == "application/json"
    assert calls[1]["url"] == SOURCE and calls[1]["authorization"] == "Bearer memory-secret-one"
    assert calls[2]["authorization"] is None and calls[2]["url"].startswith(CDN)
    assert all(call["user_agent"] == "ProWorkSim-domestic-asset/1" for call in calls)
    assert calls[2]["accept"] == "application/octet-stream"
    saved = "\n".join(path.read_text() for path in tmp_path.glob("*.json*"))
    assert "memory-secret-one" not in saved and "temporary-secret-one" not in saved
    assert "?<redacted>" in saved

    monkeypatch.setattr(asset, "direct_opener", forbidden)
    monkeypatch.setattr(asset, "file_hasher", forbidden)
    result = registry.download_blob(IMAGE, DIGEST, output, expected_bytes=6)
    assert result["status"] == "existing_verified" and result["payload_bytes_received"] == 0
    assert len(calls) == 3


def test_resume_refreshes_token_and_signed_url_but_keeps_fixed_blob_identity(tmp_path, monkeypatch):
    output = tmp_path / "blob"
    calls = offline_transport(monkeypatch, [
        auth_reply("old-memory-secret"),
        (307, {"Location": CDN + "?signature=old-signed-secret"}, b""),
        (200, {"Content-Length": "6"}, CONTENT[:3]),
        auth_reply("new-memory-secret"),
        (307, {"Location": CDN + "?signature=new-signed-secret"}, b""),
        (206, {"Content-Length": "3", "Content-Range": "bytes 3-5/6"}, CONTENT[3:]),
    ])
    with pytest.raises(asset.DownloadPaused, match="ended early"):
        registry.download_blob(IMAGE, DIGEST, output, expected_bytes=6)
    saved = json.loads((tmp_path / "blob.part.json").read_text())
    assert saved["source_url"] == SOURCE and saved["partial_bytes"] == 3
    assert (tmp_path / "blob.part").read_bytes() == b"abc"
    result = registry.download_blob(IMAGE, DIGEST, output, expected_bytes=6)
    assert result["payload_bytes_received"] == 3 and output.read_bytes() == CONTENT
    assert len(calls) == 6
    assert calls[1]["url"] == calls[4]["url"] == SOURCE
    assert calls[1]["authorization"] == "Bearer old-memory-secret"
    assert calls[4]["authorization"] == "Bearer new-memory-secret"
    assert calls[4]["range"] == calls[5]["range"] == "bytes=3-"
    assert calls[2]["authorization"] is calls[5]["authorization"] is None
    saved_text = "\n".join(path.read_text() for path in tmp_path.glob("*.json*"))
    assert all(secret not in saved_text for secret in (
        "old-memory-secret", "new-memory-secret", "old-signed-secret", "new-signed-secret"))


def test_invalid_pins_precede_auth_and_auth_redirect_never_follows(tmp_path, monkeypatch):
    calls = offline_transport(monkeypatch, [
        (307, {"Location": "https://unapproved.invalid/token"}, b""),
    ])
    with pytest.raises(asset.DownloadPaused, match="fixed swebench"):
        registry.download_blob("swebench/../elsewhere", DIGEST, tmp_path / "bad1", expected_bytes=6)
    with pytest.raises(asset.DownloadPaused, match="sha256"):
        registry.download_blob(IMAGE, "latest", tmp_path / "bad2", expected_bytes=6)
    with pytest.raises(asset.DownloadPaused, match="positive expected"):
        registry.download_blob(IMAGE, DIGEST, tmp_path / "bad3", expected_bytes=0)
    assert calls == []
    with pytest.raises(asset.DownloadPaused, match="authentication HTTP 307"):
        registry.download_blob(IMAGE, DIGEST, tmp_path / "blob", expected_bytes=6)
    assert len(calls) == 1 and calls[0]["authorization"] is None
    assert not (tmp_path / "blob.part").exists()
