"""Freeze the approved 12-repository pilot without admitting API or Docker work."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import re

from proworksim import software_benchmark_scope_v192 as scope
from proworksim import software_benchmark_sdk_bundle_v192 as bundle
from proworksim.software_benchmark_alignment_contract_v192 import VERSION as ALIGNMENT_VERSION
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_critical_v191 import RULES
from proworksim.software_context_task_api_v192 import TaskLedger
from proworksim.software_public_test_view_v192 import VERSION as TEST_VIEW


def read(relative):
    ref = reference(scope.ROOT / relative)
    return ref, scope.load(ref)


def controls():
    cpu = {
        'artifacts/software-benchmark-v191/critical-cpu-r1/pytest-r2.log': 9,
        'artifacts/software-benchmark-v192/cash-cpu-r1/pytest.log': 3,
        'artifacts/software-benchmark-v192/public-test-view-cpu-r1/pytest.log': 3,
        'artifacts/software-benchmark-v192/storage-cpu-r1/pytest.log': 1,
        'artifacts/software-benchmark-v192/host-bindings-cpu-r1/pytest.log': 2,
    }
    evidence = {}
    for name, count in cpu.items():
        path = scope.ROOT / name
        text = path.read_text()
        if not re.search(rf'\b{count} passed in ', text) or re.search(r'\b(?:FAILED|ERRORS)\b', text):
            raise ValueError('A required targeted CPU control did not pass: ' + name)
        evidence[name] = reference(path)
    sdk_controls = {
        'runs/software-benchmark-v192/sdk-controls-r1/summary.json': set(scope.GROUP_IDS),
        'runs/software-benchmark-v192/sdk-critical-reader-r2/summary.json': {'M1-5K'},
        'runs/software-benchmark-v192/sdk-common-view-r3/summary.json': {'M0', 'M1-5K'},
    }
    for name, groups in sdk_controls.items():
        ref, value = read(name)
        if value.get('passed') is not True or {v['group'] for v in value['groups']} != groups:
            raise ValueError('Missing actual SDK scripted control: ' + name)
        for group in value['groups']:
            if (group.get('passed') is not True or group.get('API_calls') != 0
                    or group.get('Docker_operations') != 0
                    or group['observation'].get('runtime_measurement_errors')):
                raise ValueError('SDK source/observer control failed')
            if name.endswith('sdk-common-view-r3/summary.json'):
                if not group.get('reader_reference_selected_from_actual_wire'):
                    raise ValueError('Reader control must select a reference the model actually saw')
                if group['group'] == 'M1-5K' and not group.get('critical_cards_seen_in_actual_wire'):
                    raise ValueError('New policy was not exercised in actual SDK requests')
        evidence[name] = ref
    ref, views = read('artifacts/software-benchmark-v191/offline-views-r1/summary.json')
    if len(views['rows']) != 144 or views['source_final_outcomes_consulted_by_projection']:
        raise ValueError('The fixed 48-point offline comparison changed')
    for value in views['groups'].values():
        if value['points'] != 48 or value['over_input_cap']:
            raise ValueError('Fixed offline contexts did not fit')
    if scope.load(views['rules']) != RULES:
        raise ValueError('Critical event rules changed after the offline comparison')
    evidence['offline_prototype'] = ref
    evidence['critical_rules'] = views['rules']
    return evidence


def main():
    if scope.AUTH_FILE.exists() or (scope.API_ROOT / 'execution-started.json').exists():
        raise ValueError('Never reseal an admitted or entered experiment')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    panel = scope.load(reference(scope.PANEL_FILE))
    if (len(plan['environments']) != 12 or len({r['repo'] for r in panel['tasks']}) != 12
            or Counter(r['group_id'] for r in plan['rows'] if r['primary_panel'])
            != Counter({g: 12 for g in scope.GROUP_IDS})
            or Counter(r['group_id'] for r in plan['rows'] if not r['primary_panel'])
            != Counter({'M0': 6, 'M1-10': 6})):
        raise ValueError('The user-approved 48 primary plus 12 repeat design changed')
    evidence = controls()
    images_ref, images = read('artifacts/software-benchmark-v192/local-images-r2/plan-equivalence.json')
    if (images['current_plan'] != reference(scope.PLAN_FILE)
            or images['all_selected_image_IDs_identical'] is not True
            or images['all_present_at_previous_check'] is not True):
        raise ValueError('The selected image IDs differ from the local inventory')
    evidence['local_image_inventory'] = images_ref
    packed = scope.load(reference(bundle.OUTPUT / 'manifest.json'))
    for ref in [*packed['source_tools'].values(), *packed['project_modules'].values(), packed['archive']]:
        checked(ref)
    if (packed.get('benchmark_scorer_or_gold_modules_included')
            or packed.get('host_key_files_included') or packed.get('downloaded_packages')):
        raise ValueError('The offline model bundle contains an unexpected dependency')
    grant_ref, grant = read('artifacts/software-benchmark-v191/full-task-design-r1/user-authority.json')
    if (grant.get('approved') is not True or grant['new_API_budget_CNY'] != 300
            or grant['total_runs'] != 60 or grant['old_ledger_balance_transferred'] is not False):
        raise ValueError('The explicit new cash and scope reply is missing')
    user_grant = scope.retain(scope.USER_GRANT_FILE, {
        **grant, 'original_user_reply': grant_ref, 'plan': reference(scope.PLAN_FILE),
        'standing_Docker_API_policy': '非干扰实验Docker/API无需另行请求',
        'no_new_host_root_or_shared_configuration_authority': True,
    })
    ledger = TaskLedger(plan=plan)
    cash = ledger.snapshot()
    if (cash['cap_CNY'] != 300 or cash['physical_requests'] or cash['jobs']
            or cash['committed_upper_CNY'] or cash['unentered_repeat_earmark_CNY'] != 120):
        raise ValueError('The new account is not empty with the planned repeat earmark')
    initial_cash = scope.retain(scope.ARTIFACT_ROOT / 'runtime-authorization-r1/initial-cash.json', cash)
    proposal = scope.retain(scope.PROPOSAL_FILE, {
        'version': scope.VERSION, 'plan': reference(scope.PLAN_FILE), 'user_grant': user_grant,
        'constraints': scope.CONSTRAINTS, 'primary': 48, 'repeats': 12, 'different_tasks': 12,
        'new_independent_API_budget_CNY': 300, 'old_ledger_modified_or_balance_transferred': False,
        'unentered_repeat_earmark_CNY_per_episode': 10, 'initial_repeat_earmark_CNY': 120,
        'earmarks_are_estimates_not_worst_case_guarantees': True,
        'started_episodes_finish_above_cash_line': True, 'normal_episode_start_hold_CNY': 5,
        'common_public_test_view_revision': TEST_VIEW, 'storage_policy': scope.STORAGE_POLICY,
        'API_dispatch_requires_successful_zero_model_diagnostics_and_task_controls': True,
        'no_extra_attempts_or_old_unknown_resampling': True,
    })
    gate = scope.retain(scope.ARTIFACT_ROOT / 'sdk-gate-r1/summary.json', {
        'passed': True, 'targeted_CPU_tests_passed': 18, 'evidence': evidence,
        'common_header_after_change_controls': ['M0', 'M1-5K'],
        'all_four_history_strategies_scripted_before_common_header_change': True,
        'critical_rules_frozen': RULES, 'fresh_initial_cash': initial_cash,
        'bundle_manifest': reference(bundle.OUTPUT / 'manifest.json'),
        'actual_benchmark_model_calls': 0, 'new_experimental_Docker_objects': 0,
        'scope': 'CPU, SDK, offline source binding; real isolated task qualification follows',
        'source_tokens_are_local_estimates_not_provider_exact': True,
        'offline_retention_is_rule_defined_not_full_semantic_ground_truth': True,
    })
    spec = importlib.util.spec_from_file_location('v192_source_closure', scope.ROOT / 'tools/seal_role_pilot_v143.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    roots = [p for folder in ('src/proworksim', 'tools', 'tests') for version in (191, 192)
             for p in (scope.ROOT / folder).glob(f'*v{version}.py')]
    files = module.source_closure(roots=roots)
    files += [reference(bundle.OUTPUT / 'manifest.json'), packed['archive'], reference(scope.PLAN_FILE),
              reference(scope.PANEL_FILE), gate, proposal, user_grant, initial_cash]
    files += list(evidence.values())
    files += [reference(scope.ROOT / 'docs/experiments' / name) for name in (
        'software-benchmark-v191-critical-context-p0-report.md',
        'software-benchmark-v192-critical-context-protocol.md')]
    files = list({r['path']: r for r in files}.values())
    sources = scope.retain(scope.SOURCE_FILE, {
        'version': scope.VERSION, 'files': files, 'gate': gate,
        'paid_model_calls_at_freeze': 0, 'new_experimental_Docker_objects_at_freeze': 0,
        'failed_unentered_bundle_r1_preserved': str(bundle.OUTPUT.with_name('sdk-bundle-r1')),
    })
    auth = scope.retain(scope.AUTH_FILE, {
        'version': scope.VERSION, 'status': 'approved', 'plan': reference(scope.PLAN_FILE),
        'source_index': sources, 'constraints': scope.CONSTRAINTS,
        'execution_alignment_version': ALIGNMENT_VERSION, 'cash_cap_CNY': '300.00',
        'common_public_test_view_revision': TEST_VIEW, 'storage_policy': scope.STORAGE_POLICY,
        'proposal': proposal, 'user_grant': user_grant, 'gate': gate,
    })
    scope.require_allowed()
    print(json.dumps({'sealed': True, 'authorization': auth, 'source_files': len(files),
                      'Docker_operations': 0, 'API_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
