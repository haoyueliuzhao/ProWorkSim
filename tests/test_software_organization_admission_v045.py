"""Host-only controls for selective v045 evidence reuse and fail-closed binding."""
import copy
import json

import pytest

from scripts import software_organization_admission_v045 as admission


def test_fixture_repair_cannot_change_another_test_or_production_behavior():
    before = (f'def {admission.FAILED_TEST}():\n'
              "    assert call(world, partner, 'read_file', path=path)['text'] == shared_text\n"
              "    assert call(world, child, 'read_file', path=path)['text'] == shared_text\n")
    after = (f'def {admission.FAILED_TEST}():\n'
             "    assert call(world, partner, 'read_file', path=path, start_line=1, max_lines=len(shared_text.splitlines()))['text'] == '\\n'.join(shared_text.splitlines())\n"
             "    assert call(world, child, 'read_file', path=path, start_line=1, max_lines=len(shared_text.splitlines()))['text'] == '\\n'.join(shared_text.splitlines())\n")
    admission.check_fixture_edit(before, after)
    with pytest.raises(ValueError, match='Only the two'):
        admission.check_fixture_edit(before, after + '\n# unrelated drift\n')


def manifests():
    original = {root: {'cases': [{'case_id': 'old-rejection'}]} for root in admission.ROOTS}
    current = {root: {'cases': [*original[root]['cases'], *[{'case_id': str(n)} for n in range(count)]]}
               for root, count in zip(admission.ROOTS, (3, 4))}
    before = {'sha256': 'old', 'cases': [{'task_id': 'LA'}, {'task_id': admission.ROOTS[0],
        'files_sha256': {'acceptance.json': 'old-ha'}, 'private_check_count': 1, 'independent_driver_sha256': 'old'},
        {'task_id': 'LB'}, {'task_id': admission.ROOTS[1], 'files_sha256': {'acceptance.json': 'old-hb'},
         'private_check_count': 1, 'independent_driver_sha256': 'old'}]}
    after = copy.deepcopy(before)
    after['sha256'] = 'new'
    for index, count in ((1, 4), (3, 5)):
        after['cases'][index].update(private_check_count=count, independent_driver_sha256='new')
        after['cases'][index]['files_sha256']['acceptance.json'] = 'new'
    return before, after, original, current


@pytest.mark.parametrize('fault', ['old_case', 'public_manifest'])
def test_private_extension_cannot_remove_old_rejection_or_change_public_material(fault):
    before, after, original, current = manifests()
    assert len(admission.check_manifest_extension(before, after, original, current)) == 7
    if fault == 'old_case':
        current[admission.ROOTS[0]]['cases'][0] = {'case_id': 'replacement'}
    else:
        after['cases'][0]['public_driver_sha256'] = 'different'
    with pytest.raises(ValueError):
        admission.check_manifest_extension(before, after, original, current)


def test_driver_admission_delegation_cannot_alter_model_limits():
    before = 'LIMIT = 128\ndef validate_qualification(path):\n    return path\n'
    after = ('LIMIT = 128\ndef validate_qualification(path):\n'
             '    from scripts.software_organization_admission_v045 import validate_admission\n'
             '    return validate_admission(path, source_root=SOURCE)\n')
    admission.check_driver_edit(before, after)
    with pytest.raises(ValueError, match='Only the declared'):
        admission.check_driver_edit(before, after.replace('LIMIT = 128', 'LIMIT = 129'))


def test_duplicate_native_units_do_not_satisfy_twelve_route_count():
    native = {'kind': 'twelve_new_material_native_cpu_routes_repaired', 'passed': True,
              'required_route_ids': sorted(admission.ROUTES), 'routes': [{'route_id': 'LA-S1'}] * 12}
    with pytest.raises(ValueError, match='twelve unique'):
        admission.check_native(native, {})


def test_hard_capacity_failure_is_not_replaced_by_margin_diagnostics():
    measurement = {'selected_hard_capacity_passed': True, 'context_limit': 16384,
        'reserved_output_tokens': 2048, 'prompt_tokens': 14336,
        'preservation_checks': {'all_required': True}, 'protected_preservation_checks': {'all_required': True},
        'protected_headroom_after_margin_tokens': -1024}
    admission.check_measurements([measurement], 1)
    measurement['prompt_tokens'] += 1
    with pytest.raises(ValueError, match='hard capacity'):
        admission.check_measurements([measurement], 1)


def test_sealed_admission_rejects_source_or_saved_evidence_mutation(tmp_path):
    evidence = tmp_path / 'evidence.log'
    evidence.write_text('original successful check')
    value = {'version': admission.VERSION, 'admission_version': 'v045-composed-cpu-admission-v1',
        'passed': True, 'source_files': admission.source_files(tmp_path), 'new_model_calls': 0,
        'model_weights_loaded': False, 'new_backward_calls': 0, 'prior_qualification_preserved_false': True,
        'reused_cpu_passed': 56, 'reused_native_sdk_passed': 1, 'repaired_cpu_passed': 1, 'native_route_count': 12,
        'evidence': {'log': {'path': str(evidence), 'sha256': admission.sha(evidence)}}}
    path = tmp_path / 'admission.json'
    path.write_text(json.dumps(value))
    assert admission.validate_admission(path, source_root=tmp_path)['passed'] is True
    evidence.write_text('changed')
    with pytest.raises(ValueError, match='Evidence hash changed'):
        admission.validate_admission(path, source_root=tmp_path)
    evidence.write_text('original successful check')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/new.py').write_text('changed = True\n')
    with pytest.raises(ValueError, match='source-bound'):
        admission.validate_admission(path, source_root=tmp_path)
