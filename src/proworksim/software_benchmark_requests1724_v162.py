"""An isolated, direct httpbin scoring provider for Requests1724 only.

Construction/preparation are local and inert. The caller supplies a separately
frozen grading policy, endpoint probe and fresh resource identities. Nothing
here authorizes a container or modifies the host. Test code, its Python2
interpreter and its TLS validation remain unchanged. Only an existing Python3
inside the immutable image runs the standard-library Docker-exec relay.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_environment_v141 as frozen
from . import software_benchmark_grading_repairs_v141 as repair
from . import software_benchmark_grader_probe_v097 as boundary
from . import software_benchmark_requests_offline_v066 as original
from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_requests1724_ca_v162 as ca
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = 'v162-requests1724-original-python2-bounded-httpbin-r1'
TASK = 'psf__requests-1724'
TASKS = TLS_TASKS = frozenset({TASK})
OFFLINE_TASKS = frozenset()
PORTS = (80, 443)
RELAY_PYTHON = '/opt/miniconda3/bin/python'
ORIGINAL_CA = '/testbed/requests/cacert.pem'
PROFILE = {'standalone_httpbin': True, 'admission_enabled': True, 'blockers': [],
           'actual_httpbin_service': 'frozen_public_httpbin_over_exec_TCP',
           'test_interpreter_changed': False, 'offline_pip_install': False,
           'timeout_interface_needed': False}
CAPABILITIES = ['NET_BIND_SERVICE']


def _load(ref):
    return json.loads(checked(ref).read_bytes())


def fixture_environment(values):
    """Remove proxy routing and trust overrides, preserving original test inputs."""
    result = dict(x.split('=', 1) for x in values) if isinstance(values, list) else dict(values or {})
    for key in ('HTTPBIN_URL', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'OPENSSL_CONF',
                'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'PYTHONHTTPSVERIFY'):
        result.pop(key, None)
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'):
        result[key] = result[key.lower()] = ''
    return ca.fixture_environment(result)


def validate_container_config(attrs, request, limits, profile):
    if request['mapping']['instance_id'] != TASK or profile != PROFILE:
        raise ValueError('The1724 provider cannot enter another task/profile')
    host = attrs['HostConfig']
    if (attrs.get('Image') != request['image_id'] or host.get('NetworkMode') != 'none'
            or host.get('Privileged') or host.get('CapAdd') != CAPABILITIES
            or host.get('CapDrop') != ['ALL'] or host.get('SecurityOpt') != ['no-new-privileges:true']
            or host.get('CpusetCpus') != request['cpuset_cpus']
            or host.get('Memory') != limits['memory_bytes']
            or host.get('MemorySwap') != limits['memory_bytes']
            or host.get('NanoCpus') != limits['nano_cpus']
            or host.get('PidsLimit') != limits['pids_limit']):
        raise ValueError('Actual1724 grader limits or private network/capabilities changed')
    if any(host.get(k) not in (None, '', 'private') for k in ('PidMode', 'IpcMode', 'UTSMode', 'CgroupnsMode')):
        raise ValueError('No host/foreign namespace sharing')
    if (host.get('UsernsMode') not in (None, '') or attrs.get('Mounts')
            or any(host.get(k) for k in ('Binds', 'Mounts', 'VolumesFrom', 'Devices', 'DeviceRequests',
                                         'Links', 'PortBindings', 'PublishAllPorts', 'Sysctls'))
            or host.get('ExtraHosts') != ['httpbin.org:127.0.0.1']):
        raise ValueError('Only the container-local httpbin hosts entry is allowed')
    actual = dict(x.split('=', 1) for x in attrs.get('Config', {}).get('Env', []) if '=' in x)
    if any(actual.get(k) for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                                  'http_proxy', 'https_proxy', 'all_proxy')):
        raise ValueError('The task must not inherit proxy configuration')
    if any(actual.get(k) for k in ('HTTPBIN_URL', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
                                  'OPENSSL_CONF', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                                  'SSLKEYLOGFILE', 'PYTHONHTTPSVERIFY')):
        raise ValueError('Preserve the original task endpoint and strict CA/TLS conditions')


RELAY_INTERPRETER_PROBE = r'''import sys, os, json, socket
if sys.version_info[:2] < (3, 7) or not hasattr(os, 'set_blocking'):
    raise RuntimeError('Existing base Python cannot run the bounded standard-library relay')
addresses=sorted(set(row[4][0] for row in socket.getaddrinfo('httpbin.org',80,socket.AF_INET,socket.SOCK_STREAM)))
if addresses != ['127.0.0.1']:
    raise RuntimeError('The actual container-only hostname mapping differs')
links=sorted(name for _,name in socket.if_nameindex())
if links != ['lo']:
    raise RuntimeError('The grader must retain only its loopback interface')
with open('/proc/self/net/route') as stream:
    routes=stream.read().splitlines()[1:]
if any(len(row.split()) >= 3 and row.split()[2] != '00000000' for row in routes):
    raise RuntimeError('The grader has an unexpected gateway')
print(json.dumps({'executable':sys.executable,'python_version':list(sys.version_info[:3]),
    'has_set_blocking':True,'httpbin_ipv4':addresses,'interfaces':links,
    'gateway_present':False,'outside_DNS_queries':0,
    'interfaces_source':'socket.if_nameindex','routes_source':'/proc/self/net/route'},sort_keys=True))
'''


def ca_identity(container, test_python):
    # Python2 compatible; does not import candidate Requests or alter trust.
    source = ("import hashlib,json; path="+repr(ORIGINAL_CA)+"; "
              "print(json.dumps({'path':path,'sha256':hashlib.sha256(open(path,'rb').read()).hexdigest()}))")
    return json.loads(original.checked_exec(container, [test_python, '-S', '-c', source],
        timeout_note='1724 original repository CA identity'))


def run_official(run_instance, *args, tracking, **kwargs):
    """Bind finish before the actual official CLI cleanup, then restore it."""
    namespace=getattr(run_instance,'__globals__',None)
    if not isinstance(namespace,dict) or not callable(namespace.get('cleanup_container')):
        raise ValueError('1724 needs the actual diagnostic evaluator cleanup namespace')
    module=sys.modules.get(namespace.get('__name__'))
    if module is not None and vars(module) is namespace:
        raise ValueError('Only the private diagnostic function namespace may be patched')
    return lifecycle.run_official(run_instance,*args,tracking=tracking,**kwargs)


def cleanup_transport(tracking):
    errors = []
    wrapper = tracking.get('environment_container')
    if wrapper is not None:
        try:
            result = wrapper.finish_transport()
            if result.get('thread_finished') is False:
                errors.append('1724 relay host thread still running')
        except Exception as error:
            errors.append(type(error).__name__+': '+str(error))
    errors.extend(tracking.get('transport_cleanup_errors', []))
    return errors


def cold_environment(policy, *, scope_ref, directory, resolution_ref,
                     resolution_source='v162_current_DNS_and_bounded_endpoint_probe'):
    """Create private scorer providers; no network or Docker operations here."""
    checked(scope_ref)
    if not callable(getattr(policy, 'require_v066_allowed', None)):
        raise ValueError('A separately scoped caller dispatch guard is required')
    directory = Path(directory).resolve()
    tcp = repair.transport_adapter(policy)
    limits = tcp.Limits(max_connections=512, max_bytes=64*1024**2,
                        wall_seconds=1800, max_active=16, idle_seconds=60)

    def resolution():
        return frozen.validate_resolution(resolution_ref, scope_ref=scope_ref,
                                          expected_source=resolution_source)

    def environment_manifest():
        resolution()
        return {'version': VERSION, 'adapter': reference(__file__), 'scope': scope_ref,
            'profiles': {TASK: copy.deepcopy(PROFILE)}, 'network_resolution': resolution_ref, 'resolution_source': resolution_source,
            'transport': reference(repair.__file__), 'transport_original': reference(repair.original_tcp.__file__),
            'transport_source_repair_sha256': tcp.source_repair_sha256,
            'boundary_probe': reference(boundary.__file__),
            'network_mode': 'none', 'cap_add': list(CAPABILITIES), 'cap_drop': ['ALL'],
            'no_new_privileges': True, 'extra_hosts': {'httpbin.org': '127.0.0.1'},
            'listen_ports': list(PORTS), 'relay_existing_interpreter': RELAY_PYTHON,
            'relay_interpreter_runtime_probe_required': True, 'task_interpreter_unchanged': True,
            'test_commands_changed': False, 'official_test_patch_changed': False,
            'repository_files_changed': False, 'original_CA_file_unchanged': True,
            'effective_CA_changed': True, 'TLS_validation_disabled': False,
            'scoring_CA_profile':reference(ca.PROFILE_FILE),
            'scoring_CA_compatibility':ca.profile_manifest(),
            'cleanup_binding':reference(lifecycle.__file__),
            'cleanup_order':'finish_transport_before_actual_official_CLI_cleanup',
            'TLS_bytes_opaque_to_host': True, 'host_listeners': False,
            'host_mounts_or_network_configuration_changed': False, 'new_packages_installed': False,
            'new_data_downloads': False, 'model_network_access': False,
            'limits': vars(limits), 'fresh_gold_empty_controls_required': True,
            'runtime_qualified': False}

    def validate_environment(ref):
        value = _load(ref)
        if value != environment_manifest():
            raise ValueError('1724 frozen environment differs from its executing binding')
        return value

    class EnvironmentContainer(original.EnvironmentContainer):
        def __init__(self, delegate, preparation, resource_limits, tracking):
            super().__init__(delegate, preparation, resource_limits)
            self.tracking = tracking
            self.ready, self.stop_event = threading.Event(), threading.Event()
            self.relay_thread = self.relay_exec = self.relay_socket = None
            self.relay_result = None
            self.ca_before = None
            self.finished = False
            self.start_entered = False

        def start(self, *args, **kwargs):
            task = self.preparation['mapping']['instance_id']
            if self.start_entered:
                raise ValueError('An owned1724 transport may start only once')
            self.start_entered=True
            if task != TASK or self.delegate.id not in self.tracking.get('owned_container_ids', []):
                raise ValueError('1724 network fixture requires its exact newly owned scorer')
            policy.require_v066_allowed('v066.grader.start', instance_id=TASK)
            manifest = validate_environment(self.preparation['environment_revision'])
            self.delegate.reload()
            validate_container_config(self.delegate.attrs, self.preparation, self.limits, PROFILE)
            intended = self.tracking['create_identity']
            actual_labels = self.delegate.attrs.get('Config', {}).get('Labels') or {}
            if any(actual_labels.get(k) != v for k,v in intended['labels'].items()):
                raise ValueError('1724 container ownership labels differ')
            result = base.PreparationObservedContainer.start(self, *args, **kwargs)
            validate_container_config(self.delegate.attrs, self.preparation, self.limits, PROFILE)
            path = Path(self.preparation['path'])
            observed = json.loads(path.read_bytes())
            if (observed['head_git_tree'] != self.preparation['mapping']['official_tree']
                    or observed['working_tree_clean'] is not True):
                raise ValueError('1724 starts from the exact clean official baseline')
            test_python = self.preparation['mapping']['public_python']
            inside, probe_ref = boundary.observe(self.delegate, test_python,
                                                 path.with_name('private-boundary-probe-v162.json'))
            host = {key: os.stat('/proc/self/ns/'+key).st_ino for key in original.NAMESPACES}
            isolation = original.namespace_evidence(inside['namespaces'], host)
            expected_cpus = []
            for part in self.preparation['cpuset_cpus'].split(','):
                edges = part.split('-')
                expected_cpus.extend(range(int(edges[0]), int(edges[-1])+1))
            if inside['cpus'] != sorted(set(expected_cpus)):
                raise ValueError('1724 container CPU affinity differs')
            relay_python = json.loads(original.checked_exec(self.delegate,
                [RELAY_PYTHON, '-S', '-c', RELAY_INTERPRETER_PROBE],
                timeout_note='1724 existing Python3 relay and offline-network probe'))
            self.ca_before = ca_identity(self.delegate, test_python)
            ca_probe=ca.stage_owned(self.delegate,public_python=test_python,owned_ids=self.tracking['owned_container_ids'])
            observed.update(environment_revision=self.preparation['environment_revision'],
                network_resolution=resolution_ref, namespace_evidence=isolation, boundary_probe=probe_ref,
                actual_relay_interpreter=relay_python, actual_test_interpreter=test_python,
                original_ca=self.ca_before, original_CA_file_unchanged=True,
                effective_CA_changed=True, TLS_validation_disabled=False,
                scoring_CA_profile=reference(ca.PROFILE_FILE),scoring_CA_loader_probe=ca_probe,
                actual_capabilities=list(CAPABILITIES), actual_dropped_capabilities=['ALL'],
                actual_security_options=['no-new-privileges:true'], effective_network_mode='none',
                host_network_namespace_shared=False, task_files_changed=False,
                candidate_or_official_tests_changed=False, local_httpbin=False,
                httpbin_service_scope='public_httpbin_over_bounded_exec_transport',
                source_image_id=self.preparation['image_id'], resource_key=self.preparation['resource_key'])
            path.write_bytes(base.canonical(observed))
            endpoint = resolution()
            client = self.tracking['client']
            self.relay_exec = client.api.exec_create(self.delegate.id,
                [RELAY_PYTHON, '-S', '-u', '-B', '-c', tcp.build_container_source(limits, listen_ports=PORTS)],
                stdin=True, stdout=True, stderr=True, tty=False)['Id']
            self.relay_socket = client.api.exec_start(self.relay_exec, socket=True, tty=False)
            def relay():
                try:
                    self.relay_result = tcp.relay_many(self.relay_socket, endpoint['selected_ip'],
                        instance_id=TASK, resolved_ips=endpoint['ipv4'], limits=limits,
                        listen_ports=PORTS, stop_event=self.stop_event, on_ready=self.ready.set)
                except Exception as error:
                    self.relay_result = {'ok':False, 'status':'failed',
                        'error':{'type':type(error).__name__,'message':str(error)}}
                finally:
                    self.ready.set()
            self.relay_thread = threading.Thread(target=relay, name='pws-v162-1724-bounded-relay', daemon=True)
            self.relay_thread.start()
            if not self.ready.wait(20) or self.relay_result is not None:
                raise RuntimeError('1724 bounded real-httpbin relay did not become ready')
            return result

        def finish_transport(self):
            if self.finished:
                return self.relay_result or {'ok':False,'status':'finishing'}
            self.finished = True
            self.stop_event.set()
            if self.relay_thread is not None:
                self.relay_thread.join(timeout=20)
                if self.relay_thread.is_alive():
                    if self.relay_socket is not None:
                        self.relay_socket.close()
                    self.relay_thread.join(timeout=5)
            value = dict(self.relay_result or {'ok':False,'status':'not_started'})
            value['thread_finished'] = self.relay_thread is None or not self.relay_thread.is_alive()
            ca_after = None
            if self.ca_before is not None:
                try:
                    ca_after = ca_identity(self.delegate,self.preparation['mapping']['public_python'])
                except Exception as error:
                    self.tracking.setdefault('transport_cleanup_errors',[]).append('CA readback: '+str(error))
            value.update(original_ca_before=self.ca_before,original_ca_after=ca_after,
                original_ca_unchanged=self.ca_before is not None and self.ca_before==ca_after,
                TLS_validation_disabled=False,host_listeners=False)
            if not value['thread_finished'] or not value['original_ca_unchanged']:
                value['ok']=False
            if self.relay_exec is not None:
                try:
                    end=time.monotonic()+2
                    state=self.tracking['client'].api.exec_inspect(self.relay_exec)
                    while state.get('Running') and time.monotonic()<end:
                        time.sleep(.05);state=self.tracking['client'].api.exec_inspect(self.relay_exec)
                    value.update(exec_finished=state.get('Running') is False,exec_exit_code=state.get('ExitCode'))
                    if not value['exec_finished'] or value['exec_exit_code']!=0:
                        value['ok']=False
                except Exception as error:
                    value.update(ok=False,exec_inspect_error=str(error))
            self.relay_result=value
            path=Path(self.preparation['path']).with_name('transport-v162.json')
            self.tracking['transport_result']=write_new(path,value)
            return value

        def _cleanup(self, action, *args, **kwargs):
            lifecycle=self.tracking.setdefault('tls_lifecycle',{'version':VERSION,
                'binding':'owned_EnvironmentContainer.stop_remove_and_finally','stop_remove_calls':[],
                'finish_attempts_before_cleanup':0,'shared_harness_globals_modified':False,'binding_restored':True})
            lifecycle['finish_attempts_before_cleanup']+=not self.finished
            try:
                self.finish_transport()
            except Exception as error:
                self.tracking.setdefault('transport_cleanup_errors',[]).append(str(error))
            lifecycle.setdefault('stop_remove_calls',[]).append({'operation':action,'container_id':self.delegate.id,
                'transport_finish_attempted_first':True,'relay_thread_finished':self.relay_thread is None or not self.relay_thread.is_alive()})
            return getattr(self.delegate,action)(*args,**kwargs)

        def stop(self,*args,**kwargs):
            return self._cleanup('stop',*args,**kwargs)

        def remove(self,*args,**kwargs):
            return self._cleanup('remove',*args,**kwargs)

    def install_socket_guard(docker_socket, endpoint):
        if endpoint != resolution():
            raise ValueError('The scoring socket guard must bind its exact fresh endpoint')
        selected=endpoint['selected_ip'];owned_socket=Path(docker_socket).resolve()
        def audit(event,args):
            if event in {'socket.bind','socket.getaddrinfo'}:
                raise RuntimeError('No host listeners or additional DNS in the scoring process')
            if event=='socket.connect':
                sock,address=args
                if sock.family==socket.AF_UNIX and isinstance(address,str) and Path(address).resolve()==owned_socket:
                    return
                if (sock.family==socket.AF_INET and isinstance(address,tuple) and len(address)==2
                        and address[0]==selected and address[1] in PORTS):
                    return
                raise RuntimeError('Scoring connection leaves the frozen Docker/httpbin route')
        sys.addaudithook(audit)

    def finish_transport(tracking):
        wrapper=tracking.get('environment_container')
        return wrapper.finish_transport() if wrapper is not None else {'ok':False,'status':'not_started'}

    provider = SimpleNamespace(PROFILES={TASK:copy.deepcopy(PROFILE)},
        EnvironmentContainer=EnvironmentContainer, environment_manifest=environment_manifest,
        validate_environment=validate_environment, fixture_environment=fixture_environment,
        run_official=run_official, cleanup_transport=cleanup_transport, finish_transport=finish_transport,
        install_socket_guard=install_socket_guard, transport=tcp,
        __file__=__file__, VERSION=VERSION)

    def prepare():
        ref=frozen._retain(directory/'1724-environment.json',environment_manifest())
        return frozen._retain(directory/'bindings.json',{'version':VERSION,'scope':scope_ref,
            'environment_revision':ref,'network_resolution':resolution_ref,'instance_id':TASK})

    def request_fields(task):
        if task!=TASK:
            return {'environment_revision':None,'network_resolution':None}
        bound=_load(reference(directory/'bindings.json'))
        if bound['scope']!=scope_ref or bound['network_resolution']!=resolution_ref:
            raise ValueError('1724 environment bindings belong to another scope')
        validate_environment(bound['environment_revision'])
        return {key:bound[key] for key in ('environment_revision','network_resolution')}

    def validate_request(request,task):
        expected=request_fields(task)
        if any(request.get(k)!=v for k,v in expected.items()):
            raise ValueError('Task-specific1724 environment or endpoint identity changed')
        return provider if task==TASK else None

    return SimpleNamespace(__file__=__file__,VERSION=VERSION,TASKS=TASKS,TLS_TASKS=TLS_TASKS,OFFLINE_TASKS=OFFLINE_TASKS,
        tls=provider,offline=SimpleNamespace(__file__=__file__,validate_container_config=validate_container_config),
        prepare=prepare,request_fields=request_fields,validate_request=validate_request,
        validate_control_environment=validate_control_environment,
        validate_transport_evidence=validate_transport_evidence,
        provider=lambda task:provider if task==TASK else None,
        capabilities=lambda task:list(CAPABILITIES) if task==TASK else [])


def validate_transport_evidence(receipt, quiet, observed, identity, folder, *,
                                transport_directory=None, require_usage=True):
    """Validate actual private transport/cleanup; TCP success is not a test score."""
    if receipt.get('instance_id')!=TASK or identity.get('instance_id')!=TASK:
        raise ValueError('Only1724 may use the new transport evidence')
    manifest=_load(identity['environment_revision'])
    if (manifest.get('version')!=VERSION or manifest.get('adapter')!=reference(__file__)
            or observed.get('environment_revision')!=identity['environment_revision']
            or observed.get('network_resolution')!=identity['network_resolution']
            or manifest.get('network_resolution')!=identity['network_resolution']):
        raise ValueError('1724 evidence lost its exact frozen environment identity')
    resolution=frozen.validate_resolution(identity['network_resolution'],scope_ref=manifest['scope'],
                                          expected_source=manifest['resolution_source'])
    directory=Path(folder)/'official-output' if transport_directory is None else Path(transport_directory)
    ref=receipt.get('transport_result')
    if (not isinstance(ref,dict) or Path(ref.get('path','')).resolve()!=(directory/'transport-v162.json').resolve()
            or quiet.get('transport_result')!=ref or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors')!=[] or quiet.get('deadline_reached') is not False):
        raise ValueError('1724 transport or cleanup evidence belongs to another scoring attempt')
    result=_load(ref)
    if (result.get('ok') is not True or result.get('status')!='completed' or result.get('ready') is not True
            or result.get('network_errors')!=[] or result.get('cleanup_errors')!=[] or result.get('error') is not None
            or result.get('thread_finished') is not True or result.get('exec_finished') is not True
            or result.get('exec_exit_code')!=0 or result.get('original_ca_unchanged') is not True
            or result.get('original_ca_before')!=observed.get('original_ca')
            or result.get('original_ca_after')!=observed.get('original_ca')
            or observed.get('original_ca',{}).get('path')!=ORIGINAL_CA
            or observed.get('effective_CA_changed') is not True
            or observed.get('TLS_validation_disabled') is not False
            or observed.get('task_files_changed') is not False
            or observed.get('effective_network_mode')!='none'
            or observed.get('actual_capabilities')!=CAPABILITIES):
        raise ValueError('1724 original trust, opaque transport or private boundary did not qualify')
    if (result.get('target_ip')!=resolution['selected_ip'] or result.get('target_hostname')!='httpbin.org'
            or result.get('listen_ports')!=list(PORTS)):
        raise ValueError('Actual transport reached another destination')
    minimum=1 if require_usage else 0
    for key,limit in [('connection_attempts',512),('max_active_observed',16),('application_payload_bytes',64*1024**2)]:
        if type(result.get(key)) is not int or not minimum<=result[key]<=limit:
            raise ValueError('1724 transport exceeds its bounded use')
    for row in result.get('connections',[]):
        if row.get('outcome')=='tcp_eof' and not all(row.get(k) is True for k in
                ('client_eof_observed','remote_eof_observed','tcp_completion_evidence')):
            raise ValueError('A clean EOF needs actual two-sided closure evidence')
    observed_lifecycle=quiet.get('TLS_lifecycle') or receipt.get('TLS_lifecycle')
    if (not isinstance(observed_lifecycle,dict) or observed_lifecycle.get('version')!=lifecycle.VERSION
            or observed_lifecycle.get('binding')!='passed_function.__globals__.cleanup_container'
            or observed_lifecycle.get('cleanup_calls',0)<1
            or observed_lifecycle.get('finish_attempts_before_cleanup')!=1
            or observed_lifecycle.get('binding_restored') is not True):
        raise ValueError('The real private evaluator must finish relay before official CLI cleanup')
    profile=ca.profile_manifest();ca_probe=observed.get('scoring_CA_loader_probe') or {}
    if (observed.get('scoring_CA_profile')!=reference(ca.PROFILE_FILE)
            or ca_probe.get('verify_mode')!=2 or ca_probe.get('verification_settings_unchanged') is not True
            or ca_probe.get('combined_CA_sha256')!=profile['combined_CA']['sha256']
            or ca_probe.get('original_CA_sha256')!=ca.EXPECTED_ORIGINAL_SHA256
            or ca_probe.get('shim_version')!=ca.VERSION or ca_probe.get('network_calls')!=0):
        raise ValueError('Actual scoring CA augmentation lacks unchanged verification evidence')

    return result


def validate_control_environment(observed, identity, *, mapping=None):
    """1724's real boundary replaces the unrelated legacy timeout-fixture gate.

    The original evaluator still independently checks the clean pinned tree,
    gold/empty outcomes, namespaces and resource identities. Do not manufacture
    timeout_route evidence: this task receives no dummy interface or IPRoute.
    """
    if identity.get('instance_id')!=TASK:
        raise ValueError('The1724 control boundary cannot qualify another task')
    mapping=_load(identity['baseline_mapping']) if mapping is None else mapping
    relay=observed.get('actual_relay_interpreter') or {}
    version=relay.get('python_version')
    if (observed.get('environment_revision')!=identity.get('environment_revision')
            or observed.get('network_resolution')!=identity.get('network_resolution')
            or observed.get('actual_test_interpreter')!=mapping.get('public_python')
            or observed.get('task_files_changed') is not False
            or observed.get('candidate_or_official_tests_changed') is not False
            or observed.get('actual_capabilities')!=CAPABILITIES
            or observed.get('actual_dropped_capabilities')!=['ALL']
            or observed.get('actual_security_options')!=['no-new-privileges:true']
            or observed.get('effective_network_mode')!='none'
            or observed.get('host_network_namespace_shared') is not False
            or observed.get('effective_CA_changed') is not True
            or observed.get('TLS_validation_disabled') is not False
            or observed.get('original_CA_file_unchanged') is not True
            or not isinstance(version,list) or len(version)!=3
            or any(type(n) is not int or n<0 for n in version) or tuple(version[:2])<(3,7)
            or relay.get('executable')!=RELAY_PYTHON or relay.get('has_set_blocking') is not True
            or relay.get('httpbin_ipv4')!=['127.0.0.1'] or relay.get('interfaces')!=['lo']
            or relay.get('gateway_present') is not False
            or relay.get('interfaces_source')!='socket.if_nameindex'
            or relay.get('routes_source')!='/proc/self/net/route'):
        raise ValueError('Actual1724 Python/endpoint/permissions/TLS boundary differs')
    probe=_load(observed['boundary_probe'])
    if probe.get('status')!='observed' or probe.get('observation',{}).get('affinity_source') not in {'sched_getaffinity','proc_self_status'}:
        raise ValueError('1724 lacks an actual kernel-affinity/namespace observation')
    return {'version':VERSION,'passed':True,'instance_id':TASK,
        'legacy_timeout_route_not_required_or_fabricated':True,
        'actual_test_interpreter':observed['actual_test_interpreter'],
        'actual_relay_interpreter':copy.deepcopy(relay),'test_or_candidate_changed':False}
