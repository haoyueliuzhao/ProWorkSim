"""Two explicitly authorized, bounded TLS diagnostics; never official scoring.

Ordinary host Python may connect only to its private Docker socket and frozen
public httpbin.org:443 addresses. No host listener, namespace or mount operation
is used. The original container client verifies the real server itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

from proworksim import software_benchmark_tls_policy_v059 as policy
from proworksim import software_benchmark_tls_transport_v059 as transport
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_grading_environment_v058 import namespace_evidence

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs/software-benchmark-v059/tls-probe-r1-20261025"
VERSION = "v059-original-ca-live-tls-diagnostic-r1"
PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
OVERRIDES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
             "NO_PROXY", "no_proxy", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE",
             "SSL_CERT_DIR", "OPENSSL_CONF", "PYTHONHTTPSVERIFY", "SSLKEYLOGFILE")

PROBE_SOURCE = r'''
import hashlib, inspect, json, os, pathlib, signal, socket, ssl, sys
overrides = ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy",
             "NO_PROXY","no_proxy","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE","SSL_CERT_FILE",
             "SSL_CERT_DIR","OPENSSL_CONF","PYTHONHTTPSVERIFY","SSLKEYLOGFILE")
for key in overrides: os.environ.pop(key, None)
def deadline(signum, frame): raise TimeoutError("Diagnostic process deadline")
signal.signal(signal.SIGALRM, deadline); signal.alarm(25)
mode = sys.argv[1]
result = {"mode":mode,"tls_completed":False,"http_status":None,"service_http_200":False,
          "url":"https://httpbin.org/get","redirects_allowed":False,"ca_overrides_removed":list(overrides)}
ca = before = session = None
try:
    import requests
    module = pathlib.Path(requests.__file__).resolve()
    if not module.is_relative_to(pathlib.Path('/testbed/requests')): raise RuntimeError("Wrong Requests source")
    ca = pathlib.Path(requests.certs.where()).resolve()
    if ca != pathlib.Path('/testbed/requests/cacert.pem'): raise RuntimeError("Wrong original CA path")
    for selected in (requests.utils.DEFAULT_CA_BUNDLE_PATH, requests.adapters.DEFAULT_CA_BUNDLE_PATH):
        if pathlib.Path(selected).resolve() != ca: raise RuntimeError("CA selectors differ")
    before = ca.read_bytes()
    result.update(python=sys.version,openssl=ssl.OPENSSL_VERSION,requests_version=requests.__version__,
                  requests_source=str(module),requests_source_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),
                  original_ca_path=str(ca),ca_sha256_before=hashlib.sha256(before).hexdigest(),ca_bytes=len(before))
    session = requests.Session()
    if session.verify is not True: raise RuntimeError("Unexpected Session.verify")
    adapter = session.get_adapter(result['url'])
    result.update(session_verify=True,adapter_class=type(adapter).__module__+'.'+type(adapter).__name__,
                  adapter_source=inspect.getsourcefile(type(adapter)))
    if mode == 'stdlib':
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        if context.verify_mode != ssl.CERT_REQUIRED or context.check_hostname is not True:
            raise RuntimeError("TLS verification disabled")
        result.update(cert_required=True,hostname_check=True,system_ca_loaded=False)
        with socket.create_connection(('httpbin.org',443),timeout=10) as raw:
            with context.wrap_socket(raw,server_hostname='httpbin.org') as connection:
                result.update(tls_completed=True,tls_version=connection.version(),cipher=connection.cipher(),
                              peer_certificate_sha256=hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest())
                connection.sendall(b'GET /get HTTP/1.1\r\nHost: httpbin.org\r\nConnection: close\r\n\r\n')
                body = bytearray()
                while True:
                    data=connection.recv(4096)
                    if not data: break
                    body.extend(data)
                    if len(body)>65536: raise RuntimeError("HTTP response exceeds diagnostic bound")
        line=bytes(body).split(b'\r\n',1)[0].split()
        if len(line)<2 or not line[0].startswith(b'HTTP/'): raise RuntimeError("Invalid HTTP response")
        result.update(http_status=int(line[1]),response_bytes=len(body),response_sha256=hashlib.sha256(body).hexdigest())
    elif mode == 'legacy':
        request=requests.Request('GET',result['url'],headers={'Connection':'close'}).prepare()
        if request.url != result['url']: raise RuntimeError("Unexpected prepared URL")
        try:
            response=session.send(request,timeout=10,allow_redirects=False,stream=True)
            try:
                result.update(tls_completed=True,http_status=response.status_code)
                body=bytearray()
                for chunk in response.iter_content(4096):
                    body.extend(chunk)
                    if len(body)>65536: raise RuntimeError("HTTP response exceeds diagnostic bound")
                result.update(response_bytes=len(body),response_sha256=hashlib.sha256(body).hexdigest())
            finally: response.close()
        finally: session.close()
    else: raise RuntimeError("Unexpected probe mode")
    after=ca.read_bytes()
    result.update(ca_sha256_after=hashlib.sha256(after).hexdigest(),ca_unchanged=before==after,
                  service_http_200=result['http_status']==200)
    if before!=after: raise RuntimeError("Original CA changed")
    result['status']='completed'
except Exception as error:
    result.update(status='failed',error={'type':type(error).__name__,'message':str(error)[:1500]})
finally:
    signal.alarm(0)
    if session is not None: session.close()
    if ca is not None and before is not None:
        try:
            after=ca.read_bytes()
            result.update(ca_sha256_after=hashlib.sha256(after).hexdigest(),ca_unchanged=before==after)
            if before!=after: result.update(status='failed',error={'type':'ChangedCA','message':'Original CA changed'})
        except Exception as error:
            result.update(ca_unchanged=None,ca_check_error=str(error)[:500])
print(json.dumps(result),flush=True)
'''


def container_options(image_id, name, labels):
    return dict(image=image_id, name=name, labels=labels, user="root", detach=True,
                command=["tail", "-f", "/dev/null"], network_mode="none", privileged=False,
                mem_limit=4 * 1024**3, memswap_limit=4 * 1024**3, nano_cpus=2 * 10**9,
                pids_limit=64, cap_drop=["ALL"], cap_add=["NET_BIND_SERVICE"],
                security_opt=["no-new-privileges:true"], ipc_mode="private",
                extra_hosts={"httpbin.org": "127.0.0.1"},
                environment={**{key: "" for key in OVERRIDES}, "PYTHONDONTWRITEBYTECODE": "1"})


def inspect_isolation(attrs, image_id, labels):
    h = attrs["HostConfig"]
    actual_labels = attrs.get("Config", {}).get("Labels") or {}
    if (attrs.get("Image") != image_id or any(actual_labels.get(k) != v for k, v in labels.items())
            or h.get("NetworkMode") != "none" or h.get("Privileged")
            or h.get("Memory") != 4 * 1024**3 or h.get("MemorySwap") != 4 * 1024**3
            or h.get("NanoCpus") != 2 * 10**9 or h.get("PidsLimit") != 64
            or h.get("CapAdd") != ["NET_BIND_SERVICE"] or h.get("CapDrop") != ["ALL"]
            or h.get("SecurityOpt") != ["no-new-privileges:true"]
            or h.get("ExtraHosts") != ["httpbin.org:127.0.0.1"]):
        raise ValueError("Actual diagnostic container differs from the approved restrictions")
    if attrs.get("Mounts") or any(h.get(k) for k in ("Binds", "Devices", "DeviceRequests", "PortBindings",
                                                     "PublishAllPorts", "Links", "Sysctls", "VolumesFrom")):
        raise ValueError("Unexpected host material or exposed port")
    if any(h.get(k) not in (None, "", "private") for k in ("PidMode", "IpcMode", "UTSMode", "CgroupnsMode")):
        raise ValueError("Host or shared namespace is forbidden")
    if h.get("UsernsMode") not in (None, "") or attrs.get("Config", {}).get("User") not in ("root", "0", "0:0"):
        raise ValueError("Unexpected diagnostic user configuration")


def exec_text(container, argv):
    result = container.exec_run(argv, workdir="/testbed")
    if result.exit_code != 0:
        raise RuntimeError(result.output.decode("utf-8", "replace")[-1600:])
    return result.output.decode("utf-8")


def freeze_resolution():
    policy.require_tls_diagnostic_allowed("v059.resolve")
    records = socket.getaddrinfo(policy.TARGET_HOST, 443, socket.AF_INET, socket.SOCK_STREAM)
    addresses = policy.validate_ipv4_targets([record[4][0] for record in records])
    return {"hostname": policy.TARGET_HOST, "port": 443, "ipv4": list(addresses),
            "selected_ip": addresses[0], "automatic_retry": False}


def install_socket_guard(docker_socket, addresses):
    def audit(event, args):
        if event in {"socket.bind", "socket.getaddrinfo"}:
            raise RuntimeError("No host listeners or additional DNS resolution are permitted")
        if event == "socket.connect":
            sock, address = args
            if sock.family == socket.AF_UNIX and isinstance(address, str) and str(Path(address).resolve()) == docker_socket:
                return
            if sock.family == socket.AF_INET:
                policy.validate_connect_target(address, addresses)
                return
            raise RuntimeError("Socket outside the reviewed Docker and HTTPS endpoints")
    sys.addaudithook(audit)


def run_probe(client, container, task, mode, resolution, budget, folder):
    policy.require_tls_diagnostic_allowed("v059.probe", task)
    ready, cancelled = threading.Event(), threading.Event()
    result = {}
    exec_id = client.api.exec_create(container.id, [PYTHON, "-u", "-B", "-c", transport.CONTAINER_RELAY_SOURCE],
                                     stdin=True, stdout=True, stderr=True, tty=False)["Id"]
    channel = client.api.exec_start(exec_id, socket=True, tty=False)

    def probe():
        if not ready.wait(16) or cancelled.is_set():
            result["probe"] = {"status": "not_started", "reason": "relay_not_ready"}
            return
        try:
            outcome = container.exec_run([PYTHON, "-u", "-B", "-c", PROBE_SOURCE, mode],
                                         workdir="/testbed", demux=True)
            stdout, stderr = outcome.output
            result["probe_exit_code"] = outcome.exit_code
            result["probe_stderr"] = (stderr or b"").decode("utf-8", "replace")[-2000:]
            result["probe"] = json.loads((stdout or b"").decode("utf-8"))
        except Exception as error:
            result["probe"] = {"status": "failed", "error": {"type": type(error).__name__, "message": str(error)[:1500]}}

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    result["transport"] = transport.relay_once(channel, resolution["selected_ip"], budget,
        instance_id=task, resolved_ips=resolution["ipv4"], on_ready=ready.set)
    cancelled.set()
    ready.set()
    thread.join(timeout=min(30, max(1, budget.remaining_seconds(time.monotonic()))))
    result["probe_thread_finished"] = not thread.is_alive()
    result["relay_exec"] = client.api.exec_inspect(exec_id)
    exit_deadline = time.monotonic() + min(2, budget.remaining_seconds(time.monotonic()))
    while result["relay_exec"].get("Running") and time.monotonic() < exit_deadline:
        time.sleep(.05)
        result["relay_exec"] = client.api.exec_inspect(exec_id)
    # Retain only diagnostic execution state, not all daemon metadata.
    result["relay_exec"] = {k: result["relay_exec"].get(k) for k in ("Running", "ExitCode", "ContainerID")}
    proof = result.get("probe", {})
    trusted = (proof.get("requests_source") == "/testbed/requests/__init__.py"
               and proof.get("original_ca_path") == "/testbed/requests/cacert.pem"
               and proof.get("ca_unchanged") is True and proof.get("session_verify") is True)
    result.update(version=VERSION, instance_id=task, mode=mode,
                  trusted_original_client=trusted, official_scoring=False)
    write_new(folder / (mode + ".json"), result)
    if thread.is_alive():
        raise RuntimeError("Probe process did not finish within its diagnostic budget")
    return result


def run_task(client, authorization, task, resolution, folder):
    policy.require_tls_diagnostic_allowed("v059.container.create", task)
    image_id = authorization["image_ids"][task]
    original = policy.validate_task_image(authorization, task, image_id)
    mapping = json.loads(checked(original["baseline_mapping"]).read_bytes())
    image = client.images.get(image_id)
    if image.id != image_id or image.attrs.get("Os") != "linux" or image.attrs.get("Architecture") != "amd64":
        raise ValueError("Fixed local diagnostic image unavailable")
    folder.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256((str(RUN_ROOT) + task).encode()).hexdigest()
    name = "pws-v059-" + task + "-" + identity[:12]
    labels = {"proworksim.owner": VERSION, "proworksim.diagnostic": identity, "proworksim.task": task}
    container = None
    tracking = {"create_result_unknown": False, "owned_container_ids": [], "cleanup_errors": []}
    result = {"instance_id": task, "image_id": image_id, "probes": [], "status": "incomplete"}
    timer = None
    deadline_reached = threading.Event()
    try:
        started = time.monotonic()
        tracking["create_result_unknown"] = True
        container = client.containers.create(**container_options(image_id, name, labels))
        tracking["owned_container_ids"] = [container.id]
        tracking["create_result_unknown"] = False
        container.reload()
        inspect_isolation(container.attrs, image_id, labels)
        policy.require_tls_diagnostic_allowed("v059.container.start", task)
        def expire():
            deadline_reached.set()
            try:
                container.stop(timeout=3)
            except Exception as error:
                tracking["deadline_stop_error"] = str(error)[:500]

        remaining = 120 - (time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError("Container creation exceeded diagnostic deadline")
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        container.start()
        container.reload()
        inspect_isolation(container.attrs, image_id, labels)
        baseline = exec_text(container, ["git", "-c", "safe.directory=/testbed", "rev-parse", "HEAD", "HEAD^{tree}"]).splitlines()
        clean = exec_text(container, ["git", "-c", "safe.directory=/testbed", "status", "--porcelain"])
        if baseline != [mapping["official_head"], mapping["official_tree"]] or clean:
            raise ValueError("Diagnostic repository is not the fixed clean baseline")
        host = {k: os.stat("/proc/self/ns/" + k).st_ino for k in ("net", "mnt", "pid", "ipc")}
        inside = json.loads(exec_text(container, [PYTHON, "-B", "-c", "import os,json;print(json.dumps({k:os.stat('/proc/self/ns/'+k).st_ino for k in ('net','mnt','pid','ipc')}))"]))
        result["isolation"] = namespace_evidence(inside, host)
        result["initial_tree"] = baseline
        budget = transport.TransferBudget()
        budget.started_at = started
        for mode in ("stdlib", "legacy"):
            outcome = run_probe(client, container, task, mode, resolution, budget, folder)
            result["probes"].append(outcome)
            if not outcome["transport"]["upstream_connected"]:
                # An import/CA failure may precede the first TCP attempt.
                # Only an accepted relay connection proves upstream connect was attempted.
                result["shared_transport_unavailable"] = outcome["transport"].get("accepted") is True
                result["probe_connection_not_established"] = True
                break
        result["final_tree_clean"] = not exec_text(container, ["git", "-c", "safe.directory=/testbed", "status", "--porcelain"])
        result.update(status="diagnostic_complete", elapsed_seconds=time.monotonic() - started,
                      payload_bytes=budget.bytes_used, tcp_sessions=budget.sessions)
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)[:2000]})
    finally:
        if timer:
            timer.cancel()
            timer.join(timeout=20)
            if timer.is_alive():
                tracking["cleanup_errors"].append("Deadline watcher did not finish")
        if container is None and tracking["create_result_unknown"]:
            try:
                possible = client.containers.get(name)
                possible.reload()
                possible_labels = possible.attrs.get("Config", {}).get("Labels") or {}
                if (possible.attrs.get("Image") == image_id
                        and all(possible_labels.get(k) == v for k, v in labels.items())):
                    container = possible
                    tracking["owned_container_ids"] = [possible.id]
                    tracking["create_result_unknown"] = False
            except Exception as error:
                tracking["creation_recovery_error"] = str(error)[:500]
        if container is not None:
            try:
                container.reload()
                actual_labels = container.attrs.get("Config", {}).get("Labels") or {}
                if (container.id not in tracking["owned_container_ids"]
                        or container.attrs.get("Image") != image_id
                        or any(actual_labels.get(k) != v for k, v in labels.items())):
                    raise ValueError("Container ownership changed; refusing cleanup")
                if container.attrs["State"]["Running"]:
                    container.stop(timeout=5)
                container.reload()
                if container.attrs["State"]["Running"]:
                    raise RuntimeError("Owned container still running")
                container.remove(force=False)
            except Exception as error:
                tracking["cleanup_errors"].append(str(error)[:1000])
        result["deadline_reached"] = deadline_reached.is_set()
        tracking["quiescent"] = not tracking["create_result_unknown"] and not tracking["cleanup_errors"]
        write_new(folder / "quiescence.json", tracking)
        result["quiescence"] = reference(folder / "quiescence.json")
        write_new(folder / "result.json", result)
    return result


def run():
    authorization = policy.require_tls_diagnostic_allowed("v059.run")
    if os.geteuid() == 0 or os.environ.get("PROWORKSIM_SCORER_HOST_LAUNCHER") != "v058-unprivileged-fixed-python-launcher-r1":
        raise RuntimeError("Use the reviewed ordinary-user fixed-Python launcher")
    if Path(authorization["run_root"]).resolve() != RUN_ROOT.resolve():
        raise ValueError("The single approved diagnostic root differs")
    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    write_new(RUN_ROOT / "authorization-used.json", authorization)
    resolution = freeze_resolution()
    write_new(RUN_ROOT / "resolution.json", resolution)
    requests = [policy.validate_task_image(authorization, t, authorization["image_ids"][t]) for t in sorted(policy.TASKS)]
    sockets = {str(Path(r["docker_socket"]).resolve()) for r in requests}
    if len(sockets) != 1:
        raise ValueError("Diagnostic tasks must use the same existing project Docker endpoint")
    docker_socket = sockets.pop()
    install_socket_guard(docker_socket, resolution["ipv4"])
    import docker
    client = docker.DockerClient(base_url="unix://" + docker_socket, timeout=15)
    results = []
    try:
        for task in sorted(policy.TASKS):
            result = run_task(client, authorization, task, resolution, RUN_ROOT / task)
            results.append(result)
            quiet = json.loads(checked(result["quiescence"]).read_bytes())
            if not quiet["quiescent"] or result.get("shared_transport_unavailable"):
                break
    finally:
        client.close()
    summary = {"version": VERSION, "tasks_planned": sorted(policy.TASKS), "tasks_executed": len(results),
               "results": results, "resolution": reference(RUN_ROOT / "resolution.json"),
               "model_calls": 0, "official_scoring_calls": 0, "scores_changed": False,
               "original_ca_changed": False if results and all(
                   r.get("final_tree_clean") is True and len(r.get("probes", [])) == 2
                   and all(p.get("probe", {}).get("ca_unchanged") is True for p in r["probes"])
                   for r in results) else None,
               "host_configuration_changed": False}
    write_new(RUN_ROOT / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Only explicit --execute is supported; pending authorization remains blocked")
    summary = run()
    print(json.dumps({k: summary[k] for k in ("version", "tasks_executed", "scores_changed")}))


if __name__ == "__main__":
    main()
