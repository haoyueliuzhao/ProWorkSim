"""Host-loader isolation controls; these tests do not load CUDA or weights."""
import pytest

from proworksim import software_benchmark_ref_host_v061 as host


def test_environment_does_not_export_private_libc_or_proxy_or_secrets():
    env = host.runtime_environment(inherited={'HOME': '/tmp/user', 'LD_LIBRARY_PATH': '/untrusted',
        'HTTP_PROXY': 'https://proxy', 'OPENAI_API_KEY': 'secret', 'PYTHONPATH': '/wrong'})
    assert 'LD_LIBRARY_PATH' not in env and 'OPENAI_API_KEY' not in env
    assert env['HOME'] == '/tmp/user' and env['HTTP_PROXY'] == ''
    assert env['CUDA_VISIBLE_DEVICES'] == '' and '/wrong' not in env['PYTHONPATH']


def test_root_and_unrelated_cache_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match='independent'):
        host.runtime_environment(cache='/tmp/outside-project')
    monkeypatch.setattr(host.os, 'geteuid', lambda: 0)
    with pytest.raises(PermissionError, match='ordinary'):
        host.runtime_environment()


def test_wrapper_has_no_shell_mount_or_namespace_operations():
    source = host.wrapper_source()
    assert '--argv0' in source and 'execv(args[0], args)' in source
    assert all(x not in source for x in ('system(', 'mount(', 'unshare(', 'chroot(', 'setuid('))
