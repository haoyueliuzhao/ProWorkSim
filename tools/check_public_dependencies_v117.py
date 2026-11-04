"""Collect a tiny public fixture override with actual pytest; never start HTTP."""
from __future__ import annotations
import argparse
from importlib import util
import json
import os
from pathlib import Path
import sys


def control(payload, output):
    payload, output = Path(payload).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    sys.dont_write_bytecode = True
    counts = {'network': 0, 'process': 0}
    def audit(event, _args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            counts['network'] += 1
            raise AssertionError('Collection control may not open any listener or use the network')
        if event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'}:
            counts['process'] += 1
            raise AssertionError('Collection control may not start child processes')
    sys.addaudithook(audit)
    sys.path.insert(0, str(payload/'site'))
    os.environ.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD', None)
    import pytest
    import importlib.metadata
    declaration = importlib.metadata.distribution('pytest-httpbin')
    assert declaration.version == '0.0.7'
    assert any(x.group == 'pytest11' and x.name == 'httpbin' and x.value == 'pytest_httpbin.plugin'
               for x in declaration.entry_points)
    fixture = '''import pytest
from urllib.parse import urljoin
@pytest.fixture
def httpbin(httpbin):
    httpbin_url = httpbin.url.rstrip('/') + '/'
    def inner(*suffix):
        return urljoin(httpbin_url, '/'.join(suffix))
    return inner
def test_collect_only(httpbin):
    raise AssertionError('This body must never execute')
'''
    (output/'test_public_fixture.py').write_text(fixture)
    observed = {}
    class Check:
        def pytest_collection_finish(self, session):
            assert len(session.items) == 1
            node = session.items[0] if int(pytest.__version__.split('.')[0]) >= 8 else session.items[0].nodeid
            definitions = session._fixturemanager.getfixturedefs('httpbin', node)
            modules = [x.func.__module__ for x in definitions]
            assert modules == ['pytest_httpbin.plugin', 'test_public_fixture'], modules
            assert session._fixturemanager.getfixturedefs('httpbin_secure', node)
            observed.update(parent_fixture_registered=True, original_wrapper_retained=True,
                            fixture_modules=modules, tests_executed=0)
    status = pytest.main(['--collect-only', '-q', '-p', 'no:cacheprovider', str(output/'test_public_fixture.py')], plugins=[Check()])
    assert status == 0 and observed and not any(counts.values())
    helper_path = Path(__file__).with_name('public_test_dependencies_v117.py')
    spec = util.spec_from_file_location('fixture_dependency_helper', helper_path)
    helper = util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest_path = payload/'manifest.json'
    import hashlib
    raw = manifest_path.read_bytes()
    descriptor = {'version': helper.VERSION, 'instance_id': helper.TASK,
        'actor_root': helper.ACTOR_ROOT,
        'manifest': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}
    profile = helper.validate_descriptor(descriptor, instance_id=helper.TASK, root=payload)
    original = {'PATH': '/original/python/bin', 'HOME': '/actor'}
    assert helper.effective_test_environment(original, profile)['PYTHONPATH'] == str(payload/'site')
    assert original == {'PATH': '/original/python/bin', 'HOME': '/actor'}
    result = {'version': 'v117-public-dependency-collection-control-r1', 'passed': True,
        'actual_pytest': pytest.__version__, 'actual_python': sys.version.split()[0],
        'production_python39_not_executed': True, 'official_task_suite_not_run': True,
        'original_pytest_not_replaced': True, 'fixture_servers_started': 0,
        'environment_profile_verified': True, 'prohibited_counts': counts, **observed}
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    control(args.payload, args.output)
