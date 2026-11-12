"""Run only in an owned diagnostic actor: actual public Python/pytest loopback."""
from __future__ import annotations
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

VERSION = 'v131-private-localhost-public-fixture-diagnostic-r1'
TASK = 'psf__requests-2931'
PREFIX = 'PWS_V131_PUBLIC_ENVIRONMENT_QUALIFICATION='
PROFILE = Path('/opt/pws-runtime/public-dependencies/v130/manifest.json')
OBSERVER = Path('/opt/pws-runtime/public-test-evidence.py')
EXECUTION = Path('/opt/pws-runtime/public-test-execution.py')
BASELINE_NAMES = ('requirements.txt', 'test_requests.py', 'requests/cacert.pem')
TEST_SOURCE = '''import os
from urllib.parse import urljoin
import pytest
import requests
from pytest_httpbin import certs

@pytest.fixture
def httpbin(httpbin):
    base = httpbin.url.rstrip('/') + '/'
    return lambda path: urljoin(base, path)

def _assert_get_contract(response, record_property):
    record_property('http_status', response.status_code)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get('args'), dict)
    assert isinstance(payload.get('headers'), dict)
    record_property('public_json_contract', 'args_and_headers_objects')
    # A legacy WSGI fixture can echo http:// after a real verified TLS connection.
    # Its URL scheme echo is not part of this environment qualification.

def test_http_public_fixture(httpbin, record_property):
    record_property('requested_scheme', 'http')
    response = requests.get(httpbin('get'), timeout=5)
    _assert_get_contract(response, record_property)

def test_https_public_fixture(httpbin_secure, httpbin_ca_bundle, record_property):
    assert os.environ['REQUESTS_CA_BUNDLE'] == certs.where()
    record_property('requested_scheme', 'https')
    record_property('verification_CA_path', certs.where())
    url = httpbin_secure.url.rstrip('/') + '/get'
    response = requests.get(url, timeout=5)
    _assert_get_contract(response, record_property)
'''


def run(descriptor):
    result = {'version': VERSION, 'instance_id': TASK, 'diagnostic_id': descriptor.get('diagnostic_id'),
              'profile_manifest_sha256': descriptor.get('profile_manifest_sha256'),
              'helper_sha256': descriptor.get('helper_sha256'),
              'observer_sha256': descriptor.get('observer_sha256'),
              'execution_sha256': descriptor.get('execution_sha256'),
              'passed': False, 'status': 'environment_unknown', 'model_calls': 0,
              'organization_id': 'CHIEF', 'fixed_members': ['member_001','member_002','member_003','member_004'],
              'hidden_material_used': False, 'official_scoring': False,
              'network_scope': 'private_container_loopback_only', 'tests': {}, 'components': {},
              'fixture_parent_binding_verified': False, 'repository_CA_and_public_baseline_unchanged': False}
    counts = {'loopback_binds': 0, 'loopback_connections': 0, 'nonloopback_attempts': 0, 'child_process_attempts': 0}
    try:
        if (descriptor.get('version') != VERSION or descriptor.get('instance_id') != TASK
                or descriptor.get('organization_id') != 'CHIEF'
                or descriptor.get('fixed_members') != ['member_001','member_002','member_003','member_004']
                or descriptor.get('network_scope') != result['network_scope']
                or descriptor.get('maximum_loopback_connections') != 32
                or descriptor.get('model_calls') != 0 or descriptor.get('hidden_material_used') is not False):
            raise ValueError('Diagnostic descriptor has another scope')
        # Refuse an accidental host invocation before any fixture import/listener.
        interfaces = [line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]]
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        if (interfaces != ['lo'] or not Path('/testbed/requests').is_dir()
                or status['NoNewPrivs'].strip() != '1'
                or any(int(status[k].strip(), 16) for k in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))):
            raise RuntimeError('This probe requires the isolated capability-free actor, not the host')
        if list(sys.version_info[:2]) != descriptor['expected_python_major_minor']:
            raise RuntimeError('The diagnostic is not using the original Python3.9 interpreter')
        manifest_raw = PROFILE.read_bytes()
        if hashlib.sha256(manifest_raw).hexdigest() != descriptor['profile_manifest_sha256']:
            raise ValueError('The diagnostic public fixture profile differs')
        manifest = json.loads(manifest_raw)
        for source, key in ((OBSERVER, 'observer_sha256'), (EXECUTION, 'execution_sha256')):
            if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != descriptor.get(key):
                raise ValueError('The new structured test evidence implementation changed')
        if manifest.get('public_compatibility', {}).get('version') != 'v130-public-requests-compatibility-r1':
            raise ValueError('Only the repaired public fixture can qualify this organization batch')
        before = {name: hashlib.sha256((Path('/testbed')/name).read_bytes()).hexdigest() for name in BASELINE_NAMES}
        if (before['requirements.txt'] != manifest['requirements_sha256']
                or before['test_requests.py'] != manifest['public_fixture_sha256']):
            raise ValueError('Fixture qualification must run on the unmodified original public baseline')
        sys.path.insert(0, '/testbed')
        sys.dont_write_bytecode = True
        for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
            if os.environ.get(name):
                raise ValueError('The private diagnostic cannot inherit a proxy')

        def local(address):
            return isinstance(address, tuple) and len(address) >= 2 and address[0] in ('127.0.0.1', '::1', 'localhost')

        def audit(event, args):
            if event in ('socket.bind', 'socket.connect'):
                if not local(args[1]):
                    counts['nonloopback_attempts'] += 1
                    raise RuntimeError('Diagnostic sockets are restricted to private loopback')
                key = 'loopback_binds' if event == 'socket.bind' else 'loopback_connections'
                counts[key] += 1
                if counts['loopback_connections'] > 32 or counts['loopback_binds'] > 4:
                    raise RuntimeError('The bounded localhost diagnostic socket allowance is exhausted')
            if event == 'socket.getaddrinfo' and args[0] not in ('127.0.0.1', '::1', 'localhost'):
                counts['nonloopback_attempts'] += 1
                raise RuntimeError('No external hostname resolution in the public fixture diagnostic')
            if event == 'socket.sendto':
                counts['nonloopback_attempts'] += 1
                raise RuntimeError('UDP is not part of the public fixture diagnostic')
            if event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'):
                counts['child_process_attempts'] += 1
                raise RuntimeError('The public fixture diagnostic may use threads, not further subprocesses')
        sys.addaudithook(audit)
        import pytest
        import requests
        from pytest_httpbin import certs
        if pytest.__version__ != descriptor['expected_pytest']:
            raise RuntimeError('The original pytest version differs from the frozen actor profile')
        if not Path(requests.__file__).resolve().is_relative_to('/testbed/requests'):
            raise RuntimeError('The neutral HTTP client did not import the original repository Requests')
        ca_path = Path(certs.where()).resolve()
        if ca_path != PROFILE.parent/'site/pytest_httpbin/certs/cacert.pem':
            raise RuntimeError('The plugin did not expose the frozen public test CA')
        result.update(actual_python=sys.version.split()[0], actual_pytest=pytest.__version__,
                      actual_requests=requests.__version__, public_test_CA_path=str(ca_path))

        class Check:
            def pytest_collection_finish(self, session):
                if len(session.items) != 4:
                    raise ValueError('The diagnostic requires two original public tests and two neutral HTTP/TLS tests')
                node = next(item.nodeid for item in session.items if item.name == 'test_http_public_fixture')
                definitions = session._fixturemanager.getfixturedefs('httpbin', node)
                modules = [value.func.__module__ for value in definitions]
                if modules != ['pytest_httpbin.plugin', 'test_public_fixture_v131']:
                    raise ValueError('The original-style wrapper did not bind the installed parent fixture')
                result['fixture_parent_binding_verified'] = True

            def pytest_runtest_logreport(self, report):
                name = report.nodeid.rsplit('::', 1)[-1]
                if report.when == 'call':
                    result['components'][name] = dict(report.user_properties)
                if report.failed:
                    result['tests'][name] = 'failed'
                    result.setdefault('failure_excerpts', []).append(str(report.longrepr)[-2500:])
                elif report.when == 'call' and name not in result['tests']:
                    result['tests'][name] = 'passed' if report.passed else 'skipped'

        with tempfile.TemporaryDirectory(prefix='pws-v131-public-fixture-') as temporary:
            path = Path(temporary)/'test_public_fixture_v131.py'
            path.write_text(TEST_SOURCE)
            specification = importlib.util.spec_from_file_location('v131_test_execution', EXECUTION)
            execution = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(execution)

            def observed_run(name, arguments, plugins):
                report = Path(temporary)/(name+'-counts.jsonl')
                report.write_bytes(b'')
                token = hashlib.sha256((descriptor['diagnostic_id']+':'+name).encode()).hexdigest()
                os.environ.update(PWS_TEST_OBSERVER_REPORT=str(report), PWS_TEST_OBSERVER_TOKEN=token,
                                  PWS_TEST_OBSERVER_FRAMEWORK='pytest')
                spec = importlib.util.spec_from_file_location('v131_observer_'+name, OBSERVER)
                observer = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(observer)
                status = pytest.main(['-q', '-p', 'no:cacheprovider', '--confcutdir', temporary, *arguments],
                                     plugins=[observer, *plugins])
                evidence = execution.parse_test_evidence(report.read_bytes(), framework='pytest', token=token,
                    process_group=os.getpgrp(), returncode=int(status), timed_out=False)
                return int(status), evidence

            original_targets = ['/testbed/test_requests.py::TestRequests::test_conflicting_post_params',
                                '/testbed/test_requests.py::TestRequests::test_cookie_removed_on_expire']
            code, positive = observed_run('positive', [str(path), *original_targets], [Check()])
            empty = Path(temporary)/'test_empty_v131.py'
            empty.write_text('# A real pytest collection with no tests.\n')
            empty_code, no_tests = observed_run('empty', [str(empty)], [])
            skip = Path(temporary)/'test_skipped_v131.py'
            skip.write_text('import pytest\n@pytest.mark.skip(reason="diagnostic control")\ndef test_skip(): pass\n')
            skip_code, skipped = observed_run('skipped', [str(skip)], [])
            result['public_test_evidence'] = {'positive': positive, 'no_tests': no_tests, 'all_skipped': skipped}
            result['negative_returncodes'] = {'no_tests': empty_code, 'all_skipped': skip_code}
            result['new_count_semantics_verified'] = (
                positive['passed'] is True and positive['counts']['passed'] == 4
                and positive['counts']['tests_run'] == 4
                and no_tests['passed'] is False and no_tests['validation_status'] == 'no_tests'
                and no_tests['counts']['collected'] == 0
                and skipped['passed'] is False and skipped['validation_status'] == 'all_skipped_or_xfailed'
                and skipped['counts']['skipped'] == 1)

        after = {name: hashlib.sha256((Path('/testbed')/name).read_bytes()).hexdigest() for name in BASELINE_NAMES}
        result['repository_CA_and_public_baseline_unchanged'] = before == after
        result['baseline_hashes_before'], result['baseline_hashes_after'] = before, after
        result['pytest_returncode'] = code
        result['passed'] = (code == 0 and result['fixture_parent_binding_verified'] and before == after
                            and result['tests'] == {'test_http_public_fixture': 'passed', 'test_https_public_fixture': 'passed',
                                'test_conflicting_post_params': 'passed', 'test_cookie_removed_on_expire': 'passed'}
                            and result.get('new_count_semantics_verified') is True
                            and not counts['nonloopback_attempts'] and not counts['child_process_attempts'])
        if result['passed']:
            result['status'] = 'qualified'
        else:
            failures = '\n'.join(result.get('failure_excerpts', []))
            result['failure_kind'] = 'public_fixture_TLS_failure' if 'SSL' in failures or 'CERTIFICATE' in failures else 'public_fixture_execution_failure'
    except Exception as error:
        result.update(failure_kind='public_fixture_preparation_failure', error={'type': type(error).__name__, 'message': str(error)})
    result['socket_and_process_counts'] = counts
    print(PREFIX+json.dumps(result, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descriptor-json', required=True)
    options = parser.parse_args()
    raise SystemExit(run(json.loads(options.descriptor_json)))
