import hashlib
import io
import json
import re
import urllib.error

import pytest

from tools import verified_registry_ranges_v054 as ranges


def test_explicit_lease_refresh_preserves_ranges_and_rate_limit_boundaries(tmp_path, monkeypatch):
    body = bytes(range(256)) * (12 * 1024)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    source = f"https://docker.1ms.run/v2/swebench/example/blobs/{digest}"
    for mode in ("expired", "unknown_403", "refresh_429"):
        clock, auth, permits, received, failed = [10000], [0], [0], [0], [False]
        registry_ranges = []

        class Auth:
            def __init__(self, source):
                assert source == "mirror"

            def token(self, image):
                auth[0] += 1
                if mode == "refresh_429" and auth[0] == 2:
                    try:
                        raise urllib.error.HTTPError(
                            "https://docker.1ms.run/openapi/v1/auth/token", 429, "limited",
                            {"Retry-After": "3600"}, None)
                    except urllib.error.HTTPError:
                        raise ValueError("suppressed auth HTTP context") from None
                return "lease-secret"

        def open_response(opener, url, headers, policy, emit):
            start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"]).groups())
            is_registry = url == source
            if is_registry:
                registry_ranges.append((start, end))
                assert headers["Authorization"] == "Bearer lease-secret"
            else:
                assert "Authorization" not in headers
                if not failed[0]:
                    failed[0] = True
                    if mode != "unknown_403":
                        clock[0] = 14000
                    error = urllib.error.HTTPError(url, 403, "forbidden", {}, None)
                    raise ranges.asset.DownloadPaused("HTTP 403") from error
            received[0] += end - start + 1
            response = io.BytesIO(body[start:end + 1])
            response.getcode = lambda: 206
            response.headers = {"Content-Range": f"bytes {start}-{end}/{len(body)}",
                                "Content-Length": str(end - start + 1)}
            lease = ("https://cloudfront-docker-cf.mrs.1ms.run/blob?"
                     f"Expires={clock[0] + 3000}&Key-Pair-Id=key&Signature=hidden-signature")
            return response, lease

        monkeypatch.setattr(ranges, "Metadata", Auth)
        monkeypatch.setattr(ranges.asset, "open_response", open_response)
        pool = ranges.RangePool(workers=1, chunk_bytes=1024 * 1024)
        pool.now_epoch = lambda: clock[0]
        pool.registry_turn = lambda: permits.__setitem__(0, permits[0] + 1)
        output = tmp_path / mode / "blob"
        if mode == "expired":
            pool.download("swebench/example", digest, output, expected_bytes=len(body))
            assert output.read_bytes() == body
            assert received[0] == len(body)
            assert registry_ranges == [(0, 1048575), (1048576, 2097151)]
            assert auth[0] == permits[0] == 2
        else:
            with pytest.raises(ranges.asset.DownloadPaused) as caught:
                pool.download("swebench/example", digest, output, expected_bytes=len(body))
            assert received[0] == 1048576
            assert auth[0] == permits[0] == (1 if mode == "unknown_403" else 2)
            assert pool.stop.is_set()
            if mode == "refresh_429":
                assert caught.value.__cause__.headers["Retry-After"] == "3600"
                assert pool.first_failure["http_status"] == 429
                assert pool.first_failure["retry_after"] == "3600"
        pool.close()
        ledger_text = output.with_name("blob.ranges").joinpath("ledger.json").read_text()
        assert "hidden-signature" not in ledger_text
        assert "lease-secret" not in ledger_text


def test_range_requires_exact_206_bounds():
    response = io.BytesIO(b"ignored")
    response.getcode = lambda: 200
    response.headers = {}
    with pytest.raises(ranges.asset.DownloadPaused, match="206"):
        ranges.checked_range(response, 0, 7, 8)
    response.getcode = lambda: 206
    response.headers = {"Content-Range": "bytes 0-7/9"}
    with pytest.raises(ranges.asset.DownloadPaused, match="Content-Range"):
        ranges.checked_range(response, 0, 7, 8)


def test_apiba_partial_handoff_downloads_only_missing_bytes(tmp_path, monkeypatch):
    body = bytes(range(256)) * 8192
    prefix = body[:512 * 1024]
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    output = tmp_path / "blob"
    output.with_name("blob.part").write_bytes(prefix)
    output.with_name("blob.part.json").write_text(json.dumps({
        "version": "domestic-asset-download-v1",
        "source_url": f"https://docker.apiba.cn/v2/swebench/example/blobs/{digest}",
        "expected_sha256": digest.split(":")[1], "expected_bytes": len(body),
        "partial_bytes": len(prefix), "partial_sha256": hashlib.sha256(prefix).hexdigest(),
    }))
    transferred, starts = [0], []

    class Auth:
        def __init__(self, source):
            assert source == "mirror"

        def token(self, image):
            return "synthetic"

    def open_response(opener, url, headers, policy, emit):
        start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"]).groups())
        starts.append(start)
        transferred[0] += end - start + 1
        response = io.BytesIO(body[start:end + 1])
        response.getcode = lambda: 206
        response.headers = {"Content-Range": f"bytes {start}-{end}/{len(body)}",
                            "Content-Length": str(end - start + 1)}
        return response, "https://cloudfront-docker-cf.mrs.1ms.run/blob?sig=private"

    monkeypatch.setattr(ranges, "Metadata", Auth)
    monkeypatch.setattr(ranges.asset, "open_response", open_response)
    pool = ranges.RangePool(workers=2, chunk_bytes=1024 * 1024)
    pool.download("swebench/example", digest, output, expected_bytes=len(body))
    pool.close()
    assert min(starts) == len(prefix)
    assert transferred[0] == len(body) - len(prefix)
    assert output.read_bytes() == body
    ledger = json.loads((tmp_path / "blob.ranges/ledger.json").read_bytes())
    reused = next(row for row in ledger["events"] if row["event"] == "reuse_sequential_prefix")
    assert reused["original_source_url"].startswith("https://docker.apiba.cn/")


@pytest.mark.parametrize("interrupt", [False, True])
def test_shared_ranges_resume_and_keep_credentials_off_cdn(tmp_path, monkeypatch, interrupt):
    body = bytes(range(256)) * (12 * 1024 + 7)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    calls, delivered, auth = [], [0], [0]
    pending_failure = [interrupt]

    class Auth:
        def __init__(self, source):
            assert source == "mirror"

        def token(self, image):
            auth[0] += 1
            return "secret-bearer"

    class Response(io.BytesIO):
        def __init__(self, start, end, fail):
            super().__init__(body[start:end + 1])
            self.headers = {"Content-Range": f"bytes {start}-{end}/{len(body)}",
                            "Content-Length": str(end - start + 1)}
            self.fail = fail
            self.reads = 0

        def getcode(self):
            return 206

        def read(self, size=-1):
            if self.fail and self.reads == 1:
                raise OSError("synthetic transport stop")
            if self.fail and self.reads == 0:
                size = min(size, 512 * 1024)
            value = super().read(size)
            self.reads += 1
            delivered[0] += len(value)
            return value

    def open_response(opener, url, headers, policy, emit):
        start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"]).groups())
        calls.append((url, start, end, dict(headers)))
        if "cloudfront-" in url:
            assert "Authorization" not in headers
        else:
            assert headers["Authorization"] == "Bearer secret-bearer"
        final = "https://cloudfront-docker-cf.mrs.1ms.run/blob?sig=secret-signature"
        emit("request", url=url)
        fail = pending_failure[0]
        pending_failure[0] = False
        return Response(start, end, fail), final

    monkeypatch.setattr(ranges, "Metadata", Auth)
    monkeypatch.setattr(ranges.asset, "open_response", open_response)
    output = tmp_path / "content.blob"
    if interrupt:
        pool = ranges.RangePool(workers=3, chunk_bytes=1024 * 1024)
        with pytest.raises(OSError, match="synthetic"):
            pool.download("swebench/example", digest, output, expected_bytes=len(body))
        pool.close()
    pool = ranges.RangePool(workers=3, chunk_bytes=1024 * 1024)
    result = pool.download("swebench/example", digest, output, expected_bytes=len(body))
    pool.close()
    assert result["status"] == "download_complete"
    assert output.read_bytes() == body
    assert delivered[0] == len(body)
    if interrupt:
        assert calls[1][1] == 512 * 1024
    ledger = output.with_name(output.name + ".ranges") / "ledger.json"
    assert "secret-" not in ledger.read_text()
    assert json.loads(output.with_name(output.name + ".verified.json").read_text())[
        "expected_sha256"] == digest.split(":")[1]
    pool = ranges.RangePool(workers=1, chunk_bytes=1024 * 1024)
    before = auth[0]
    assert pool.download("swebench/example", digest, output, expected_bytes=len(body))[
        "status"] == "existing_verified"
    pool.close()
    assert auth[0] == before
