import hashlib
import io
import json
import urllib.error

import pytest

from tools import verified_apiba_blob_v054 as apiba


def test_full_blob_identity_cache_and_refusal_to_restart_partial(tmp_path, monkeypatch):
    content = b"synthetic pinned blob" * 100
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    calls = []

    class Response(io.BytesIO):
        def __init__(self, body):
            super().__init__(body)
            self.headers = {"Content-Length": str(len(body))}

        def getcode(self):
            return 200

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("User-agent") == apiba.USER_AGENT
            assert request.get_header("Range") is None
            calls.append(request.full_url)
            return Response(json.dumps({"token": "synthetic-secret"}).encode()
                            if "/token?" in request.full_url else content)

    monkeypatch.setattr(apiba.asset, "direct_opener", Opener)
    output = tmp_path / "blob"
    assert apiba.download_blob("swebench/example", digest, output, expected_bytes=len(content))[
        "status"] == "download_complete"
    assert output.read_bytes() == content
    assert len(calls) == 2
    assert apiba.download_blob("swebench/example", digest, output, expected_bytes=len(content))[
        "status"] == "existing_verified"
    assert len(calls) == 2
    other = tmp_path / "other"
    other.with_name("other.part").write_bytes(content[:5])
    with pytest.raises(apiba.asset.DownloadPaused, match="Range unsupported"):
        apiba.download_blob("swebench/example", digest, other, expected_bytes=len(content))
    assert len(calls) == 2
    assert "synthetic-secret" not in output.with_name("blob.apiba.jsonl").read_text()


def test_redirect_is_refused_without_following(tmp_path, monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(
                request.full_url, 307, "redirect",
                {"Location": "https://unapproved.example/blob"}, None)

    monkeypatch.setattr(apiba.asset, "direct_opener", Opener)
    with pytest.raises(apiba.asset.DownloadPaused, match="no redirect"):
        apiba.download_blob("swebench/example", "sha256:" + "1" * 64,
                            tmp_path / "blob", expected_bytes=1)
    assert len(calls) == 1
