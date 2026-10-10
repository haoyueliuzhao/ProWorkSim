"""Narrow v045 admission assembled from preserved CPU evidence, without replay."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

VERSION = 'software-organization-diagnostic-v0.45'
SOURCE = Path(__file__).resolve().parents[1]
ASSETS = 'examples/software-organization-v045/'
ROOTS = ('sc-event-import-atomic-ha-v045', 'sc-rule-migration-hb-v045')
TEST = 'tests/test_software_organization_v045.py'
DRIVER = 'scripts/software_organization_v045.py'
QUALIFIER = 'scripts/software_organization_qualification_v045.py'
HOST_NEW = {'scripts/software_organization_admission_v045.py', 'tests/test_software_organization_admission_v045.py',
            'scripts/software_organization_cpu_repair_v045.py'}
MANIFEST = ASSETS + 'source-manifest.json'
FAILED_TEST = 'test_published_version_and_private_report_round_trip_use_new_root_and_old_pages'
ROUTES = {root + '-' + condition for root in ('LA', 'HA', 'LB', 'HB') for condition in ('S1', 'F2', 'O3')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def source_files(source_root=SOURCE):
    root = Path(source_root)
    paths = [p for folder in ('src', 'scripts', 'tests') for p in (root / folder).rglob('*.py')]
    paths += [p for p in (root / ASSETS).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def bind(path, evidence, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    require(expected is None or actual == expected, 'Evidence hash changed: ' + str(path))
    evidence[str(path)] = {'path': str(path), 'sha256': actual}
    return path


def bind_refs(value, evidence):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            bind(value['path'], evidence, value['sha256'])
        for child in value.values():
            bind_refs(child, evidence)
    elif isinstance(value, list):
        for child in value:
            bind_refs(child, evidence)


def load(path, evidence):
    value = read(bind(path, evidence))
    bind_refs(value, evidence)
    return value


def check_fixture_edit(before, after):
    expected = before
    for member in ('partner', 'child'):
        old = f"assert call(world, {member}, 'read_file', path=path)['text'] == shared_text"
        new = (f"assert call(world, {member}, 'read_file', path=path, start_line=1, "
               "max_lines=len(shared_text.splitlines()))['text'] == '\\n'.join(shared_text.splitlines())")
        require(expected.count(old) == 1, 'Unexpected failed-fixture source')
        expected = expected.replace(old, new)
    require(after == expected, 'Only the two failed-fixture read_file assertions may change')
    tree = ast.parse(before)
    target = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == FAILED_TEST)
    require(all(f"call(world, {member}, 'read_file', path=path)" in ast.get_source_segment(before, target)
                for member in ('partner', 'child')), 'Fixture edits must remain inside the failed test')


def check_manifest_extension(before, after, originals, current):
    expected = copy.deepcopy(before)
    changes = []
    for index, case_id in ((1, ROOTS[0]), (3, ROOTS[1])):
        old, new = originals[case_id], current[case_id]
        count = 3 if index == 1 else 4
        require({k: v for k, v in old.items() if k != 'cases'} == {k: v for k, v in new.items() if k != 'cases'}
                and new['cases'][:len(old['cases'])] == old['cases'] and len(new['cases']) == len(old['cases']) + count,
                'Private extension must append the declared checks without replacing old cases')
        require(before['cases'][index]['task_id'] == after['cases'][index]['task_id'] == case_id,
                'Private extension root changed')
        for key in ('independent_driver_sha256', 'private_check_count'):
            expected['cases'][index][key] = after['cases'][index][key]
            changes.append(f'cases/{index}/{key}')
        expected['cases'][index]['files_sha256']['acceptance.json'] = after['cases'][index]['files_sha256']['acceptance.json']
        changes.append(f'cases/{index}/files_sha256/acceptance.json')
        require(after['cases'][index]['private_check_count'] == len(new['cases']), 'Private count mismatch')
    expected['sha256'] = after['sha256']
    require(expected == after, 'Unrelated business manifest fields changed')
    return [*changes, 'sha256']


def check_driver_edit(before, after):
    old_tree, new_tree = ast.parse(before), ast.parse(after)
    expected = ast.parse("def validate_qualification(path):\n    from scripts.software_organization_admission_v045 import validate_admission\n    return validate_admission(path, source_root=SOURCE)\n").body[0]
    matched = 0
    for index, node in enumerate(old_tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == 'validate_qualification':
            old_tree.body[index] = expected
            matched += 1
    require(matched == 1 and ast.dump(old_tree) == ast.dump(new_tree), 'Only the declared admission delegation may change in the driver')


def check_sources(prior, source_root, fixture_receipt, evidence):
    root = Path(source_root)
    current = source_files(root)
    old = prior['source_files']
    allowed = {TEST, DRIVER, QUALIFIER, MANIFEST, *(ASSETS + case_id + '/acceptance.json' for case_id in ROOTS)}
    added = set(current) - set(old)
    changed = {p for p in old if current.get(p) != old[p]}
    require(not (set(old) - set(current)) and added <= HOST_NEW and changed <= allowed,
            'Undeclared source change invalidates CPU evidence reuse')
    previous_test = Path(fixture_receipt).parent / 'previous-test.py'
    bind(previous_test, evidence, old[TEST])
    check_fixture_edit(previous_test.read_text(), (root / TEST).read_text())
    if DRIVER in changed:
        before = root / 'runs/v045-controls/admission-source-before/software_organization_v045.py'
        bind(before, evidence, old[DRIVER])
        check_driver_edit(before.read_text(), (root / DRIVER).read_text())
    if QUALIFIER in changed:
        before = root / 'runs/v045-controls/admission-source-before/software_organization_qualification_v045.py'
        bind(before, evidence, old[QUALIFIER])
        previous = before.read_text()
        replacement = "read_json(Path(selected_ref['path']))"
        require(previous.count("read_json(selected_ref['path'])") == 1
                and previous.replace("read_json(selected_ref['path'])", replacement) == (root / QUALIFIER).read_text(),
                'Only Path coercion in CPU receipt inspection may change in qualifier')
    return current, {'changed': sorted(changed), 'added_host_controls': sorted(added), 'unchanged_source_count': len(old) - len(changed)}


def check_measurements(measurements, count):
    require(len(measurements) == count and all(
        m.get('selected_hard_capacity_passed') is True and m.get('context_limit') == 16384
        and m.get('reserved_output_tokens') == 2048 and m.get('prompt_tokens', 16385) + 2048 <= 16384
        and bool(m.get('preservation_checks')) and all(m['preservation_checks'].values())
        and bool(m.get('protected_preservation_checks')) and all(m['protected_preservation_checks'].values())
        for m in measurements), 'Native hard capacity or material preservation evidence incomplete')


def check_native(native, evidence):
    rows = native.get('routes', [])
    require(native.get('kind') == 'twelve_new_material_native_cpu_routes_repaired'
            and native.get('passed') is True and not native.get('failures') and len(rows) == 12
            and {r['route_id'] for r in rows} == ROUTES and set(native.get('required_route_ids', [])) == ROUTES,
            'All twelve unique native material units must pass')
    require(native.get('new_model_calls') == 0 and native.get('model_weights_loaded') is False
            and native.get('new_backward_calls') == 0 and native.get('actual_gpu_work') == 0
            and native.get('original_prepared_requests') == 36 and native.get('supplemental_prepared_requests') == 8
            and native.get('old_requests_retokenized') == native.get('old_runtimes_resumed') == 0
            and native.get('continuous_four_step_routes_claimed') is False,
            'Native controls must preserve 36 old requests and only add eight CPU initial shapes')
    original = load(native['original_failed_receipt']['path'], evidence)
    require(original.get('passed') is False and original.get('prepared_requests') == 36
            and original.get('programmed_responses') == 36, 'Original native failure and work counts must remain intact')
    for row in rows:
        value = load(row['original_route']['path'], evidence)
        review = load(row['readonly_review']['path'], evidence)
        require(row.get('passed') is True and value.get('passed') is False
                and value.get('route_id') == row['route_id'] == review.get('route_id')
                and value.get('failure') == {'type': 'AttributeError', 'message': "'str' object has no attribute 'read_text'"},
                'Only the original CPU receipt-inspection failure may be repaired')
        check_measurements(value.get('measurements', []), 3)
        require(review.get('passed') is True and review.get('old_requests_not_retokenized') is True
                and bool(review.get('checks')) and all(v is True for v in review['checks'].values()),
                'Read-only action and exact-home checks are incomplete')
        expected_actors = ['member_001'] if value['condition'] == 'S1' else ['member_001', 'member_002']
        require(row.get('initial_shapes_complete') is True and sorted(row.get('initial_actor_ids', [])) == expected_actors,
                'Every initial actor must have a qualified input shape')
        supplemental = row.get('supplemental_initial_shape')
        if value['condition'] == 'S1':
            require(supplemental is None, 'S1 must not acquire a hidden partner')
        else:
            extra = load(supplemental['path'], evidence)
            require(extra.get('passed') is True and extra.get('route_id') == row['route_id']
                    and extra.get('member') in set(expected_actors) - {value['first_member']}
                    and extra.get('prepared_requests') == extra.get('programmed_responses') == 1,
                    'Require one independent missing-partner initial shape, not a route replay')
            check_measurements(extra.get('measurements', []), 1)


def finalize(prior_qualification, fixture_receipt, extension_receipt, native_receipt, final_check_receipt,
             output, source_root=SOURCE):
    output, root = Path(output), Path(source_root)
    require(not output.exists(), 'Admission is immutable; choose a new output')
    evidence = {}
    prior = load(prior_qualification, evidence)
    require(prior.get('version') == VERSION and prior.get('passed') is False
            and prior.get('new_model_calls') == 0 and prior.get('model_weights_loaded') is False,
            'Keep the original failed CPU qualification')
    checks = prior['checks']
    require([c['exit_code'] for c in checks] == [1, 0, 0] and not any(c.get('skipped') for c in checks), 'Unexpected original check history')
    require('1 failed, 56 passed, 1 deselected' in Path(checks[0]['log']['path']).read_text()
            and '1 passed' in Path(checks[2]['log']['path']).read_text(), 'Original successful-control counts not bound')
    reuse = load(prior['evidence']['source_reuse']['path'], evidence)
    require(reuse.get('passed') is True and all(item['unchanged'] for item in reuse['files'].values()), 'Inherited source evidence failed')
    fixture = load(fixture_receipt, evidence)
    require(fixture.get('passed') is True and fixture.get('returncode') == 0 and fixture.get('selected_tests') == 1
            and fixture.get('other_controls_repeated') == 0 and fixture.get('native_sdk_repeated') == 0
            and fixture.get('source_contract_changed') is False and fixture.get('new_model_calls') == 0
            and fixture.get('model_weights_loaded') is False, 'Require only the repaired failed test')
    fixture_dir = Path(fixture_receipt).parent
    repair = read(bind(fixture_dir / 'repair.json', evidence, fixture['repair_receipt_sha256']))
    bind(prior_qualification, evidence, repair['qualification_sha256'])
    bind(fixture_dir / 'pytest.log', evidence, fixture['log_sha256'])
    bind(root / TEST, evidence, fixture['source_file_sha256'])
    current, differences = check_sources(prior, root, fixture_receipt, evidence)
    extension = load(extension_receipt, evidence)
    require(extension.get('passed') is True and extension.get('private_driver_executions') == 2
            and extension.get('public_driver_executions') == 0 and extension.get('negative_control_executions') == 0
            and extension.get('observation_count') == extension.get('passed_observations') == 30
            and extension.get('all_business_sources_unchanged_during_execution') is True
            and all(extension.get(k) == 0 for k in ('new_model_calls', 'new_tokenizer_calls', 'new_gpu_calls', 'new_backward_calls')),
            'Two final private reference witnesses required')
    record = load(extension['sources']['extension_record']['path'], evidence)
    archive = Path(record['before_manifest']['path']).parent
    before = read(bind(archive / 'source-manifest.json', evidence, prior['source_files'][MANIFEST]))
    after = read(root / MANIFEST)
    originals, expanded = {}, {}
    for case_id in ROOTS:
        relative = ASSETS + case_id + '/acceptance.json'
        originals[case_id] = read(bind(archive / case_id / 'acceptance.json', evidence, prior['source_files'][relative]))
        expanded[case_id] = read(root / relative)
        require(expanded[case_id]['cases'][len(originals[case_id]['cases']):] == record['added_cases'][case_id], 'Undeclared private check appended')
    manifest_paths = check_manifest_extension(before, after, originals, expanded)
    require({r['task_id'] for r in extension['cases']} == set(ROOTS), 'Private reference root mismatch')
    for row in extension['cases']:
        receipt = load(row['receipt']['path'], evidence)
        require(row['passed'] is True and receipt['passed'] is True and receipt['observation_count'] == 15
                and len(receipt['checks']) == 15 and all(c['passed'] for c in receipt['checks'])
                and receipt['task_id'] == row['task_id']
                and receipt['private_driver_sha256'] == next(c['independent_driver_sha256'] for c in after['cases'] if c['task_id'] == row['task_id']),
                'Private reference acceptance failed')
    native = load(native_receipt, evidence)
    check_native(native, evidence)
    host = load(final_check_receipt, evidence)
    require(host.get('passed') is True and host.get('source_files') == current
            and {c['kind'] for c in host['checks']} == {'admission_tests', 'ruff'}
            and len(host['checks']) == 2 and all(c['exit_code'] == 0 and not c.get('skipped') for c in host['checks']),
            'New admission controls and final Ruff must pass')
    value = {'version': VERSION, 'admission_version': 'v045-composed-cpu-admission-v1', 'passed': True,
        'source_files': current, 'source_differences': differences, 'manifest_changed_paths': manifest_paths,
        'prior_qualification_preserved_false': True, 'reused_cpu_passed': 56, 'reused_native_sdk_passed': 1,
        'repaired_cpu_passed': 1, 'native_route_count': 12, 'native_material_unit_count': 12,
        'native_original_continuous_requests': 36, 'native_independent_partner_initial_requests': 8,
        'continuous_four_step_routes_claimed': False, 'new_private_driver_executions': 2,
        'checks': host['checks'], 'evidence': evidence, 'new_model_calls': 0, 'model_weights_loaded': False,
        'new_backward_calls': 0, 'old_model_slots_replayed': 0, 'historical_tokenizer_requests_replayed': 0,
        'scope': 'Reuse 56 unchanged passing CPU controls and one native SDK control; repair one fixture and add two extended private reference witnesses and host controls. Twelve new-material condition units comprise 36 original consecutive programmed requests closed by read-only review plus eight independent partner-initial supplements; they are not twelve continuous four-step routes. Preserve both failed original receipts and separate CPU costs. Real 9B model calls, historical request replay and parameter updates remain zero.'}
    require(current == source_files(root), 'Source changed during admission composition')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return value


def validate_admission(path, source_root=SOURCE):
    value = read(path)
    require(value.get('version') == VERSION and value.get('admission_version') == 'v045-composed-cpu-admission-v1'
            and value.get('passed') is True and value.get('source_files') == source_files(source_root)
            and value.get('new_model_calls') == 0 and value.get('model_weights_loaded') is False
            and value.get('new_backward_calls') == 0 and value.get('prior_qualification_preserved_false') is True
            and (value.get('reused_cpu_passed'), value.get('reused_native_sdk_passed'), value.get('repaired_cpu_passed'), value.get('native_route_count')) == (56, 1, 1, 12),
            'Require the complete source-bound composed v045 admission')
    require(bool(value.get('evidence')), 'Admission evidence missing')
    bind_refs(value['evidence'], {})
    return value
