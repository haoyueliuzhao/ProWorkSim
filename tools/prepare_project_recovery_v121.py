"""Materialize exactly the user-approved independent attempts, without execution."""
import copy
import json
from proworksim import software_benchmark_scope_v121 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    proposal = scope.load(reference(scope.USER_PROPOSAL_FILE))
    panel = scope.load(proposal['panel'])
    prior_ref = reference(scope.PRIOR_BATCH_ROOT/'execution-plan-v119.json')
    prior = scope.load(prior_ref)
    rows, resources, environments, environment_sources = [], {}, {}, {}
    proposed_resources = scope.load(proposal['resource_identities'])['resources']
    for original in panel['rows']:
        row = copy.deepcopy(original)
        row.pop('execution_authorized', None)
        config = scope.load(row['configuration'])
        config = {**config, 'version': 'v121-private-independent-recovery-config-r1',
                  'source_configuration_proposal': row['configuration']}
        for key in ('execution_authorized', 'preparation_only', 'runtime_reuse_proposal'):
            config.pop(key, None)
        row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/f"{row['slot_index']}.json", config)
        rows.append(row)
        task = row['instance_id']
        environments[task] = {**prior['environments'][task], 'configuration': row['configuration']}
        environment_sources[task] = copy.deepcopy(prior['environment_sources'][task])
        for role in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            key = f"{role}-{row['slot_index']}"
            resource = copy.deepcopy(proposed_resources[key])
            resource.pop('proposal_only', None)
            resource.pop('execution_authorized', None)
            resources[key] = resource
    inventory = scope.retain(scope.INVENTORY_FILE, {'version': scope.VERSION,
        'rows': rows, 'user_grant': reference(scope.USER_GRANT_FILE),
        'held_original_inventory': reference(scope.HELD_INVENTORY_FILE),
        'new_attempts': True, 'original_attempts_resumed': False})
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT), 'rows': rows,
        'panel': reference(scope.PANEL_FILE), 'matrix': reference(scope.PANEL_FILE),
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'inventory': inventory,
        'constraints': scope.CONSTRAINTS, 'environments': environments,
        'environment_sources': environment_sources, 'resources': resources,
        'resource_role_counts': {'actor': 27, 'controller': 27, 'volume': 27,
                                 'score': 27, 'delivery_score': 27},
        'diagnostics': [], 'historical_results_preserved': True, 'training': False,
        'model_calls_during_preparation': 0, 'new_runtime_scope': True,
        'system_parent_slice_required': False, 'prior_plan': prior_ref,
        'original_panel_plan': reference(scope.ORIGINAL_PLAN_FILE),
        'user_grant': reference(scope.USER_GRANT_FILE),
        'authorized_proposal': reference(scope.USER_PROPOSAL_FILE),
        'independent_recovery': True, 'old_results_preserved': True,
        'prior_stage_must_complete': reference(scope.PRIOR_PLAN_FILE),
        'dispatch_admission': declaration(scope.BATCH_ROOT)}
    scope.validate_plan(plan)
    plan_ref = scope.retain(scope.PLAN_FILE, plan)
    recovery = {'version': scope.VERSION, 'user_grant': reference(scope.USER_GRANT_FILE),
        'proposal': reference(scope.USER_PROPOSAL_FILE), 'prior_plan': reference(scope.PRIOR_PLAN_FILE),
        'prior_API_root': str(scope.PRIOR_API_ROOT),
        'prior_preparation_qualification': reference(scope.PRIOR_BATCH_ROOT/'api-coordinator-v119/preparation-qualification.json'),
        'prior_API_qualification': reference(scope.PRIOR_BATCH_ROOT/'api-qualification/result.json'),
        'original_to_recovery': proposal['original_to_recovery'], 'new_generation_attempts': 27,
        'new_tokens_upper_bound': 135_000_000, 'old_episodes_resumed': False,
        'original_records_overwritten': False, 'new_neutral_calls': 0,
        'new_diagnostic_pairs': 0, 'new_controls': 0, 'new_containers': 108,
        'new_volumes': 27, 'must_wait_for_prior_completion': True,
        'prior_completion_file': str(scope.PRIOR_COMPLETION_FILE), 'additional_cash': 0}
    return {'plan': plan_ref, 'recovery': scope.retain(scope.RECOVERY_FILE, recovery)}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
