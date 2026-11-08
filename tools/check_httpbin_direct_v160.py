"""One bounded direct public-endpoint check, only after this batch is authorized."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import time

ROOT = Path(__file__).resolve().parents[1]
HOST = "httpbin.org"
MAX_CONNECTIONS = 4
MAX_APPLICATION_BYTES = 64 * 1024
OUTPUT = ROOT / "artifacts/software-benchmark-v160/httpbin-direct-diagnostic-r1.json"
INTENT = ROOT / "artifacts/software-benchmark-v160/httpbin-direct-intent-r1.json"
RESOLUTION = ROOT / "runs/software-benchmark-v160/requests1724-environment-r1/network-resolution.json"
PLAN = RESOLUTION.parent / 'plan.json'


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return reference(path)


class ApplicationBudget:
    def __init__(self, maximum=MAX_APPLICATION_BYTES):
        self.maximum, self.used = maximum, 0

    def consume(self, size):
        if size < 0 or self.used + size > self.maximum:
            raise RuntimeError("The one-run HTTP application payload allowance is exhausted")
        self.used += size


class LimitedReader(io.RawIOBase):
    def __init__(self, source, budget):
        self.source, self.budget = source, budget

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.budget.maximum - self.budget.used
        if remaining <= 0:
            raise RuntimeError("The one-run HTTP application payload allowance is exhausted")
        data = self.source.read(min(len(buffer), remaining))
        self.budget.consume(len(data))
        buffer[: len(data)] = data
        return len(data)

    def close(self):
        try:
            self.source.close()
        finally:
            super().close()


class LimitedSocket:
    def __init__(self, sock, budget):
        self.sock, self.budget = sock, budget

    def sendall(self, data):
        self.budget.consume(len(data))
        return self.sock.sendall(data)

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("Only bounded HTTP response reading is allowed")
        return io.BufferedReader(LimitedReader(self.sock.makefile("rb", buffering=0), self.budget))

    def close(self):
        return self.sock.close()


def get_contract_valid(status, body):
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        return False
    return (
        status == 200
        and isinstance(value, dict)
        and isinstance(value.get("headers"), dict)
        and value.get("args") == {}
        and value.get("url") in ("http://httpbin.org/get", "https://httpbin.org/get")
    )


def readonly_panel_identity():
    from proworksim import software_benchmark_scope_v160 as scope
    plan = scope.validate_plan(scope.load(reference(PLAN)))
    if os.getuid() == 0 or set(plan['environments']) != {scope.TASK}:
        raise PermissionError('Only the separately planned1724 environment probe is admitted')
    return {'plan': reference(PLAN), 'scope': reference(scope.__file__),
            'public_hostname': HOST, 'ports': [80,443], 'instance_id': scope.TASK,
            'credentials_read': False, 'planned_model_episodes': 0, 'planned_controls': 2}


def run():
    from proworksim import software_benchmark_scope_v160 as scope
    scope.require_probe_allowed('v160.probe')
    if os.getuid() == 0 or any(path.exists() for path in (OUTPUT, INTENT, RESOLUTION)):
        raise PermissionError(
            "One ordinary-user attempt only; preserve entered or existing evidence"
        )
    panel_identity = readonly_panel_identity()
    started = time.time()
    intent = write_once(
        INTENT,
        {
            "version": "v160-bounded-httpbin-check-intent-r1",
            "source": reference(__file__),
            "started_unix": started,
            "maximum_connections": MAX_CONNECTIONS,
            "maximum_application_bytes": MAX_APPLICATION_BYTES,
            "proxy_used": False,
            "automatic_retry": False,
            "mode": "authorized_activation",
            "panel_identity": panel_identity,
            "scope": panel_identity["scope"],
            "model_calls": 0,
            "Docker_operations": 0,
        },
    )
    prior_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("90-second direct-probe boundary")),
    )
    signal.alarm(90)
    budget = ApplicationBudget()
    ips, results = [], []
    failure = None
    try:
        ips = sorted(
            {row[4][0] for row in socket.getaddrinfo(HOST, 443, socket.AF_INET, socket.SOCK_STREAM)}
        )
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("Only current public IPv4 results for the fixed hostname are allowed")
        matrix = [(ip, port) for ip in ips[:2] for port in (80, 443)]
        assert len(matrix) <= MAX_CONNECTIONS
        for ip, port in matrix:
            item = {"ip": ip, "port": port, "current_DNS_member": True, "request_path": "/get"}
            began = time.monotonic()
            sock = connection = None
            before = budget.used
            try:
                if budget.used >= budget.maximum:
                    raise RuntimeError("No application payload remains")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(8)
                sock.connect((ip, port))
                if port == 443:
                    context = ssl.create_default_context()
                    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
                        raise ValueError("TLS trust/hostname verification cannot be disabled")
                    sock = context.wrap_socket(sock, server_hostname=HOST)
                connection = http.client.HTTPConnection(HOST, port, timeout=8)
                connection.auto_open = 0
                connection.sock = LimitedSocket(sock, budget)
                connection.request(
                    "GET",
                    "/get",
                    headers={
                        "Host": HOST,
                        "Connection": "close",
                        "User-Agent": "ProWorkSim-v160-public-environment-check",
                    },
                )
                response = connection.getresponse()
                body = response.read(MAX_APPLICATION_BYTES)
                item.update(
                    status=response.status,
                    body_bytes=len(body),
                    body_sha256=hashlib.sha256(body).hexdigest(),
                    get_contract_valid=get_contract_valid(response.status, body),
                    TLS_verified=port == 443,
                    TLS_verify_mode=int(context.verify_mode) if port == 443 else None,
                    TLS_check_hostname=context.check_hostname if port == 443 else None,
                )
            except Exception as error:
                item.update(
                    get_contract_valid=False,
                    error={"type": type(error).__name__, "message": str(error)},
                )
            finally:
                if connection is not None:
                    connection.close()
                elif sock is not None:
                    sock.close()
                item.update(
                    duration_seconds=time.monotonic() - began,
                    application_bytes=budget.used - before,
                )
                results.append(item)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prior_handler)
    selected = next(
        (
            ip
            for ip in ips[:2]
            if all(
                any(
                    r["ip"] == ip and r["port"] == port and r.get("get_contract_valid") is True
                    for r in results
                )
                for port in (80, 443)
            )
        ),
        None,
    )
    diagnostic = {
        "version": "v160-public-httpbin-reachability-r1",
        "intent": intent,
        "source": reference(__file__),
        "panel_identity": panel_identity,
            "scope": panel_identity["scope"],
        "mode": "authorized_activation",
        "host": HOST,
        "started_unix": started,
        "finished_unix": time.time(),
        "current_DNS_ipv4": ips,
        "probes": results,
        "selected_ip": selected,
        "passed": selected is not None,
        "error": failure,
        "maximum_connections": MAX_CONNECTIONS,
        "actual_probe_slots": len(results),
        "maximum_application_bytes": MAX_APPLICATION_BYTES,
        "application_bytes": budget.used,
        "application_budget_counts_HTTP_request_and_response_headers_and_body": True,
        "TLS_handshake_wire_bytes_not_application_payload": True,
        "model_calls": 0,
        "Docker_operations": 0,
        "proxy_used": False,
        "host_listener": False,
        "shared_host_configuration_changes": 0,
        "automatic_retry": False,
        "container_original_CA_not_tested_by_host_probe": True,
    }
    proof = write_once(OUTPUT, diagnostic)
    resolution = None
    if selected is not None:
        resolution = write_once(
            RESOLUTION,
            {
                "version": "v160-current-public-httpbin-r1",
                "source": "v160_current_DNS_and_bounded_endpoint_probe",
                "scope": panel_identity["scope"],
                "hostname": HOST,
                "ports": [80, 443],
                "ipv4": [selected],
                "selected_ip": selected,
                "diagnostic": proof,
                "automatic_retry": False,
                "container_side_DNS": False,
                "host_original_CA_probe_does_not_replace_grading_controls": True,
            },
        )
    return {"diagnostic": proof, "network_resolution": resolution, "passed": selected is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
