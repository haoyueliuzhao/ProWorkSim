"""Conservative observation of plaintext HTTP/1.1 framing with pinned h11.

This module never forwards or changes bytes. An eligible proof is only a
necessary condition for treating an idle socket as a completed keepalive;
the relay must additionally prove both forwarding queues are empty.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
from pathlib import Path

import h11
from h11._connection import _body_framing

VERSION = "v203.2.3-strict-h11-http-idle-framing-r4"
H11_VERSION = "0.16.0"
MAX_HEADER_BYTES = 16384


class _RejectedFraming(ValueError):
    pass


@lru_cache(maxsize=1)
def parser_descriptor():
    root = Path(h11.__file__).resolve().parent
    return {"library": "h11", "version": h11.__version__, "required_version": H11_VERSION,
        "sources": [{"path": str(path), "name": path.name,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                    for path in sorted(root.glob("*.py"))],
        "documentation": "https://h11.readthedocs.io/en/latest/api.html",
        "framing_metadata_function": "h11._connection._body_framing"}


class HTTPKeepaliveTracker:
    """One synchronous observer per TCP connection, using two h11 endpoints.

    Feed only client bytes actually sent upstream and server bytes actually
    received. Mirrored h11 events advance the opposite endpoint's method/state
    context; their serialized output is discarded and never sent to any socket.
    """

    def __init__(self, port=80, *, max_transactions=256, max_buffer_bytes=262144):
        self.port = port
        self.max_transactions = max_transactions
        self.max_buffer_bytes = max_buffer_bytes
        self.request_parser = h11.Connection(h11.SERVER, max_incomplete_event_size=MAX_HEADER_BYTES)
        self.response_parser = h11.Connection(h11.CLIENT, max_incomplete_event_size=MAX_HEADER_BYTES)
        self.failure = None
        self.requests_started = self.requests_completed = 0
        self.responses_started = self.responses_completed = 0
        self.bytes_from_client = self.bytes_from_server = 0
        self.server_eof_seen = self.client_eof_seen = False
        self._request_closed = self._response_closed = False
        self.current = None
        self.frames = []
        if type(port) is not int or port != 80:
            self._fail("not_plaintext_http_port_80")
        elif h11.__version__ != H11_VERSION:
            self._fail("unreviewed_h11_version")
        elif type(max_transactions) is not int or not 1 <= max_transactions <= 256:
            self._fail("invalid_tracker_limit")
        elif type(max_buffer_bytes) is not int or not 65536 <= max_buffer_bytes <= 1048576:
            self._fail("invalid_tracker_limit")

    def _fail(self, reason, error=None):
        if self.failure is None:
            self.failure = {"reason": reason, "error_type": type(error).__name__ if error else None}

    @staticmethod
    def _headers(event):
        # h11 already validates and normalizes header syntax/duplicate lengths.
        # Its RFC precedence accepts TE+CL; our narrow exemption rejects that
        # potentially ambiguous combination rather than choosing a framing.
        headers = dict(event.headers)
        if b"content-length" in headers and b"transfer-encoding" in headers:
            raise _RejectedFraming("ambiguous_transfer_encoding_with_content_length")
        if b"upgrade" in headers or b"upgrade" in [item.strip() for item in headers.get(b"connection", b"").lower().split(b",")]:
            raise _RejectedFraming("protocol_upgrade_not_eligible")
        return headers

    @staticmethod
    def _framing(method, event, headers):
        kind, args = _body_framing(method, event)
        return {"kind": "eof_delimited" if kind == "http/1.0" else kind,
            "framed_content_length": args[0] if kind == "content-length" else None,
            "declared_content_length": int(headers[b"content-length"]) if b"content-length" in headers else None,
            "transfer_encoding": headers.get(b"transfer-encoding", b"").decode("ascii"),
            "complete": False, "body_bytes": 0, "trailers": []}

    def feed_client(self, data):
        self._feed(data, client=True)

    def feed_server(self, data):
        self._feed(data, client=False)

    def _feed(self, data, *, client):
        if self.failure:
            return
        if not isinstance(data, bytes) or not data:
            self._fail("feed_requires_nonempty_bytes_use_explicit_eof")
            return
        if not client and self.current is None:
            self._fail("response_without_observed_request_headers")
            return
        if client:
            self.bytes_from_client += len(data)
        else:
            self.bytes_from_server += len(data)
        try:
            parser = self.request_parser if client else self.response_parser
            parser.receive_data(data)
            if sum(len(conn.trailing_data[0]) for conn in (self.request_parser, self.response_parser)) > self.max_buffer_bytes:
                self._fail("tracker_buffer_bound")
                return
            self._pump()
            if self.current is None and self.response_parser.trailing_data[0]:
                self._fail("unpaired_response_bytes_after_completed_cycle")
        except _RejectedFraming as error:
            self._fail(str(error))
        except h11.ProtocolError as error:
            self._fail("h11_protocol_error", error)
        except Exception as error:
            self._fail("tracker_error", error)

    def server_eof(self):
        self._eof(client=False)

    def client_eof(self):
        self._eof(client=True)

    def _eof(self, *, client):
        if client:
            self.client_eof_seen = True
        else:
            self.server_eof_seen = True
        if self.failure:
            return
        try:
            (self.request_parser if client else self.response_parser).receive_data(b"")
            self._pump()
        except _RejectedFraming as error:
            self._fail(str(error))
        except h11.ProtocolError as error:
            self._fail("h11_protocol_error_at_eof", error)
        except Exception as error:
            self._fail("tracker_error_at_eof", error)

    def _event(self, event, *, client):
        opposite = self.response_parser if client else self.request_parser
        if isinstance(event, h11.ConnectionClosed):
            if client:
                self._request_closed = True
            else:
                self._response_closed = True
            opposite.send_with_data_passthrough(event)
            return
        if isinstance(event, h11.Request):
            if self.current is not None or self.requests_started >= self.max_transactions:
                self._fail("unpaired_request_or_transaction_bound")
                return
            headers = self._headers(event)
            if event.method == b"CONNECT" or len(event.method) > 32 or event.http_version != b"1.1":
                self._fail("unsupported_method_tunnel_or_http_version")
                return
            if event.target.lower().startswith(b"https:"):
                self._fail("https_target_not_eligible")
                return
            self.requests_started += 1
            self.current = {"sequence": self.requests_started, "method": event.method.decode("ascii"),
                "status": None, "informational_statuses": [], "request": self._framing(event.method, event, headers),
                "response": None}
        elif isinstance(event, h11.InformationalResponse):
            self._headers(event)
            if self.current is None or event.status_code == 101 or len(self.current["informational_statuses"]) >= 32:
                self._fail("upgrade_or_unpaired_informational_response")
                return
            self.current["informational_statuses"].append(event.status_code)
        elif isinstance(event, h11.Response):
            headers = self._headers(event)
            if self.current is None or self.current["response"] is not None or event.http_version != b"1.1":
                self._fail("unpaired_response_or_http_version")
                return
            self.responses_started += 1
            self.current["status"] = event.status_code
            self.current["response"] = self._framing(self.current["method"].encode("ascii"), event, headers)
        elif isinstance(event, h11.Data):
            frame = self.current["request" if client else "response"]
            frame["body_bytes"] += len(event.data)
        elif isinstance(event, h11.EndOfMessage):
            frame = self.current["request" if client else "response"]
            if any(name in {b"content-length", b"transfer-encoding", b"connection", b"upgrade", b"host"}
                   for name, _ in event.headers):
                self._fail("framing_or_routing_header_in_trailer")
                return
            frame["complete"] = True
            frame["trailers"] = [name.decode("ascii") for name, _ in event.headers]
            if client:
                self.requests_completed += 1
            else:
                self.responses_completed += 1
        else:
            self._fail("unsupported_h11_event")
            return
        # Discard generated bytes: this is state bookkeeping, never forwarding.
        opposite.send_with_data_passthrough(event)

    def _pump(self):
        for _ in range(65536):
            progress = False
            for client, parser, closed in ((True, self.request_parser, self._request_closed),
                                            (False, self.response_parser, self._response_closed)):
                if closed or (not client and self.current is None and not self.server_eof_seen):
                    continue
                event = parser.next_event()
                if event is h11.NEED_DATA or event is h11.PAUSED:
                    continue
                self._event(event, client=client)
                if self.failure:
                    return
                progress = True
            if (self.current is not None and self.current["request"]["complete"]
                    and self.current["response"] is not None and self.current["response"]["complete"]):
                if not any(frame is self.current for frame in self.frames):
                    self.frames.append(self.current)
                if all(conn.our_state is h11.DONE and conn.their_state is h11.DONE
                       for conn in (self.request_parser, self.response_parser)):
                    self.request_parser.start_next_cycle()
                    self.response_parser.start_next_cycle()
                    self.current = None
                    progress = True
            if not progress:
                return
        self._fail("tracker_event_bound")

    def proof(self):
        buffered_client = len(self.request_parser.trailing_data[0])
        buffered_server = len(self.response_parser.trailing_data[0])
        idle = all(conn.our_state is h11.IDLE and conn.their_state is h11.IDLE
                   for conn in (self.request_parser, self.response_parser))
        complete = (self.requests_started > 0 and self.requests_started == self.requests_completed
                    == self.responses_started == self.responses_completed == len(self.frames))
        if self.failure:
            reason = self.failure["reason"]
        elif self.server_eof_seen or self.client_eof_seen:
            reason = "eof_observed_not_idle_keepalive"
        elif not complete:
            reason = "no_complete_exchange_or_pending_request_response"
        elif buffered_client or buffered_server:
            reason = "unparsed_or_pipelined_bytes_pending"
        elif not idle or self.current is not None:
            reason = "connection_not_reusable_idle"
        else:
            reason = "complete_http11_keepalive_framing"
        return {"version": VERSION, "h11_version": h11.__version__, "port": self.port,
            "limits": {"max_transactions": self.max_transactions,
                       "max_incomplete_header_bytes": MAX_HEADER_BYTES, "max_buffer_bytes": self.max_buffer_bytes},
            "eligible": reason == "complete_http11_keepalive_framing", "reason": reason,
            "failure": copy.deepcopy(self.failure), "requests_started": self.requests_started,
            "requests_completed": self.requests_completed, "responses_started": self.responses_started,
            "responses_completed": self.responses_completed,
            "pending_responses": self.requests_started - self.responses_completed,
            "complete_framing": complete, "frames": copy.deepcopy(self.frames),
            "current_frame": copy.deepcopy(self.current), "buffered_client_bytes": buffered_client,
            "buffered_server_bytes": buffered_server, "server_eof": self.server_eof_seen,
            "client_eof": self.client_eof_seen, "bytes_from_client": self.bytes_from_client,
            "bytes_from_server": self.bytes_from_server,
            "h11_states": {"request_parser": [str(self.request_parser.our_state), str(self.request_parser.their_state)],
                           "response_parser": [str(self.response_parser.our_state), str(self.response_parser.their_state)]},
            "relay_empty_forwarding_queues_still_required": True,
            "application_or_test_success_inferred": False, "forwarded_bytes_modified": False}
