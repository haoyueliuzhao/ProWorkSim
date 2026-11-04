"""CPU contract regression: HTTPS may have a legacy http URL echo, no sockets."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run():
    helper = load('public_fixture_v119', ROOT/'tools/public_fixture_diagnostic_v119.py')
    admission = load('fixture_admission_v119', ROOT/'src/proworksim/software_benchmark_generation_admission_v119.py')
    tree = ast.parse(helper.TEST_SOURCE, feature_version=(3, 9))
    names = {'_assert_get_contract', 'test_http_public_fixture', 'test_https_public_fixture'}
    selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    requested, properties = [], {}
    ca = '/frozen/public-fixture/cacert.pem'

    class Response:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self.payload = payload if payload is not None else {'args': {}, 'headers': {'Host': '127.0.0.1:4319'},
                                                                 'url': 'http://127.0.0.1:4319/get'}

        def json(self):
            return self.payload

    def scripted_get(url, **kwargs):
        assert kwargs == {'timeout': 5}  # No verify=False or additional environment workaround.
        requested.append(url)
        return Response()

    namespace = {'os': SimpleNamespace(environ={'REQUESTS_CA_BUNDLE': ca}),
                 'certs': SimpleNamespace(where=lambda: ca), 'requests': SimpleNamespace(get=scripted_get)}
    exec(compile(selected, 'actual-v119-diagnostic-test-bodies', 'exec'), namespace)
    namespace['test_http_public_fixture'](lambda path: 'http://127.0.0.1:4319/'+path, properties.__setitem__)
    namespace['test_https_public_fixture'](SimpleNamespace(url='https://127.0.0.1:4319'), None, properties.__setitem__)
    assert requested == ['http://127.0.0.1:4319/get', 'https://127.0.0.1:4319/get']
    assert properties['requested_scheme'] == 'https' and properties['http_status'] == 200
    assert properties['verification_CA_path'] == ca
    rejected = []
    for label, response in [('bad_status', Response(503)), ('nonobject_JSON', Response(payload=[])),
                             ('nonobject_args', Response(payload={'args': [], 'headers': {}})),
                             ('nonobject_headers', Response(payload={'args': {}, 'headers': []}))]:
        try:
            namespace['_assert_get_contract'](response, properties.__setitem__)
            raise RuntimeError('Invalid public contract accepted: '+label)
        except AssertionError:
            rejected.append(label)
    manifest = json.loads(admission.MANIFEST.read_bytes())
    source = Path(manifest['original_source_manifest']['path'])
    task = json.loads(source.read_bytes())['tasks'][0]
    text = json.loads((source.parent/task['initial_tree']['path']).read_bytes())['files']['test_requests.py']
    assert "['url']" not in text and '["url"]' not in text
    assert "get('url')" not in text and 'get("url")' not in text
    result = {'version': 'v119-public-fixture-contract-regression-controls-r1', 'passed': True,
              'original_public_fixture_sha256': manifest['public_fixture_sha256'],
              'original_public_tests_have_no_JSON_url_accessor_assertion': True,
              'actual_v119_test_bodies_executed_with_scripted_HTTP': True,
              'legacy_http_scheme_echo_accepted_for_scripted_HTTPS_response': True,
              'synthetic_requested_urls': requested, 'negative_contracts_rejected': rejected,
              'TLS_disabling_request_argument_added': False, 'tests_status_field_names_unchanged': True,
              'descriptor': admission.diagnostic_descriptor(),
              'CA_profile_regenerated': False, 'v118_false_result_overwritten': False,
              'real_HTTP_or_TLS_connections': 0, 'model_calls': 0, 'Docker_operations': 0,
              'runtime_qualification_passed': False, 'new_private_actor_diagnostic_still_required': True}
    output = ROOT/'artifacts/software-benchmark-v119/public-fixture-contract-controls-r1'
    output.mkdir(parents=True, exist_ok=True)
    (output/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
