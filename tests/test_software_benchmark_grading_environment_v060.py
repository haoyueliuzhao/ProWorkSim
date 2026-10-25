import io
import sys
import tarfile
import types

import pytest

from proworksim import software_benchmark_grading_environment_v060 as env
from proworksim.software_benchmark_candidates_v054 import reference


def test_original_ca_and_httpbin_defaults_are_not_overridden():
    value = env.fixture_environment({'HTTPBIN_URL': 'http://wrong', 'REQUESTS_CA_BUNDLE': '/wrong',
        'SSL_CERT_FILE': '/wrong', 'SSLKEYLOGFILE': '/wrong', 'HTTPS_PROXY': 'http://proxy', 'KEEP': 'value'})
    assert value['KEEP'] == 'value'
    assert value['HTTPS_PROXY'] == value['https_proxy'] == ''
    assert not {'HTTPBIN_URL', 'REQUESTS_CA_BUNDLE', 'SSL_CERT_FILE', 'SSLKEYLOGFILE'} & value.keys()


def test_asset_transfer_preserves_wheel_bytes_without_host_paths(tmp_path):
    wheel = tmp_path / 'a.whl'
    wheel.write_bytes(b'pinned-wheel')
    data = env.archive_assets({'wheels': [reference(wheel)]})
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member, = tar.getmembers()
        assert member.name == 'wheels/a.whl'
        assert member.uid == member.gid == 0
        assert tar.extractfile(member).read() == b'pinned-wheel'


def test_official_cleanup_finishes_transport_before_container_removal(monkeypatch):
    calls = []
    official = types.ModuleType('swebench.harness.run_evaluation')
    def original(*args):
        calls.append('official_remove')
    official.cleanup_container = original
    harness = types.ModuleType('swebench.harness')
    swebench = types.ModuleType('swebench')
    swebench.harness, harness.run_evaluation = harness, official
    for name, module in [('swebench', swebench), ('swebench.harness', harness), ('swebench.harness.run_evaluation', official)]:
        monkeypatch.setitem(sys.modules, name, module)
    wrapper = types.SimpleNamespace(id='owned', finish_transport=lambda: calls.append('transport_finish'))
    tracking = {'environment_container': wrapper, 'owned_container_ids': ['owned']}
    def run():
        official.cleanup_container(None, wrapper, None)
        return 'result'
    assert env.run_official(run, tracking=tracking) == 'result'
    assert calls == ['transport_finish', 'official_remove']
    assert official.cleanup_container is original
    with pytest.raises(ValueError, match='unowned'):
        env.run_official(lambda: official.cleanup_container(None, types.SimpleNamespace(id='other'), None), tracking=tracking)
    assert calls == ['transport_finish', 'official_remove']
    assert official.cleanup_container is original


def test_uncertain_quiescence_retains_active_lease(monkeypatch):
    released = []
    monkeypatch.setattr(env.policy, 'release_container_slot', lambda claim, quiet: released.append((claim, quiet)) or quiet)
    proof = {'quiescent': False, 'cleanup_errors': ['unknown create']}
    env.release_claim({'container_claim': {'path': 'claim'}}, proof)
    assert released == [({'path': 'claim'}, False)]
    assert proof['active_slot_released'] is False


def test_failed_transport_cleanup_is_not_lost(monkeypatch):
    tracking = {}
    def finish(value):
        value.setdefault('transport_cleanup_errors', []).append('CA unavailable')
        return {'thread_finished': True}
    monkeypatch.setattr(env, 'finish_transport', finish)
    assert env.cleanup_transport(tracking) == ['CA unavailable']


def test_create_preserves_cap_boundary_and_claims_before_docker(monkeypatch):
    order = []
    monkeypatch.setattr(env.policy, 'require_v060_rescore_allowed', lambda *a, **k: {})
    monkeypatch.setattr(env.policy, 'validate_task_image', lambda *a: None)
    monkeypatch.setattr(env.policy, 'claim_container_slot', lambda *a: order.append('claim') or {'path': 'claim'})
    monkeypatch.setattr(env.threading, 'Timer', lambda *a: types.SimpleNamespace(start=lambda: None))
    created = types.SimpleNamespace(id='owned')
    def create(**kwargs):
        order.append('docker')
        assert kwargs['cap_add'] == ['NET_ADMIN', 'NET_BIND_SERVICE']
        assert kwargs['cap_drop'] == ['ALL']
        assert kwargs['network_mode'] == 'none'
        assert kwargs['pids_limit'] == 512
        assert kwargs['memswap_limit'] == kwargs['mem_limit']
        assert kwargs['extra_hosts'] == {'httpbin.org': '127.0.0.1'}
        assert kwargs['name'].startswith('pws-v060-psf__requests-1766-')
        return created
    observation = {'mapping': {'instance_id': 'psf__requests-1766'}, 'path': '/run/initial-container.json',
                   'cpuset_cpus': '0,1,2,3', 'dispatch_kind': 'gold'}
    tracking = {'owned_container_ids': [], 'create_result_unknown': False}
    provider = env.EnvironmentContainers(types.SimpleNamespace(create=create), 'image',
        {'memory_bytes': 16 * 1024**3, 'nano_cpus': 4 * 10**9, 'pids_limit': 16384}, observation, tracking=tracking)
    result = provider.create(image='image', cap_add=['SYS_ADMIN'])
    assert result.id == 'owned' and order == ['claim', 'docker']
    assert observation['upstream_capabilities_removed'] == ['SYS_ADMIN']
    assert tracking['owned_container_ids'] == ['owned']
    with pytest.raises(ValueError, match='one bounded'):
        provider.create(image='image')
    assert order == ['claim', 'docker']


def test_create_rejects_host_material_before_consuming_claim(monkeypatch):
    monkeypatch.setattr(env.policy, 'require_v060_rescore_allowed', lambda *a, **k: {})
    monkeypatch.setattr(env.policy, 'validate_task_image', lambda *a: None)
    monkeypatch.setattr(env.policy, 'claim_container_slot', lambda *a: pytest.fail('claim must follow pure validation'))
    provider = env.EnvironmentContainers(None, 'image', {}, {'mapping': {'instance_id': 'psf__requests-1766'}},
        tracking={'owned_container_ids': [], 'create_result_unknown': False})
    with pytest.raises(ValueError, match='Host material'):
        provider.create(image='image', volumes={'/': {'bind': '/host'}})
