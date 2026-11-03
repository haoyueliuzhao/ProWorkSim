"""Six bounded public GET probes; no proxy, model, Docker or host changes."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/software-benchmark-v114/httpbin-direct-diagnostic-r1.json"
HOST = "httpbin.org"
OLD_IP = "3.211.106.232"
MAX_BODY = 65536


def run():
    if os.getuid() == 0 or OUTPUT.exists():
        raise PermissionError("One ordinary-user diagnostic only; preserve earlier evidence")
    signal.signal(
        signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("90-second probe boundary"))
    )
    signal.alarm(90)
    started = time.time()
    ips = sorted(
        {row[4][0] for row in socket.getaddrinfo(HOST, 443, socket.AF_INET, socket.SOCK_STREAM)}
    )
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Only current public official-host IPv4 addresses may be inspected")
    selected = [OLD_IP, *[ip for ip in ips if ip != OLD_IP][:2]]
    results = []
    for ip in selected:
        for port in (80, 443):
            entry = {
                "ip": ip,
                "port": port,
                "current_DNS_member": ip in ips,
                "request_path": "/get",
            }
            sock = connection = None
            began = time.monotonic()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(8)
                sock.connect((ip, port))
                if port == 443:
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=HOST)
                connection = http.client.HTTPConnection(HOST, port, timeout=8)
                connection.sock = sock
                connection.request(
                    "GET",
                    "/get",
                    headers={
                        "Host": HOST,
                        "Connection": "close",
                        "User-Agent": "ProWorkSim-v114-public-environment-check",
                    },
                )
                response = connection.getresponse()
                body = response.read(MAX_BODY)
                entry.update(
                    status=response.status,
                    body_bytes=len(body),
                    body_sha256=hashlib.sha256(body).hexdigest(),
                    content_type=response.getheader("content-type"),
                    server=response.getheader("server"),
                    body_truncated_at_limit=len(body) == MAX_BODY,
                    TLS_verified=port == 443,
                )
                try:
                    value = json.loads(body)
                    entry["json_keys"] = sorted(value) if isinstance(value, dict) else None
                    entry["get_contract_valid"] = (
                        response.status == 200
                        and isinstance(value, dict)
                        and isinstance(value.get("headers"), dict)
                        and value.get("args") == {}
                        and value.get("url") in (f"http://{HOST}/get", f"https://{HOST}/get")
                    )
                except (ValueError, UnicodeError):
                    entry["get_contract_valid"] = False
            except Exception as error:
                entry["error"] = {"type": type(error).__name__, "message": str(error)}
            finally:
                if connection is not None:
                    connection.close()
                elif sock is not None:
                    sock.close()
                entry["duration_seconds"] = time.monotonic() - began
                results.append(entry)
    signal.alarm(0)
    value = {
        "version": "v114-public-httpbin-reachability-r1",
        "host": HOST,
        "started_unix": started,
        "current_DNS_ipv4": ips,
        "original_frozen_ipv4": OLD_IP,
        "probes": results,
        "maximum_connections": 6,
        "actual_connection_attempts": len(results),
        "maximum_response_bytes": MAX_BODY * 6,
        "model_calls": 0,
        "Docker_operations": 0,
        "proxy_used": False,
        "host_listener": False,
        "server_configuration_changed": False,
        "container_original_CA_not_tested_by_host_probe": True,
        "original_failed_controls_reclassified": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    run()
