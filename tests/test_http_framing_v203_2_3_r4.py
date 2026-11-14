"""Framing controls over observed bytes only; no sockets, API, Docker or test score."""
import pytest

from proworksim.software_benchmark_http_framing_v203_2_3_r4 import HTTPKeepaliveTracker

GET = b"GET / HTTP/1.1\r\nHost: example.test\r\n\r\n"
HEAD = b"HEAD / HTTP/1.1\r\nHost: example.test\r\n\r\n"
EMPTY = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"


def exchange(response, request=GET, *, port=80):
    tracker = HTTPKeepaliveTracker(port=port)
    tracker.feed_client(request)
    tracker.feed_server(response)
    return tracker


@pytest.mark.parametrize("response,req,body_bytes,framing", [
    (b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\ntest", GET, 4, "content-length"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc", GET, 3, "content-length"),
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n", GET, 3, "chunked"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: 999\r\n\r\n", HEAD, 0, "content-length"),
    (b"HTTP/1.1 204 No Content\r\n\r\n", GET, 0, "content-length"),
    (b"HTTP/1.1 304 Not Modified\r\nContent-Length: 123\r\n\r\n", GET, 0, "content-length"),
])
def test_complete_strict_boundaries(response, req, body_bytes, framing):
    proof = exchange(response, req).proof()
    assert proof["eligible"] and proof["complete_framing"]
    assert proof["requests_completed"] == proof["responses_completed"] == 1
    assert proof["pending_responses"] == 0
    assert proof["frames"][0]["response"]["body_bytes"] == body_bytes
    assert proof["frames"][0]["response"]["kind"] == framing
    assert proof["frames"][0]["response"]["complete"]
    assert proof["relay_empty_forwarding_queues_still_required"]
    assert not proof["application_or_test_success_inferred"]


@pytest.mark.parametrize("response", [
    b"HTTP/1.1 200 OK\r\nContent-Length:",
    b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nabc",
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\nabc",
    b"HTTP/1.1 200 OK\r\nContent-Length: 2, 3\r\n\r\nabc",
    b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\nabc",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabcX\n0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\ng\r\nabc\r\n0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nContent-Length: 0\r\n\r\n",
    b"HTTP/1.1 100 Continue\r\n\r\n",
    EMPTY + b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
])
def test_partial_conflicting_or_unpaired_response_never_qualifies(response):
    assert not exchange(response).proof()["eligible"]


def test_trailers_and_bytewise_fragmentation_preserve_completion_boundary():
    tracker = HTTPKeepaliveTracker()
    for byte in GET:
        tracker.feed_client(bytes([byte]))
    raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\nX-Checksum: ok\r\n\r\n"
    for byte in raw[:-1]:
        tracker.feed_server(bytes([byte]))
    assert not tracker.proof()["eligible"]  # Trailer terminating CRLF incomplete.
    tracker.feed_server(raw[-1:])
    proof = tracker.proof()
    assert proof["eligible"]
    assert proof["frames"][0]["response"]["trailers"] == ["x-checksum"]
    assert proof["bytes_from_client"] == len(GET) and proof["bytes_from_server"] == len(raw)


def test_head_cannot_swallow_unexpected_payload():
    assert not exchange(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nxx", HEAD).proof()["eligible"]


def test_100_continue_then_request_body_and_final_response():
    tracker = HTTPKeepaliveTracker()
    tracker.feed_client(b"POST / HTTP/1.1\r\nHost: example.test\r\nContent-Length: 3\r\nExpect: 100-continue\r\n\r\n")
    tracker.feed_server(b"HTTP/1.1 100 Continue\r\n\r\n")
    assert not tracker.proof()["eligible"]
    tracker.feed_client(b"abc")
    tracker.feed_server(b"HTTP/1.1 103 Early Hints\r\nLink: </example>\r\n\r\n" + EMPTY)
    proof = tracker.proof()
    assert proof["eligible"]
    assert proof["frames"][0]["informational_statuses"] == [100, 103]
    assert proof["frames"][0]["request"]["body_bytes"] == 3
    assert proof["responses_started"] == 1


def test_partial_request_body_is_pending_even_after_final_response():
    tracker = exchange(EMPTY, b"POST / HTTP/1.1\r\nHost: example.test\r\nContent-Length: 3\r\n\r\nab")
    assert not tracker.proof()["eligible"]
    assert tracker.proof()["requests_completed"] == 0


def test_chunked_request_body_uses_h11_end_of_message():
    request = b"POST / HTTP/1.1\r\nHost: example.test\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\nX-Trace: yes\r\n\r\n"
    proof = exchange(EMPTY, request).proof()
    assert proof["eligible"] and proof["frames"][0]["request"]["kind"] == "chunked"
    assert proof["frames"][0]["request"]["trailers"] == ["x-trace"]


def test_pipeline_preserves_method_order_and_requires_every_response():
    tracker = HTTPKeepaliveTracker()
    tracker.feed_client(GET + HEAD)
    tracker.feed_server(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx")
    assert not tracker.proof()["eligible"] and tracker.proof()["pending_responses"] == 1
    tracker.feed_server(b"HTTP/1.1 200 OK\r\nContent-Length: 900\r\n\r\n")
    proof = tracker.proof()
    assert proof["eligible"] and proof["requests_completed"] == proof["responses_completed"] == 2
    assert [row["method"] for row in proof["frames"]] == ["GET", "HEAD"]
    assert [row["response"]["body_bytes"] for row in proof["frames"]] == [1, 0]


def test_coalesced_pipeline_and_partial_next_request():
    tracker = HTTPKeepaliveTracker()
    tracker.feed_client(GET + GET)
    tracker.feed_server(EMPTY + EMPTY)
    assert tracker.proof()["eligible"] and len(tracker.proof()["frames"]) == 2
    tracker.feed_client(b"GET /next HTTP/1.1\r\nHost:")
    assert not tracker.proof()["eligible"] and tracker.proof()["buffered_client_bytes"] > 0


def test_actual_eof_completes_close_delimited_body_but_never_idle_exemption():
    tracker = exchange(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nabc")
    assert not tracker.proof()["complete_framing"]
    tracker.server_eof()
    proof = tracker.proof()
    assert proof["complete_framing"] and not proof["eligible"]
    assert proof["frames"][0]["response"]["kind"] == "eof_delimited"
    assert proof["frames"][0]["response"]["body_bytes"] == 3


def test_eof_is_not_a_substitute_for_missing_declared_body():
    tracker = exchange(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nabc")
    tracker.server_eof()
    assert not tracker.proof()["eligible"] and not tracker.proof()["complete_framing"]
    assert tracker.proof()["failure"]["reason"] == "h11_protocol_error_at_eof"


@pytest.mark.parametrize("req,response,port", [
    (GET, EMPTY, 443),
    (b"\x16\x03\x01\x00\x05hello", EMPTY, 80),
    (b"CONNECT example.test:443 HTTP/1.1\r\nHost: example.test\r\n\r\n", EMPTY, 80),
    (b"GET / HTTP/1.1\r\nHost: example.test\r\nConnection: keep-alive, Upgrade\r\nUpgrade: websocket\r\n\r\n", EMPTY, 80),
    (GET, b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n", 80),
    (GET, b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", 80),
    (b"GET / HTTP/1.0\r\n\r\n", b"HTTP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n", 80),
])
def test_tls_upgrade_tunnel_and_nonpersistent_connections_stay_ineligible(req, response, port):
    assert not exchange(response, req, port=port).proof()["eligible"]


def test_no_request_unsolicited_response_and_bounded_tracking():
    assert not HTTPKeepaliveTracker().proof()["eligible"]
    unsolicited = HTTPKeepaliveTracker()
    unsolicited.feed_server(EMPTY)
    unsolicited.feed_client(GET)
    assert not unsolicited.proof()["eligible"]
    header = HTTPKeepaliveTracker()
    header.feed_client(b"GET / HTTP/1.1\r\nHost: example.test\r\nX-Huge: " + b"a" * 17000)
    assert not header.proof()["eligible"] and header.proof()["failure"]
    limited = HTTPKeepaliveTracker(max_transactions=1)
    limited.feed_client(GET + GET)
    limited.feed_server(EMPTY + EMPTY)
    assert not limited.proof()["eligible"] and len(limited.proof()["frames"]) <= 1
