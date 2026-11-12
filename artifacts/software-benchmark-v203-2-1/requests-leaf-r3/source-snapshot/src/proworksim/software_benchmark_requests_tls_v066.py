"""Bounded real-httpbin grading in private containers; no host listeners/configuration.

The fixed Requests clients keep their repository CA and TLS validation. Existing
pinned fixture dependencies and the container-local TCP timeout route remain;
HTTP and TLS bytes instead reach the frozen public httpbin IPv4 over Docker exec.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import socket
import sys
import tarfile
import threading
import time

from . import software_benchmark_requests_offline_v066 as prior
from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_tcp_transport_v066 as transport
from . import software_benchmark_dispatch_v066 as policy
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = prior.ROOT
ASSETS = prior.ASSETS
VERSION = 'v064-real-httpbin-original-ca-grading-r1'
PYTHON, FIXTURES = prior.PYTHON, prior.FIXTURES
PROFILES = {task: {'httpbin': '0.7.0', 'pytest_httpbin': '0.0.7', 'standalone_httpbin': True,
                  'admission_enabled': True, 'blockers': []}
            for task in ('psf__requests-1766', 'psf__requests-1921')}
COMMON = prior.COMMON
NAMESPACES = prior.NAMESPACES
EFFECTIVE_PIDS = 512
LISTEN_PORTS = (80, 443)


def environment_manifest():
    inventory = json.loads((ASSETS / 'packages-manifest.json').read_bytes())
    wheels = [{k: item[k] for k in ('path', 'sha256', 'bytes')} for item in inventory['files']]
    for item in wheels:
        checked(item)
    return {'version': VERSION, 'adapter': reference(__file__), 'profiles': PROFILES,
            'transport': reference(transport.__file__), 'policy': reference(policy.__file__),
            'legacy_fixture_adapter': reference(prior.__file__),
            'package_inventory': reference(ASSETS / 'packages-manifest.json'), 'wheels': wheels,
            'common_requirements': COMMON, 'network_mode': 'none',
            'effective_network_policy': 'Docker exec raw TCP to one frozen public httpbin.org IPv4:80,443',
            'host_listener': False, 'host_network_configuration_changed': False,
            'httpbin_service_scope': 'public_httpbin_over_bounded_exec_transport',
            'original_ca_changed': False, 'tls_verification_changed': False,
            'task_files_changed': False, 'official_test_and_scoring_logic_changed': False,
            'cleanup_adapter': 'finish bounded transport before unchanged official container cleanup',
            'cap_add': ['NET_ADMIN', 'NET_BIND_SERVICE'], 'cap_drop': ['ALL'],
            'pids_limit': EFFECTIVE_PIDS, 'runtime_qualified': False}


def freeze_environment(path):
    return write_new(path, environment_manifest())


def validate_environment(ref):
    value = json.loads(checked(ref).read_bytes())
    if value != environment_manifest():
        raise ValueError('Frozen grading environment changed')
    return value


def archive_assets(manifest):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as tar:
        for item in manifest['wheels']:
            path = checked(item)
            body = path.read_bytes()
            entry = tarfile.TarInfo('wheels/' + path.name)
            entry.size, entry.mode, entry.uid, entry.gid = len(body), 0o600, 0, 0
            tar.addfile(entry, io.BytesIO(body))
    return output.getvalue()


def fixture_environment(values):
    if isinstance(values, list):
        values = dict(v.split('=', 1) for v in values)
    value = dict(values or {})
    for name in ('HTTPBIN_URL', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'OPENSSL_CONF',
                 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'PYTHONHTTPSVERIFY'):
        value.pop(name, None)
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'):
        value[name] = value[name.lower()] = ''
    return value


def freeze_resolution(instance_id):
    policy.require_v066_allowed('v066.resolve', instance_id=instance_id)
    records = socket.getaddrinfo('httpbin.org', 443, socket.AF_INET, socket.SOCK_STREAM)
    addresses = policy.validate_ipv4_targets([record[4][0] for record in records])
    return {'hostname': 'httpbin.org', 'ports': list(LISTEN_PORTS), 'ipv4': list(addresses),
            'selected_ip': addresses[0], 'automatic_retry': False}


def install_socket_guard(docker_socket, resolution):
    addresses = policy.validate_ipv4_targets(resolution['ipv4'])
    if resolution.get('selected_ip') != addresses[0] or resolution.get('ports') != list(LISTEN_PORTS):
        raise ValueError('Frozen direct network resolution differs')
    selected = (addresses[0],)
    def audit(event, args):
        if event in {'socket.bind', 'socket.getaddrinfo'}:
            raise RuntimeError('Host listeners and further DNS are forbidden')
        if event == 'socket.connect':
            sock, address = args
            if sock.family == socket.AF_UNIX and isinstance(address, str) and str(Path(address).resolve()) == str(docker_socket):
                return
            if sock.family == socket.AF_INET:
                policy.validate_connect_target(address, selected)
                return
            raise RuntimeError('Socket outside the bounded Docker/httpbin scope')
    sys.addaudithook(audit)


def ca_identity(container):
    source = "import hashlib,json,pathlib; p=pathlib.Path('/testbed/requests/cacert.pem'); print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
    return json.loads(prior.checked_exec(container, [PYTHON, '-B', '-c', source], timeout_note='Original repository CA identity'))


class EnvironmentContainer(prior.EnvironmentContainer):
    def __init__(self, delegate, preparation, limits, tracking):
        super().__init__(delegate, preparation, limits)
        self.tracking = tracking
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.relay_thread = None
        self.relay_result = None
        self.relay_socket = None
        self.relay_exec = None
        self.ca_before = None
        self.finished = False

    def start(self, *args, **kwargs):
        request = self.preparation
        task = request['mapping']['instance_id']
        policy.require_v066_allowed('v066.grader.start', instance_id=task)
        manifest = validate_environment(request['environment_revision'])
        profile = PROFILES[task]
        self.delegate.reload()
        prior.validate_container_config(self.delegate.attrs, request, self.limits, profile)
        actual_env = dict(item.split('=', 1) for item in self.delegate.attrs.get('Config', {}).get('Env', []) if '=' in item)
        overrides = ('HTTPBIN_URL', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'OPENSSL_CONF',
                     'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'PYTHONHTTPSVERIFY')
        if any(actual_env.get(k) for k in overrides):
            raise ValueError('Actual grader environment overrides the original CA, TLS or httpbin settings')
        if any(actual_env.get(k) for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')):
            raise ValueError('Actual grader retained a proxy override')
        actual_labels = self.delegate.attrs.get('Config', {}).get('Labels') or {}
        intended = self.tracking['create_identity']
        if any(actual_labels.get(k) != v for k, v in intended['labels'].items()):
            raise ValueError('Created grader ownership labels differ')
        result = base.PreparationObservedContainer.start(self, *args, **kwargs)
        prior.validate_container_config(self.delegate.attrs, request, self.limits, profile)
        evidence_path = Path(request['path'])
        evidence = json.loads(evidence_path.read_bytes())
        if evidence['head_git_tree'] != request['mapping']['official_tree'] or evidence['working_tree_clean'] is not True:
            raise ValueError('Fixed original baseline is not clean')
        host = {k: os.stat('/proc/self/ns/' + k).st_ino for k in NAMESPACES}
        inside = json.loads(prior.checked_exec(self.delegate, [PYTHON, '-B', '-c',
            "import os,json; print(json.dumps({k:os.stat('/proc/self/ns/'+k).st_ino for k in ('net','mnt','pid','ipc')}))"], timeout_note='Private grading namespaces'))
        isolation = prior.namespace_evidence(inside, host)
        self.ca_before = ca_identity(self.delegate)
        prior.checked_exec(self.delegate, ['mkdir', '-p', FIXTURES], timeout_note='Private fixture directory')
        if self.delegate.put_archive(FIXTURES, archive_assets(manifest)) is not True:
            raise RuntimeError('Pinned dependencies were not transferred')
        install = prior.checked_exec(self.delegate, [PYTHON, '-m', 'pip', 'install', '--no-index',
            '--disable-pip-version-check', '--find-links=' + FIXTURES + '/wheels',
            *COMMON, 'httpbin==0.7.0', 'pytest-httpbin==0.0.7'], timeout_note='Offline dependency install')
        network = json.loads(prior.checked_exec(self.delegate, [PYTHON, '-B', '-c', prior.NETWORK], timeout_note='Private TCP timeout fixture'))
        clean = prior.checked_exec(self.delegate, ['git', '-c', 'safe.directory=/testbed', '-C', '/testbed', 'status', '--porcelain'], timeout_note='Original test tree retained')
        if clean or ca_identity(self.delegate) != self.ca_before:
            raise ValueError('Environment preparation changed repository files or CA')
        evidence.update(environment_revision=request['environment_revision'], namespace_evidence=isolation,
            dependency_install_log=install, timeout_route=network, effective_network_mode='none',
            host_network_namespace_shared=False, task_files_changed=False, local_httpbin=False,
            standalone_httpbin=False, httpbin_service_scope=manifest['httpbin_service_scope'],
            original_ca=self.ca_before, original_ca_changed=False, tls_verification_changed=False,
            actual_capabilities=self.delegate.attrs['HostConfig'].get('CapAdd'),
            actual_dropped_capabilities=self.delegate.attrs['HostConfig'].get('CapDrop'),
            actual_security_options=self.delegate.attrs['HostConfig'].get('SecurityOpt'),
            upstream_capabilities_removed=request.get('upstream_capabilities_removed', []),
            resolution=request['network_resolution'])
        evidence_path.write_bytes(base.canonical(evidence))
        resolution = json.loads(checked(request['network_resolution']).read_bytes())
        limits = transport.Limits(max_connections=512, max_bytes=64 * 1024 * 1024,
                                  wall_seconds=1800, max_active=16, idle_seconds=60)
        client = self.tracking['client']
        self.relay_exec = client.api.exec_create(self.delegate.id,
            [PYTHON, '-u', '-B', '-c', transport.build_container_source(limits, listen_ports=LISTEN_PORTS)],
            stdin=True, stdout=True, stderr=True, tty=False)['Id']
        self.relay_socket = client.api.exec_start(self.relay_exec, socket=True, tty=False)
        def relay():
            try:
                self.relay_result = transport.relay_many(self.relay_socket, resolution['selected_ip'],
                    instance_id=task, resolved_ips=resolution['ipv4'], limits=limits,
                    listen_ports=LISTEN_PORTS, stop_event=self.stop_event, on_ready=self.ready.set)
            except Exception as error:
                self.relay_result = {'ok': False, 'status': 'failed', 'error': {'type': type(error).__name__, 'message': str(error)}}
            finally:
                self.ready.set()
        self.relay_thread = threading.Thread(target=relay, name='v064-bounded-transport', daemon=True)
        self.relay_thread.start()
        if not self.ready.wait(20) or self.relay_result is not None:
            raise RuntimeError('Bounded real-httpbin relay did not become ready')
        return result

    def finish_transport(self):
        if self.finished:
            return self.relay_result
        self.finished = True
        ca_after = None
        try:
            if self.ca_before is not None:
                ca_after = ca_identity(self.delegate)
        except Exception as error:
            self.tracking.setdefault('transport_cleanup_errors', []).append('CA final identity: ' + str(error))
        self.stop_event.set()
        if self.relay_thread is not None:
            self.relay_thread.join(timeout=20)
            if self.relay_thread.is_alive():
                if self.relay_socket is not None:
                    self.relay_socket.close()
                self.relay_thread.join(timeout=5)
        result = dict(self.relay_result or {'ok': False, 'status': 'not_completed'})
        result['thread_finished'] = self.relay_thread is None or not self.relay_thread.is_alive()
        result['original_ca_before'] = self.ca_before
        result['original_ca_after'] = ca_after
        result['original_ca_unchanged'] = self.ca_before is not None and self.ca_before == ca_after
        if not result['thread_finished'] or not result['original_ca_unchanged']:
            result['ok'] = False
        if self.relay_exec is not None:
            try:
                state = self.tracking['client'].api.exec_inspect(self.relay_exec)
                end = time.monotonic() + 2
                while state.get('Running') and time.monotonic() < end:
                    time.sleep(.05)
                    state = self.tracking['client'].api.exec_inspect(self.relay_exec)
                result['exec_finished'] = state.get('Running') is False
                result['exec_exit_code'] = state.get('ExitCode')
                if not result['exec_finished'] or result['exec_exit_code'] != 0:
                    result['ok'] = False
            except Exception as error:
                result['ok'] = False
                result['exec_inspect_error'] = str(error)
        self.relay_result = result
        path = Path(self.preparation['path']).with_name('transport.json')
        write_new(path, result)
        self.tracking['transport_result'] = reference(path)
        return result

    def stop(self, *args, **kwargs):
        self.finish_transport()
        return self.delegate.stop(*args, **kwargs)

    def remove(self, *args, **kwargs):
        self.finish_transport()
        return self.delegate.remove(*args, **kwargs)


def finish_transport(tracking):
    wrapper = tracking.get('environment_container')
    if wrapper is not None:
        return wrapper.finish_transport()
    return {'ok': False, 'status': 'not_started'}


def cleanup_transport(tracking):
    errors = []
    try:
        result = finish_transport(tracking)
        if result.get('thread_finished') is False:
            errors.append('Bounded transport host thread still running')
    except Exception as error:
        errors.append(str(error))
    errors.extend(tracking.get('transport_cleanup_errors', []))
    timer = tracking.get('deadline_timer')
    if timer is not None:
        timer.cancel()
        timer.join(timeout=10)
        if timer.is_alive():
            errors.append('Lifecycle deadline thread remains alive')
    return errors


def run_official(run_instance, *args, tracking, **kwargs):
    """Scope shutdown ordering to this worker; retain official tests/score/cleanup."""
    import swebench.harness.run_evaluation as official
    original = official.cleanup_container
    def cleanup(client, container, logger):
        wrapper = tracking.get('environment_container')
        if container is not None:
            if wrapper is None or container.id not in tracking['owned_container_ids']:
                raise ValueError('Official cleanup received an unowned grading container')
            try:
                wrapper.finish_transport()
            except Exception as error:
                tracking.setdefault('transport_cleanup_errors', []).append(str(error))
        return original(client, container, logger)
    official.cleanup_container = cleanup
    try:
        return run_instance(*args, **kwargs)
    finally:
        official.cleanup_container = original
