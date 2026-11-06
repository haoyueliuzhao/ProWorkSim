"""No sockets, containers, API calls or host installs: only bounded CPU fixtures."""
from collections import deque
import json
import threading
from types import SimpleNamespace
import zipfile

import pytest

from proworksim import software_benchmark_environment_v141 as environment
from proworksim import software_benchmark_grading_repairs_v141 as repairs
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def cold_fixture(folder):
    folder.mkdir()
    scope = folder/'scope.py'
    scope.write_text('# Synthetic CPU scope; authorizes no live operations.\n')
    scope_ref = reference(scope)
    probe = write_new(folder/'probe.json', {'scope': scope_ref, 'current_DNS_ipv4': ['8.8.8.8'],
        'probes': [{'ip': '8.8.8.8', 'port': port, 'get_contract_valid': True} for port in [80, 443]],
        'synthetic_CPU_fixture_not_a_real_probe': True})
    resolution = write_new(folder/'resolution.json', {'scope': scope_ref,
        'source': 'synthetic_CPU_fixture', 'hostname': 'httpbin.org', 'ports': [80, 443],
        'ipv4': ['8.8.8.8'], 'selected_ip': '8.8.8.8', 'automatic_retry': False, 'diagnostic': probe})
    policy = SimpleNamespace(__file__=str(scope), GRADING_ROOT=folder/'grading',
        require_v066_allowed=lambda *args, **kwargs: pytest.fail('No live dispatch is authorized'))
    return policy, scope_ref, resolution


def test_actual_cold_provider_manifest_scope_and_validator_chain(tmp_path):
    original_validator = environment.original_tls.validate_environment
    a = cold_fixture(tmp_path/'a')
    b = cold_fixture(tmp_path/'b')
    first = environment.cold_environment(a[0], scope_ref=a[1], directory=tmp_path/'a'/'bindings',
        resolution_ref=a[2], resolution_source='synthetic_CPU_fixture')
    second = environment.cold_environment(b[0], scope_ref=b[1], directory=tmp_path/'b'/'bindings',
        resolution_ref=b[2], resolution_source='synthetic_CPU_fixture')
    first.prepare()
    second.prepare()
    for task in ['psf__requests-1921', 'psf__requests-2931']:
        request = second.request_fields(task)
        assert environment.validate_cold_identity(second, task, request)['frozen_manifest_equals_executing_manifest']
        with pytest.raises(ValueError, match='identity changed'):
            second.validate_request(first.request_fields(task), task)
    second.tls.environment_manifest = lambda: {'wrong': True}
    with pytest.raises(ValueError, match='another manifest'):
        environment.assert_runtime_binding(second.tls)
    assert environment.original_tls.validate_environment is original_validator
    assert original_validator.__globals__['environment_manifest'] is environment.original_tls.environment_manifest


def test_new_scope_requires_new_probe_and_does_not_replace_frozen_directory(tmp_path):
    a = cold_fixture(tmp_path/'a')
    b = cold_fixture(tmp_path/'b')
    with pytest.raises(ValueError, match='new-scope'):
        environment.validate_resolution(a[2], scope_ref=b[1], expected_source='synthetic_CPU_fixture')
    directory = tmp_path/'bindings'
    first = environment.cold_environment(a[0], scope_ref=a[1], directory=directory,
        resolution_ref=a[2], resolution_source='synthetic_CPU_fixture')
    first.prepare()
    second = environment.cold_environment(b[0], scope_ref=b[1], directory=directory,
        resolution_ref=b[2], resolution_source='synthetic_CPU_fixture')
    with pytest.raises(ValueError, match='overwrite'):
        second.prepare()


def test_missing_probe_cannot_qualify_live_task(tmp_path):
    a = cold_fixture(tmp_path/'a')
    adapted = environment.cold_environment(a[0], scope_ref=a[1], directory=tmp_path/'binding')
    adapted.prepare()
    with pytest.raises(ValueError, match='authorized fresh endpoint'):
        adapted.request_fields('psf__requests-1766')
    assert adapted.request_fields('psf__requests-2931')['network_resolution'] is None


def wheel(folder, name, version, dependencies=(), python='>=3.8', extras=()):
    path = folder/(name+'-'+version+'-py3-none-any.whl')
    with zipfile.ZipFile(path, 'w') as archive:
        prefix = name+'-'+version+'.dist-info/'
        archive.writestr(prefix+'METADATA', 'Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+
            '\nRequires-Python: '+python+'\n'+''.join('Provides-Extra: '+item+'\n' for item in extras)+
            ''.join('Requires-Dist: '+item+'\n' for item in dependencies)+'\n')
        archive.writestr(prefix+'WHEEL', 'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
    return reference(path)


def build_source(folder):
    path = folder/'pyproject.toml'
    path.write_text('[build-system]\nrequires = ["setuptools>=45", "setuptools_scm>=6"]\nbuild-backend="setuptools.build_meta"\n')
    return reference(path)


def test_offline_build_keeps_isolation_and_requires_complete_frozen_closure(tmp_path):
    source = build_source(tmp_path)
    setuptools = wheel(tmp_path, 'setuptools', '65.5.0')
    scm = wheel(tmp_path, 'setuptools_scm', '7.0.5', ['packaging>=20'])
    with pytest.raises(ValueError, match='Missing or incompatible'):
        repairs.offline_build_plan(source, [setuptools, scm])
    packaging = wheel(tmp_path, 'packaging', '23.2')
    plan = repairs.offline_build_plan(source, [setuptools, scm, packaging])
    assert not plan['build_isolation_disabled'] and not plan['official_pip_command_changed']
    assert not plan['runtime_qualified'] and not plan['dynamic_backend_requirements_verified']
    plan_ref = write_new(tmp_path/'build.json', plan)
    assert repairs.validate_offline_plan(plan_ref) == plan
    archive = repairs.owned_wheel_archive(plan_ref, instance_id=repairs.PYTEST_TASK,
        container_id='owned-new', owned_container_ids=['owned-new'])
    assert archive['archive'] and archive['network_calls'] == 0
    with pytest.raises(ValueError, match='exact owned'):
        repairs.owned_wheel_archive(plan_ref, instance_id=repairs.PYTEST_TASK,
            container_id='foreign', owned_container_ids=['owned-new'])


@pytest.mark.parametrize('mode', ['version', 'python', 'url'])
def test_unavailable_build_dependency_cannot_fall_back_to_network(tmp_path, mode):
    source = build_source(tmp_path)
    if mode == 'version':
        values = [wheel(tmp_path, 'setuptools', '40.0.0'), wheel(tmp_path, 'setuptools_scm', '7.0.5')]
    elif mode == 'python':
        values = [wheel(tmp_path, 'setuptools', '65.5.0', python='>=3.10')]
    else:
        values = [wheel(tmp_path, 'setuptools', '65.5.0', ['bad @ https://example.test/pkg.whl'])]
    with pytest.raises(ValueError):
        repairs.offline_build_plan(source, values)


def test_pip_is_offline_but_no_build_isolation_bypass(tmp_path):
    result = repairs.offline_environment({'PIP_INDEX_URL': 'https://example.test', 'PIP_NO_BUILD_ISOLATION': '1'})
    assert result['PIP_NO_INDEX'] == '1' and result['PIP_CONFIG_FILE'] == '/dev/null'
    assert 'PIP_INDEX_URL' not in result and 'PIP_NO_BUILD_ISOLATION' not in result
    with pytest.raises(ValueError, match='Conflicting'):
        repairs.offline_environment({'PIP_NO_INDEX': '0'})


def test_real_build_extra_requires_its_marker_dependency_and_rejects_unreviewed_extras(tmp_path):
    path = tmp_path/'pyproject.toml'
    path.write_text('[build-system]\nrequires=["setuptools-scm[toml]>=6.2.3"]\n')
    scm = wheel(tmp_path, 'setuptools_scm', '7.1.0',
        ['tomli>=1; extra == "toml"', 'not_needed; python_version < "3.7"'], extras=['toml', 'other'])
    with pytest.raises(ValueError, match='Missing or incompatible'):
        repairs.offline_build_plan(reference(path), [scm])
    tomli = wheel(tmp_path, 'tomli', '2.0.1')
    result = repairs.offline_build_plan(reference(path), [scm, tomli])
    assert {row['selected_name'] for row in result['requirement_resolution']} == {'setuptools-scm', 'tomli'}
    path.write_text('[build-system]\nrequires=["setuptools-scm[other]>=6.2.3"]\n')
    with pytest.raises(ValueError, match='not explicitly frozen'):
        repairs.offline_build_plan(reference(path), [scm, tomli])


def test_actual_offline_creation_and_start_hooks_check_owned_baseline_and_transfer(tmp_path):
    source = build_source(tmp_path)
    wheels = [wheel(tmp_path, 'setuptools', '65.5.0'), wheel(tmp_path, 'setuptools_scm', '7.1.0')]
    plan = repairs.offline_build_plan(source, wheels)
    plan_ref = write_new(tmp_path/'build.json', plan)
    outputs, commands = [], []
    delegate = SimpleNamespace(id='owned-new', attrs={'Config': {'Env': []}}, reload=lambda: None,
        put_archive=lambda path, body: outputs.append((path, body)) or True)
    preparation = {'mapping': {'instance_id': repairs.PYTEST_TASK, 'public_python': '/frozen/python'},
                   'path': str(tmp_path/'initial-container.json')}
    def checked_exec(container, argv, **kwargs):
        assert container is delegate
        commands.append(argv)
        if argv[:2] == ['mkdir', '-p']:
            return ''
        if 'pyproject_sha256' in argv[-1]:
            return json.dumps({'python': '3.9.20', 'pyproject_sha256': source['sha256']})
        return json.dumps({row['destination']: row['wheel']['sha256'] for row in plan['wheels']})
    ns = {'archive': SimpleNamespace(checked_exec=checked_exec)}
    exec('''
class ObservedContainer:
 def __init__(self, delegate, preparation):
  self.delegate, self.preparation = delegate, preparation
 def start(self):
  return 'actual-parent-start'
class Containers:
 def create(self, **options):
  self.delegate.attrs['Config']['Env'] = [k+'='+v for k,v in options['environment'].items()]
  return ObservedContainer(self.delegate, self.observation)
def score_request():
 return None
def installation_manifest():
 return {'original': True}
''', ns)
    scorer = SimpleNamespace(**ns)
    repairs.bind_offline_build_scorer(scorer, plan_ref)
    factory = scorer.Containers()
    factory.delegate, factory.observation = delegate, preparation
    factory.tracking = {'owned_container_ids': ['owned-new']}
    created = factory.create()
    assert created.start() == 'actual-parent-start'
    assert len(outputs) == 1 and outputs[0][0] == repairs.WHEELHOUSE
    proof = json.loads((tmp_path/'offline-build-preflight-v141.json').read_bytes())
    assert proof['actual_baseline']['pyproject_sha256'] == source['sha256']
    assert proof['network_calls'] == 0 and proof['actual_build_and_gold_empty_qualification_pending']
    assert scorer.score_request.__globals__['Containers'] is scorer.Containers
    assert len(commands) == 3


class Socket:
    def __init__(self, incoming=(), port=80):
        self.incoming, self.sent, self.port = deque(incoming), bytearray(), port
    def recv(self, size):
        return self.incoming.popleft()
    def send(self, body):
        self.sent.extend(body)
        return len(body)
    def setblocking(self, value):
        assert value is False
    def getpeername(self):
        return '8.8.8.8', self.port
    def shutdown(self, how):
        pass
    def close(self):
        pass


def frame(body):
    return bytes([1, 0, 0, 0])+len(body).to_bytes(4, 'big')+body


def relay_control(*, with_eof, with_done=True):
    transport = repairs.transport_adapter(SimpleNamespace(require_v066_allowed=lambda *a, **k: None))
    stop = threading.Event()
    opening = transport.packet(transport.READY)+transport.packet(transport.OPEN, 1, (80).to_bytes(2, 'big'))
    opening += transport.packet(transport.DATA, 1, b'GET /get HTTP/1.1\r\n\r\n')
    pending = [frame(opening)]
    if with_eof:
        pending.append(frame(transport.packet(transport.EOF, 1)))
    pending.append(frame(transport.packet(transport.DONE)) if with_done else b'')
    channel = Socket(pending)
    peer = Socket([b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}']+([b''] if with_eof else []))
    clock = [0.0]
    def lapse(readers, writers):
        clock[0] = 2
        return [], [], []
    def stop_now(readers, writers):
        stop.set()
        return [], [], []
    steps = [([channel], []), ([], [peer]), ([peer], []), ([], [channel])]
    if with_eof:
        # Observe both EOFs, then the next loop is already beyond the idle limit.
        def eof_and_lapse(readers, writers):
            clock[0] = 2
            return [channel, peer], [], []
        steps += [eof_and_lapse, ([], [channel])]
    else:
        steps += [lapse, ([], [channel])]
    steps += [stop_now, ([], [channel]), ([channel], [])]
    order = deque(steps)
    def wait(readers, writers, exceptional, delay):
        value = order.popleft()
        return value(readers, writers) if callable(value) else (*value, [])
    return transport.relay_many(channel, '8.8.8.8', instance_id='psf__requests-1766',
        resolved_ips=['8.8.8.8'], stop_event=stop, limits=transport.Limits(idle_seconds=1),
        connector=lambda *a: peer, wait=wait, clock=lambda: clock[0])


def test_exchanged_http_bytes_without_eof_remain_unknown():
    result = relay_control(with_eof=False)
    assert result['ok'] is False and result['status'] == 'network_failed'
    row = result['connections'][0]
    assert row['outcome'] == 'upstream_idle_timeout' and row['bytes_from_upstream'] > 0
    assert row['tcp_completion_evidence'] is False and row['client_eof_observed'] is False
    assert row['application_success_inferred'] is False


def test_real_two_sided_eof_precedes_idle_but_never_infers_test_success():
    result = relay_control(with_eof=True)
    assert result['ok'] is True and result['connections'][0]['outcome'] == 'tcp_eof'
    assert result['connections'][0]['tcp_completion_evidence'] is True
    assert result['application_success_not_inferred'] is True


def test_missing_done_is_not_upgraded_even_after_both_eof():
    result = relay_control(with_eof=True, with_done=False)
    assert result['ok'] is False and 'without DONE' in result['error']['message']
