"""One non-streaming HTTP attempt; retry policy belongs to the model adapter.

No credential enters a serializable policy configuration or returned record.
This transport never executes a world action or interprets assistant tool calls.
"""

import base64
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from .storage import json_bytes


class TransportFailure(Exception):
    def __init__(self, code, message, *, retryable=False, details=None):
        super().__init__(message)
        self.code, self.retryable = code, retryable
        self.details = details or {}


class HTTPModelTransport:
    def __init__(self, base_url, *, api_key_env="DEEPSEEK_API_KEY"):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Model base_url must be an HTTP endpoint without embedded credentials/query"
            )
        if api_key_env is None and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                "Credential-free model transport is restricted to an explicit loopback endpoint"
            )
        if api_key_env is not None and (
            not isinstance(api_key_env, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) is None
        ):
            raise ValueError(
                "api_key_env must be an environment variable identifier, not a credential"
            )
        self.api_key_env = api_key_env
        self._loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}

    def complete(self, request, *, timeout_seconds):
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if self.api_key_env and not key:
            raise TransportFailure(
                "missing_credential", "Configured model credential variable is absent"
            )
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json_bytes(request),
            headers=headers,
            method="POST",
        )
        try:
            opener = (
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open
                if self._loopback
                else urllib.request.urlopen
            )
            with opener(request, timeout=timeout_seconds) as response:
                status, body, response_headers = (
                    response.status,
                    response.read(),
                    dict(response.headers),
                )
        except urllib.error.HTTPError as error:
            status, body, response_headers = error.code, error.read(), dict(error.headers or {})
        except (TimeoutError, socket.timeout):
            raise TransportFailure(
                "timeout", "HTTP model attempt timed out", retryable=True
            ) from None
        except urllib.error.URLError as error:
            timeout = isinstance(error.reason, (TimeoutError, socket.timeout))
            raise TransportFailure(
                "timeout" if timeout else "connection_error",
                "HTTP model attempt could not complete",
                retryable=True,
                details={"reason_type": type(error.reason).__name__},
            ) from None
        text = body.decode("utf-8", errors="replace")
        redactions = []
        if key and key in text:
            text = text.replace(key, "<redacted credential>")
            redactions.append("credential echoed in response body")
        safe_headers = {
            name: (value.replace(key, "<redacted credential>") if key else value)
            for name, value in response_headers.items()
        }
        result = {
            "http_status": status,
            "raw_body": text,
            "response_headers": safe_headers,
            "response_redactions": redactions,
        }
        if "\ufffd" in text and not redactions:
            result["raw_body_base64"] = base64.b64encode(body).decode("ascii")
        try:
            result["body"] = json.loads(text)
        except (ValueError, TypeError):
            result["body"] = None
        return result
