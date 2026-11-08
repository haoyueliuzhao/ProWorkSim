"""Seal the original second wave only after real first-wave measurement passes."""
from __future__ import annotations

import importlib.util
import json

from proworksim import software_benchmark_scope_v169 as scope
from proworksim import software_benchmark_sdk_bundle_v168 as bundle
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_benchmark_alignment_contract_v157 import VERSION as ALIGNMENT_VERSION


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def seal():
    if scope.AUTH_FILE.exists():
        raise PermissionError('A sealed deployment cannot be rewritten or relaunched')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    gate_ref = reference(scope.ROOT/'artifacts/software-benchmark-v168/wave1-measurement-r1/gate.json')
    gate = scope.load(gate_ref)
    if (gate.get('advance_to_wave_2') is not True or gate.get('passed') is not True
            or gate.get('planned_episodes') != 36 or gate.get('terminal_episodes') != 36
            or gate.get('scores_consulted') is not False):
        raise PermissionError('First-wave physical measurement has not admitted wave2')
    checked(gate['physical_measurement']); checked(gate['selection'])
    measurement = scope.load(gate['physical_measurement'])
    if measurement.get('issues') or measurement.get('reconciliation', {}).get('passed') is not True:
        raise PermissionError('Actual captured requests and provider usage do not reconcile')
    cpu_ref = reference(scope.ARTIFACT_ROOT/'deployment-cpu-r1/summary.json')
    cpu = scope.load(cpu_ref)
    if cpu.get('passed') is not True:
        raise PermissionError('Current wave2 deployment controls have not passed')
    for ref in cpu['sources']: checked(ref)
    manifest_ref = reference(bundle.OUTPUT/'manifest.json'); manifest = scope.load(manifest_ref)
    if (manifest.get('version') != bundle.VERSION or manifest['probe'].get('model_calls') != 0
            or manifest['probe'].get('all_controller_and_worker_entrypoints_imported') is not True):
        raise ValueError('Current offline bundle has no actual import proof')
    for ref in [*manifest['source_tools'].values(), *manifest['project_modules'].values()]: checked(ref)
    from proworksim.software_benchmark_grading_v169 import validate_environment_preparation
    environment = validate_environment_preparation()
    if environment.get('qualified_count') != 12 or environment.get('passed') is not True or environment['blocked_tasks']:
        raise ValueError('All12 pinned second-wave environments must be qualified')
    env_ref = scope.retain(scope.ARTIFACT_ROOT/'environment-readiness-r1/summary.json', environment)
    predecessor = scope.coexistence_status()
    predecessor_ref = reference(scope.ARTIFACT_ROOT/'predecessor-cleanup-r1/summary.json')
    if predecessor.get('passed') is not True:
        raise PermissionError('Old owned objects are still active')
    unit = module(scope.ROOT/'tools/launch_communication_pilot_v169.py', 'wave2_launch').prepare()['specification']
    preparation = scope.retain(scope.PREPARATION_QUALIFICATION_FILE, {
        'version': 'v169-second-wave-preparation-r1', 'passed': True, 'model_calls': 0,
        'no_previously_called_slot_restarted': True, 'wave1_actual_measurement_gate': gate_ref,
        'source_feedback_replay': reference(scope.ROOT/'artifacts/software-benchmark-v167/physical-source-admission-r1/summary.json'),
        'finalization_controls': reference(scope.ROOT/'artifacts/software-benchmark-v159/finalization-controls-r1/summary.json'),
        'offline_bundle': manifest_ref, 'predecessor_drain': predecessor_ref,
        'deployment_cpu': cpu_ref, 'environment': env_ref})
    proposal = scope.retain(scope.PROPOSAL_FILE, {
        'version': scope.VERSION, 'status': 'within_original_authorized72_not_new_attempts',
        'plan': reference(scope.PLAN_FILE), 'gate': gate_ref,
        'admitted_original_slots': plan['admitted_original_slots'], 'original_uncalled_episodes': 36,
        'additional_attempts': 0, 'maximum_input_output_tokens': 180_000_000,
        'original_cash_authority': reference(scope.BUDGET_BASELINE_FILE),
        'ledger_path': str(scope.LEDGER_FILE), 'cash_cap_CNY': '500.00', 'additional_cash_CNY': '0.00',
        'cash_cap_does_not_guarantee_completion_of_all36': True,
        'model_visible_configuration_changes': [], 'runtime': 'v167_same_repaired_runtime',
        'ordinary_user_coordinator': unit, 'constraints': scope.CONSTRAINTS,
        'old_results_preserved': True, 'shared_host_configuration_changes': 0,
        'other_user_objects_modified': False, 'training': False})
    original_grant = reference(scope.original_scope.ARTIFACT_ROOT/'user-amendment-r1/authorization.json')
    grant = scope.retain(scope.USER_GRANT_FILE, {
        'version': 'v169-original-second-wave-standing-user-grant-r1', 'approved': True,
        'original_user_grant': original_grant, 'proposal': proposal,
        'basis': 'User authorized the original72 team episodes under one500-CNY cap; only the36 never-called wave2 identities resume',
        'standing_Docker_policy': reference(scope.STANDING_POLICY_FILE),
        'additional_model_attempts': 0, 'additional_cash_authorized_CNY': '0.00',
        'shared_host_configuration_changes_authorized': False})
    source_builder = module(scope.ROOT/'tools/seal_role_pilot_v143.py', 'wave2_source_builder')
    roots = [scope.ROOT/p for p in (
        'tools/run_communication_pilot_v169.py', 'tools/launch_communication_pilot_v169.py',
        'tools/prepare_communication_wave2_v169.py', 'tools/seal_communication_wave2_v169.py',
        'tools/audit_communication_wave1_v168.py', 'tools/run_communication_controller_v168.py',
        'src/proworksim/software_benchmark_scope_v169.py', 'src/proworksim/software_benchmark_grading_v169.py',
        'src/proworksim/software_benchmark_host_api_v169.py', 'src/proworksim/software_benchmark_sdk_bundle_v168.py')]
    files = source_builder.source_closure(roots=roots)
    files += [reference(scope.PLAN_FILE), gate_ref, gate['physical_measurement'], gate['selection'],
        cpu_ref, env_ref, manifest_ref, manifest['archive'], preparation, proposal, grant, unit,
        original_grant, predecessor_ref, reference(scope.BUDGET_BASELINE_FILE)]
    sources = scope.retain(scope.SOURCE_FILE, {'version': 'v169-second-wave-source-closure-r1',
        'files': files, 'historical_sealed_sources_changed': False})
    auth = scope.retain(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'execution_alignment_version': ALIGNMENT_VERSION, 'plan': reference(scope.PLAN_FILE),
        'source_index': sources, 'proposal': proposal, 'user_grant': grant, 'gate': gate_ref,
        'API_cash_cap_CNY': '500.00', 'original_ledger': str(scope.LEDGER_FILE),
        'new_cash_budget_CNY': '0.00', 'constraints': scope.CONSTRAINTS,
        'shared_host_configuration_changes': 0, 'model_launch_performed': False})
    scope.require_allowed()
    return {'authorization': auth, 'source_index': sources, 'gate': gate_ref,
        'original_uncalled_episodes': 36, 'model_calls': 0, 'Docker_operations': 0}


if __name__ == '__main__':
    print(json.dumps(seal()))
