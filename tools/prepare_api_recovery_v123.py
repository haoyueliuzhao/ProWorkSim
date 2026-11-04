"""Freeze nine explicitly authorized independent API attempts; never run them."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from proworksim import software_benchmark_cash_amendment_v122 as cash
from proworksim import software_benchmark_deepseek_api_v122 as amended_api
from proworksim.software_benchmark_alignment_contract_v117 import validate_condition, validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / 'runs/software-benchmark-v121/project-independent-recovery-r1'
ORIGINAL = ROOT / 'runs/software-benchmark-v118/project-repaired-r1'
BATCH = ROOT / 'runs/software-benchmark-v123/nine-api-recovery-r1'
OUTPUT = ROOT / 'artifacts/software-benchmark-v123/api-recovery-preparation-r1'
VERSION = 'v123-nine-cash-stopped-independent-api-preparation-r1'
SEED_BASE = 20261104012300
PUBLIC_FIELDS = ('instance_id', 'repo', 'base_commit', 'problem_statement')


def read(ref):
    return json.loads(checked(ref).read_bytes())


def main():
    if OUTPUT.exists():
        raise FileExistsError('Do not overwrite the original nine-attempt preparation')
    prior_ref = reference(PRIOR / 'execution-plan.json')
    summary_ref = reference(PRIOR / 'api-coordinator/run-summary.json')
    usage_ref = reference(PRIOR / 'reporting/per-task.json')
    prior, summary, old_usage = read(prior_ref), read(summary_ref), read(usage_ref)
    generations = summary['generation']
    if (summary.get('provider_failures', {}).get('DEEPSEEK', {}).get('reason') != 'api_monetary_budget_exhausted'
            or summary.get('pending_grading_jobs') or summary.get('retained_objects')
            or summary.get('failure') is not None):
        raise ValueError('The original API phase has not closed at the documented cash boundary')
    stopped = sorted((row for row in prior['rows']
        if generations[row['slot_id']]['status'] == 'technical_unknown'), key=lambda row: row['slot_index'])
    if len(stopped) != 9:
        raise ValueError('Include all and only the nine original cash-stopped attempts')
    old_usage_by_id = {item['slot_id']: item for item in old_usage}
    condition_ref = reference(ORIGINAL / 'conditions/PROJECT.json')
    validate_condition(read(condition_ref))
    api = amended_api.bind_api()
    with closing(cash.open_read()) as db:
        totals = api.BudgetLedger._totals(db)
        if totals['inflight']:
            raise ValueError('An API request is still in flight')
        request_records = {}
        for row in stopped:
            records = [dict(record) for record in db.execute(
                'SELECT * FROM requests WHERE slot_id=? ORDER BY request_id', (row['slot_id'],))]
            usage = old_usage_by_id[row['slot_id']]
            if (not records or any(record['status'] != 'settled' for record in records)
                    or len(records) != usage['ledger_requests']
                    or usage['ledger_requests'] != usage['settled_requests']
                    or usage['generation_state'] != 'technical_unknown'
                    or usage['usage_complete_and_called'] is not True
                    or usage['usage_final'] is not True):
                raise ValueError('Every prior request must retain complete, settled cash accounting')
            request_records[row['slot_id']] = {
                'requests': len(records), 'settled_requests': len(records), 'uncertain_requests': 0,
                'settled_cost_nanoyuan': sum(record['settled_nanoyuan'] for record in records),
                'unresolved_reservation_nanoyuan': 0,
                'all_original_request_rows_sha256': hashlib.sha256(cash.encode(records)).hexdigest(),
                'actual_tokens': usage['exact_final_tokens'], 'original_usage_summary': usage_ref,
                'original_result': generations[row['slot_id']]['result']}
        available = api.CAP_NANOYUAN - totals['committed']
        if available != 45 * api.NANOYUAN:
            raise ValueError('The explicitly established CNY45 available balance has changed before preparation')
        for offset, row in enumerate(stopped):
            identity = f"v117:{row['instance_id']}:{row['condition_id']}:{SEED_BASE + offset}"
            if db.execute('SELECT 1 FROM requests WHERE slot_id=?', (identity,)).fetchone():
                raise ValueError('A proposed new attempt already has an API request')

    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT / 'configs').mkdir()
    output_rows, mapping, resources, configs, public_tasks, environments = [], [], {}, {}, [], {}
    prior_ids = {row['slot_id'] for row in prior['rows']}
    prior_seeds = {row['seed'] for row in prior['rows']}
    for offset, old in enumerate(stopped):
        index, seed = 8600 + offset, SEED_BASE + offset
        slot = f"v117:{old['instance_id']}:{old['condition_id']}:{seed}"
        result_ref = generations[old['slot_id']]['result']
        result = read(result_ref)
        if (result['slot_id'] != old['slot_id'] or result['status'] != 'technical_unknown'
                or result.get('error') != {'type': 'InterruptedError',
                    'message': 'Capability coordinator requested owned-episode cancellation'}
                or result.get('candidate_lock') is not None or result.get('retained_objects')
                or result.get('model_bridge_thread_finished') is not True):
            raise ValueError('Selected row is not the exact documented cash-interrupted attempt')
        source = read(old['configuration'])
        if (set(source['public_task']) != set(PUBLIC_FIELDS)
                or source['hidden_material_in_actor_payload'] is not False):
            raise ValueError('Actor input must retain only the admitted unchanged public task')
        if slot in prior_ids or seed in prior_seeds:
            raise ValueError('The new independent attempt must not reuse an old identity')
        row = {**copy.deepcopy(old), 'logical_index': offset + 1, 'slot_index': index,
            'slot_id': slot, 'seed': seed, 'replicate': 2, 'repeat_index': 2,
            'provider_seed_sent': False, 'panel_kind': 'independent_cash_failure_recovery_9',
            'analysis_endpoint': 'independent_recovery_v123', 'original_slot_id': old['slot_id'],
            'original_slot_index': old['slot_index'], 'old_result_overwritten': False,
            'execution_authorized': False}
        validate_plan_identity(row)
        config = {**copy.deepcopy(source),
            **{key: row[key] for key in ('logical_index', 'slot_index', 'slot_id', 'seed', 'replicate',
                                        'repeat_index', 'panel_kind', 'analysis_endpoint')},
            'version': 'v123-independent-cash-recovery-configuration-proposal-r1',
            'preparation_only': True, 'execution_authorized': False,
            'independent_recovery': {'original_row': old, 'original_result': result_ref,
                'provider_attempts_already_consumed': request_records[old['slot_id']]['requests'],
                'original_accounting_retained': True, 'original_attempt_overwritten': False,
                'resume_original_conversation': False, 'reuse_old_worktree_or_feedback': False,
                'previous_attempt_provenance': source['independent_recovery'],
                'new_model_attempt_explicitly_authorized': True,
                'stop_tree_supplemental_scoring_in_this_batch': False},
            'runtime_reuse_proposal': {'target_execution_layer': 'v120',
                'frozen_existing_bundle': reference(ROOT / 'runs/software-benchmark-v120/sdk-bundle-r1/manifest.json'),
                'new_scope_and_host_API_binding_required': 'v123 scope plus v122 amended API view',
                'this_preparation_does_not_start_runtime': True}}
        config.pop('source_configuration_proposal', None)
        if config['public_task'] != source['public_task']:
            raise ValueError('An independent recovery changed the task statement or initial baseline')
        row['configuration'] = write_new(OUTPUT / 'configs' / f'{index}.json', config)
        configs[str(index)] = row['configuration']
        output_rows.append(row)
        public_tasks.append(copy.deepcopy(source['public_task']))
        qualification_ref = reference(PRIOR / 'grading-coordinator/qualifications' / (old['instance_id'] + '.json'))
        qualification = read(qualification_ref)
        if qualification.get('passed') is not True or qualification['instance_id'] != old['instance_id']:
            raise ValueError('The exact old task environment was not qualified')
        environments[old['instance_id']] = {'proposed_configuration': row['configuration'],
            'qualified_existing_configuration': old['configuration'], 'qualification': qualification_ref,
            'qualification_plan': prior_ref, 'original_qualification': qualification['original_qualification'],
            'fresh_gold_empty_controls_proposed': 0,
            'future_runtime_rebinding_and_exact_equivalence_check_required': True}
        usage = request_records[old['slot_id']]
        mapping.append({'instance_id': old['instance_id'], 'original_slot_id': old['slot_id'],
            'original_slot_index': old['slot_index'], 'original_seed': old['seed'],
            'original_result': result_ref, 'new_slot_id': slot, 'new_slot_index': index, 'new_seed': seed,
            'provider_seed_sent': False, 'new_configuration_proposal': row['configuration'],
            'old_provider_calls': usage['requests'], 'old_settled_cost_nanoyuan': usage['settled_cost_nanoyuan'],
            'old_unresolved_reservation_nanoyuan': 0, 'old_actual_tokens': usage['actual_tokens'],
            'previous_v119_slot_id': old['original_slot_id'],
            'previous_v119_slot_index': old['original_slot_index'],
            'selection_reason': 'cash_interruption_without_official_final_candidate',
            'original_results_and_costs_retained': True})
        for prefix in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            key = f'{prefix}-{index}'
            resource = copy.deepcopy(prior['resources'][f'{prefix}-{old["slot_index"]}'])
            resource.update(slot_id=slot, proposal_only=True, execution_authorized=False)
            resources[key] = resource
            for directory in (BATCH, PRIOR, ORIGINAL):
                if (directory / 'resource-claims' / (key + '.json')).exists() or (directory / 'episodes' / str(index)).exists():
                    raise ValueError('A proposed physical identity is already consumed')

    roles = dict(Counter(item['role'] for item in resources.values()))
    if roles != {'actor': 9, 'controller': 9, 'volume': 9, 'score': 9, 'delivery_score': 9}:
        raise ValueError('Resource identity count differs from the nine-task scope')
    old_usage_totals = {'requests': sum(item['requests'] for item in request_records.values()),
        'settled_cost_nanoyuan': sum(item['settled_cost_nanoyuan'] for item in request_records.values()),
        'actual_tokens': {key: sum(item['actual_tokens'][key] for item in request_records.values())
            for key in ('input_tokens', 'output_tokens', 'total_tokens', 'cache_hit_tokens', 'cache_miss_tokens')}}
    if old_usage_totals['requests'] != 270 or old_usage_totals['actual_tokens']['total_tokens'] != 12_394_036:
        raise ValueError('The complete nine-task stopped inventory has changed')
    usage_out = write_new(OUTPUT / 'original-usage.json', {'version': VERSION,
        'original_reporting': usage_ref, 'original_plan': prior_ref,
        'original_coordinator_summary': summary_ref, 'rows': request_records, 'totals': old_usage_totals,
        'old_ledger_rows_edited': False, 'old_uncertain_reservations_released': False})
    interrupted_inventory = write_new(OUTPUT / 'prior-interrupted-inventory.json', {
        'version': VERSION, 'source_plan': prior_ref, 'source_coordinator': summary_ref,
        'rows': [{'row': old, 'original_result': generations[old['slot_id']]['result'],
            'provider_request_count': request_records[old['slot_id']]['requests'],
            'settled_cost_nanoyuan': request_records[old['slot_id']]['settled_cost_nanoyuan'],
            'unresolved_reservation_nanoyuan': 0, 'classification': 'provider_attempt_consumed',
            'failure_reason': 'api_monetary_budget_exhausted',
            'original_actual_tokens': request_records[old['slot_id']]['actual_tokens']}
            for old in stopped],
        'automatic_model_resampling_authorized': False,
        'explicit_new_independent_attempts_authorized': True,
        'selection_is_all_cash_interrupted_tasks': True,
        'old_requests_and_results_retained': True})
    panel_ref = write_new(OUTPUT / 'panel.json', {'version': VERSION,
        'status': 'new_model_attempts_explicitly_authorized_runtime_preparation_only',
        'selection': 'All nine v121 cash-interrupted attempts in original slot order; no model-score selection',
        'source_inventory': interrupted_inventory, 'planned_distinct_tasks': 9, 'planned_new_generations': 9,
        'model': 'deepseek-flash', 'thinking': False, 'arm': 'PROJECT', 'single_agent': True,
        'condition': condition_ref, 'task_ids': [row['instance_id'] for row in output_rows],
        'repository_counts': dict(Counter(item['repo'] for item in public_tasks)),
        'rows': output_rows, 'public_tasks': public_tasks, 'actor_public_fields': list(PUBLIC_FIELDS),
        'seed_base': SEED_BASE, 'seed_rule': 'base plus original v121 cash-stopped slot order offset 0..8',
        'provider_seed_sent': False, 'provider_seed_reproducibility_claim': False,
        'independent_initial_states': True, 'old_worktrees_feedback_or_conversations_reused': False,
        'original_results_overwritten': False, 'new_model_calls_authorized': 9,
        'runtime_authorized_by_this_file': False})
    public_panel_ref = write_new(OUTPUT / 'public-panel.json', {'version': VERSION,
        'tasks': public_tasks, 'allowed_fields': list(PUBLIC_FIELDS),
        'original_task_statements_and_base_commits_unchanged': True})
    mapping_ref = write_new(OUTPUT / 'original-to-recovery.json', {'version': VERSION, 'rows': mapping})
    resources_ref = write_new(OUTPUT / 'resource-identities.json', {'version': VERSION,
        'resources': resources, 'resource_role_counts': roles, 'planned_new_containers': 36,
        'planned_new_named_volumes': 9, 'physical_identity_range': [8600, 8608],
        'runtime_object_IDs_assigned': False, 'scope_implementation_created_by_this_tool': False})
    environment_ref = write_new(OUTPUT / 'environment-bindings.json', {'version': VERSION,
        'environments': environments, 'fresh_controls': 0, 'new_diagnostics': 0,
        'new_neutral_API_calls': 0, 'Requests_network_exception_tasks': [],
        'grading_network_required': False, 'public_baseline_dependencies_changed': False})
    proposal = {'version': VERSION, 'status': 'new_API_attempts_authorized_prepared_pending_runtime_scope',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'explicit_user_instruction': '九题重新调用api进行测试后补评',
        'purpose': 'One new independent model attempt for every v121 cash-interrupted task, then grade its newly closed candidate',
        'batch_root': str(BATCH), 'panel': panel_ref, 'public_panel': public_panel_ref,
        'original_to_recovery': mapping_ref, 'original_usage': usage_out,
        'prior_interrupted_inventory': interrupted_inventory,
        'resource_identities': resources_ref, 'environment_bindings': environment_ref,
        'configuration_proposals': configs, 'proposed_model': 'deepseek-flash',
        'thinking': False, 'condition': condition_ref,
        'proposed_execution_layer_reuse': {'version': 'v120',
            'bundle': reference(ROOT / 'runs/software-benchmark-v120/sdk-bundle-r1/manifest.json'),
            'actor_and_model_schema_prompts_history_unchanged': True,
            'new_API_binding_source': reference(amended_api.__file__)},
        'runtime_limits': {'maximum_generation_pairs': 8, 'maximum_graders': 2,
            'maximum_combined_reserved_CPU': 64, 'maximum_combined_reserved_memory_GiB': 320,
            'maximum_NEW_containers': 36, 'maximum_NEW_named_volumes': 9,
            'actor_per_container': {'CPU': 4, 'memory_GiB': 16},
            'controller_per_container': {'CPU': 2, 'memory_GiB': 16},
            'grader_per_container': {'CPU': 4, 'memory_GiB': 16},
            'coordinator': {'CPU': 8, 'memory_GiB': 32, 'existing_user_unit': 'proworksim-v118-project.service'},
            'container_network': 'none', 'cap_drop': ['ALL'], 'cap_add': [], 'privileged': False,
            'host_bind_mounts': False, 'published_host_ports': False, 'GPU': False,
            'maximum_new_TLS_sessions': 0, 'maximum_new_TLS_connections': 0,
            'host_configuration_mount_network_driver_or_daemon_changes': False,
            'only_new_owned_objects_managed': True, 'actor_external_network_or_answer_search': False,
            'model_API_route': 'Direct official DeepSeek TLS through existing trusted broker; no proxy'},
        'generation_and_cash_budget': {'model_input_plus_output_tokens_per_episode': 5_000_000,
            'new_generation_token_upper_bound': 45_000_000, 'upper_bound_is_expected_consumption': False,
            'cumulative_API_cap_CNY': api.CASH_CAP_CNY, 'additional_cash_over_v122_grant': '0',
            'available_at_preparation_CNY': cash.cny(available), 'ledger_path': str(cash.LEDGER),
            'cash_grant': api.cash_grant, 'cash_amendment_receipt': api.cash_receipt,
            'old_settled_and_uncertain_reservations_retained': True,
            'cash_cap_guarantees_completion_of_all_nine': False,
            'request_policy_max_concurrency': 16, 'absolute_per_request_reservation_CNY': '5.24288',
            'on_cash_exhaustion': 'Preserve records and stop new dispatch; no automatic cap increase or resampling'},
        'launch_gates': {'new_nine_model_attempts_explicitly_authorized': True,
            'old_API_owner_released': True, 'no_two_API_owners_simultaneously': True,
            'source_and_scoring_qualification_bindings_must_be_frozen_before_launch': True,
            'specific_runtime_object_scope_requires_final_review': True,
            'model_or_scoring_exception_isolated_without_retry': True,
            'shared_integrity_or_unknown_cleanup_stops_new_dispatch': True},
        'reporting_contract': {'new_results_endpoint': 'independent_recovery_v123',
            'old_technical_unknown_results_overwritten': False,
            'resume_or_replay_original_conversation_claim': False,
            'stopped_worktree_supplemental_scoring_in_this_batch': False,
            'best_of_old_and_new_candidates_selected': False,
            'code_and_legal_delivery_scored_separately': True,
            'report_per_task_and_group_actual_input_output_cache_and_total_tokens': True,
            'mean_new_attempt_denominator': 9, 'bill_old_and_new_requests_once_each': True,
            'report_old_attempt_cost_separately_from_new_attempt_means': True},
        'prior_plan': prior_ref, 'prior_completion': reference(ROOT / 'artifacts/software-benchmark-v121/completion-status-r1/summary.json'),
        'no_outcome_based_task_selection': True, 'no_new_controls_diagnostics_or_neutral_calls': True,
        'current_authorization': {'new_model_attempts': 9, 'new_API_cash_beyond_v122': 0,
            'runtime_started': False, 'concrete_Docker_scope_finalized_by_this_tool': False},
        'preparation_operations': {'API_calls': 0, 'model_calls': 0, 'Docker_operations': 0,
            'GPU_operations': 0, 'network_connections': 0, 'existing_files_changed': False},
        'preparation_source': reference(__file__)}
    proposal_ref = write_new(OUTPUT / 'proposal.json', proposal)
    check = write_new(OUTPUT / 'preparation-check.json', {'version': VERSION, 'passed': True,
        'all_nine_cash_interrupted_tasks_included': True, 'original_API_requests': 270,
        'original_API_total_tokens': 12_394_036, 'new_IDs_and_seeds_unique_and_disjoint': True,
        'public_task_and_base_commit_unchanged': True, 'v117_identity_validator_passed': True,
        'new_configuration_count': 9, 'new_container_identities': 36, 'new_volume_identities': 9,
        'existing_environment_qualifications_all_passed': True,
        'new_api_calls': 0, 'new_Docker_operations': 0, 'ledger_rows_edited': False,
        'proposal': proposal_ref})
    print(json.dumps({'proposal': proposal_ref, 'check': check,
        'new_attempts_prepared': 9, 'new_attempts_authorized': 9, 'runtime_started': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
