"""Exercise original-identity preservation, actual bindings and single-wave exit."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v168 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_wave2_account_v168 import audit, validate_recovery_plan

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/f'{name}.py')
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def test_original_wave2_exact36_no_first_wave_or_seed_changes():
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    original = scope.original_scope.validate_plan(scope.load(reference(scope.original_scope.PLAN_FILE)))
    assert plan['rows'] == [r for r in original['rows'] if r['wave'] == 2]
    assert len(plan['rows']) == 36 and len(plan['environments']) == 12
    assert scope.CONSTRAINTS['maximum_containers'] == 144
    assert scope.CONSTRAINTS['maximum_named_volumes'] == 36
    for key, value in [('seed', -1), ('slot_id', 'fake'), ('wave', 1)]:
        changed = copy.deepcopy(plan); changed['rows'][0][key] = value
        with pytest.raises(PermissionError): scope.validate_plan(changed)


def test_shared_cash_includes_all_approved_recovery_costs_and_only_admits_uncalled():
    plan = scope.load(reference(scope.PLAN_FILE))
    original = scope.load(reference(scope.original_scope.PLAN_FILE))
    snapshot = audit(scope.LEDGER_FILE, original)
    validate_recovery_plan(plan, original, snapshot, coexistence={'passed': True, 'active_old_slots': []})
    assert snapshot['approved_independent_attempts_in_account'] == 14
    assert snapshot['independent_attempt_costs_included'] is True
    assert snapshot['totals']['settled_peak_upper_nanoyuan'] >= 282_148_454_720
    assert len(snapshot['used_original_slots']) == len(snapshot['admitted_original_slots']) == 36
    assert snapshot['cash_cap_CNY'] == '500.00'
    bad = copy.deepcopy(plan); bad['admitted_original_slots'][0] = snapshot['used_original_slots'][0]
    with pytest.raises(ValueError): validate_recovery_plan(bad, original, snapshot)


def test_actual_episode_retains_original_config_and_repairs_runtime_without_old_mutation():
    from proworksim.software_benchmark_episode_v168 import build_episode
    from proworksim import software_benchmark_sdk_bundle_v168 as bundle
    from proworksim import software_benchmark_alignment_contract_v157 as alignment
    value = build_episode(scope=scope, guard=lambda *a, **k: {'status': 'approved',
        'plan': reference(scope.PLAN_FILE), 'source_index': reference(scope.original_scope.SOURCE_FILE),
        'execution_alignment_version': alignment.VERSION})
    assert value._run.__globals__['runtime'] is bundle
    assert value._run.__globals__['validate_condition'] is alignment.validate_condition
    for row in scope.load(reference(scope.PLAN_FILE))['rows']:
        config, condition, limits = value._row_and_config(row, False)
        assert config['slot_id'] == row['slot_id'] and limits['input_plus_output_tokens'] == 5_000_000
    source = (ROOT/'tools/run_communication_controller_v168.py').read_text()
    assert 'software_role_baseline_runtime_v167 as managed' in source
    assert 'software_benchmark_finalization_v159' in source


def test_wave2_is_directly_queued_and_drains_without_waiting_for_missing_wave1_gate(tmp_path, monkeypatch):
    import json
    run = module('run_communication_pilot_v168')
    from proworksim.software_benchmark_group_admission_v157 import FairAdmission, DrainControl, VERSION
    plan = scope.load(reference(scope.PLAN_FILE)); path = tmp_path/'admission.json'
    path.write_text(json.dumps({'version': VERSION, 'batch_root': str(tmp_path), 'mode': 'drain',
        'groups': list(scope.GROUP_IDS), 'maximum_generations': 16, 'revision': 0, 'reason': 'CPU fixture'}))
    admission = FairAdmission(scope.GROUP_IDS, control=DrainControl(path, batch_root=tmp_path,
        groups=scope.GROUP_IDS, maximum=16), maximum=16, maximum_startups=4)
    monkeypatch.setattr(scope, 'reconcile_generation_limit', lambda: {'passed': True})
    runtime = SimpleNamespace(for_group=lambda _: SimpleNamespace(settled_route_witnesses=lambda: True))
    coordinator = run.Coordinator(runtime=runtime, implementation=None, grading=None,
        memory=SimpleNamespace(snapshot=lambda: {}), admission=admission, plan=plan,
        qualifications={k: {'passed': True} for k in plan['environments']}, output=tmp_path/'out',
        cash_status=lambda _: {'state': 'ready', 'can_start_generation': False})
    assert coordinator.wave == 2 and not coordinator.wave2
    assert sum(map(len, coordinator.pending.values())) == 36
    monkeypatch.setattr(run.time, 'sleep', lambda _: pytest.fail('Drained wave2 must exit'))
    result = coordinator.execute()
    assert len(result['deferred']) == 36 and result['wave'] == 2


def test_direct_wave2_cannot_invoke_historical_transition():
    run = module('run_communication_pilot_v168')
    value = run.Coordinator.__new__(run.Coordinator)
    value.wave, value.wave2 = 2, []
    assert value._advance_wave() is None
    value.wave = 1
    with pytest.raises(ValueError): value._advance_wave()
