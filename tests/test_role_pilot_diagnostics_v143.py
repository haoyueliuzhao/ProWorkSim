"""CPU receipt regressions for the actual missing-controller startup failure."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_alignment_contract_v141 import condition, shared_strategy
from proworksim.software_benchmark_candidates_v054 import checked, write_new
from proworksim.software_benchmark_diagnostic_receipts_v143 import DiagnosticFailure, inspect_diagnostic
from proworksim.storage import read_json

GIB = 1024**3
ORIGINAL = {'type': 'JSONDecodeError', 'message': 'Expecting value: line 1 column 1 (char 0)'}


def loader(ref):
    return read_json(checked(ref))


def inspect(ref, spec):
    return inspect_diagnostic(ref, spec, load=loader, condition=condition, shared_strategy=shared_strategy,
                              controller_memory_bytes=32*GIB)


def receipts(folder, *, group='S1', failed=False, cleanup=True, controller=True):
    folder.mkdir(parents=True, exist_ok=True)
    members = condition(group)['fixed_members']
    quiet = write_new(folder/'quiescence.json', {'quiescent': cleanup, 'all_owned_objects_removed': cleanup,
        'cleanup_errors': [], 'create_result_unknown': False})
    result = {'status': 'technical_unknown' if failed else 'closed', 'passed': not failed,
              'model_calls': 0, 'quiescence': quiet}
    if failed:
        result['error'] = copy.deepcopy(ORIGINAL)
    if controller:
        result['controller_result'] = write_new(folder/'controller.json', {
            'diagnostic_passed': True, 'team_diagnostic': {'passed': True, 'model_calls': 0,
                'organization_id': group, 'fixed_members': members},
            'private_sessions': {m:'cpu-session-'+m for m in members},
            'actual_member_registry': {m:{'status':'live'} for m in members},
            'execution_alignment': shared_strategy(group), 'content_tokenizer': {'actual_offline_fixture': True},
            'process_resource_peak': {'measured': True, 'peak_rss_bytes': 500*1024**2},
            'collaboration_observation': None})
    return write_new(folder/'result.json', result)


@pytest.mark.parametrize('cleanup', [True, False])
def test_original_failed_error_survives_missing_controller_and_cleanup_state(tmp_path, cleanup):
    ref = receipts(tmp_path, failed=True, controller=False, cleanup=cleanup)
    with pytest.raises(DiagnosticFailure, match='JSONDecodeError: Expecting value') as caught:
        inspect(ref, {'index':5, 'organization_id':'S1'})
    report = caught.value.report
    assert report['classification'] == 'diagnostic_initialization_failed'
    assert report['original_error'] == ORIGINAL and report['model_calls'] == 0
    assert report['cleanup_status'] == ('proven' if cleanup else 'not_proven')
    assert report['controller_result'] is None and report['automatic_retry'] is False
    assert 'KeyError' not in str(caught.value)


def test_missing_cleanup_keeps_original_failure_primary(tmp_path):
    ref = write_new(tmp_path/'result.json', {'status':'technical_unknown','passed':False,
        'model_calls':0, 'error':ORIGINAL})
    with pytest.raises(DiagnosticFailure, match='cleanup=unknown') as caught:
        inspect(ref, {'index':5,'organization_id':'S1'})
    assert caught.value.report['original_error'] == ORIGINAL
    assert caught.value.report['classification'] == 'diagnostic_initialization_failed'


def test_closed_without_controller_is_named_incomplete_not_keyerror(tmp_path):
    ref = receipts(tmp_path, controller=False)
    with pytest.raises(DiagnosticFailure) as caught:
        inspect(ref, {'index':5,'organization_id':'S1'})
    assert caught.value.report['classification'] == 'diagnostic_controller_receipt_missing'
    assert caught.value.report['cleanup_status'] == 'proven'
    assert caught.value.report['passed'] is False
    assert caught.value.report['original_result_passed'] is True


def test_valid_private_runtime_accepts_unknown_observation_measurement(tmp_path):
    report = inspect(receipts(tmp_path, group='REVIEW2'), {'index':3,'organization_id':'REVIEW2'})
    assert report['classification'] == 'diagnostic_verified'
    assert report['observation_summary_required_for_business_closure'] is False


def runner():
    path = Path(__file__).parents[1]/'tools/run_role_pilot_v143.py'
    spec = importlib.util.spec_from_file_location('v143_diagnostic_runner_control', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_new_runner_mixed_diagnostic_identities_never_reenters_retired_one(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module.scope, 'API_ROOT', tmp_path/'coordinator')
    monkeypatch.setattr(module.scope, 'PREPARATION_QUALIFICATION_FILE', tmp_path/'qualification.json')
    specs = [{'index':index, 'organization_id':group, 'slot_id':f'cpu-{group}'}
             for index,group in ((5,'S1'),(2,'FREE2'),(3,'REVIEW2'),(4,'REVIEW2'))]
    rows = [{'slot_id':f'cpu-{g}', 'organization_id':g} for g in ('S1','FREE2','REVIEW2')]
    refs = {s['index']:receipts(tmp_path/str(s['index']), group=s['organization_id']) for s in specs}
    calls = []
    def run(row, resident, *, diagnostic, diagnostic_index):
        assert diagnostic is True and resident == {}
        calls.append(diagnostic_index)
        return refs[diagnostic_index]
    result = module.prepare_diagnostics(SimpleNamespace(_run=run), {'rows':rows,'diagnostics':specs})
    assert calls == [5,2,3,4] and 1 not in calls
    value = loader(result)
    assert value['passed'] and value['retired_diagnostic_reentered'] is False


def test_new_runner_archives_primary_failure_and_does_not_advance_or_mask_write_failure(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module.scope, 'API_ROOT', tmp_path/'coordinator')
    ref = receipts(tmp_path/'failed', failed=True, controller=False)
    spec = {'index':5,'organization_id':'S1','slot_id':'cpu-S1'}
    calls, saved = [], []
    def run(*_args, **kwargs):
        calls.append(kwargs['diagnostic_index'])
        return ref
    def retain(path, value):
        saved.append((path, value))
        raise OSError('Synthetic diagnostic-log disk failure')
    monkeypatch.setattr(module.scope, 'retain', retain)
    with pytest.raises(DiagnosticFailure, match='JSONDecodeError') as caught:
        module.prepare_diagnostics(SimpleNamespace(_run=run), {'rows':[{'slot_id':'cpu-S1'}],
            'diagnostics':[spec,dict(spec,index=2)]})
    assert calls == [5] and len(saved) == 1
    assert saved[0][0] == tmp_path/'coordinator/diagnostic-failures/5.json'
    assert caught.value.report['original_error'] == ORIGINAL
    assert caught.value.report['failure_report_write_error']['type'] == 'OSError'
