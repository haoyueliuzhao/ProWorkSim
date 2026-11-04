"""Materialize the two explicitly approved new REF attempts; never reuse old worktrees."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import json
from proworksim import software_benchmark_scope_v126 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    proposal = scope.load(reference(scope.USER_PROPOSAL_FILE))
    panel = scope.load(proposal['panel'])
    original = scope.load(reference(scope.ORIGINAL_PLAN_FILE))
    proposed_resources = scope.load(proposal['resource_identities'])['resources']
    grant = scope.retain(scope.USER_GRANT_FILE, {'status': 'approved',
        'explicit_user_reply': '两题各新跑一次（推荐）',
        'explicit_user_instruction': '对ref的未定做分析处理',
        'proposal': reference(scope.USER_PROPOSAL_FILE),
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Two new independent REF attempts, each5M;6containers2volumes; wait for prior2first calls; existing cumulative cap only',
        'runtime_started_by_this_record': False})
    rows, resources, environments = [], {}, {}
    for candidate in panel['rows']:
        row = copy.deepcopy(candidate)
        config = scope.load(row['configuration'])
        config = {**config, 'version': 'v126-runtime-independent-REF-configuration-r1',
                  'configuration_proposal': row['configuration']}
        for key in ('preparation_only', 'execution_authorized'):
            config.pop(key, None)
            row.pop(key, None)
        row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/f"{row['slot_index']}.json", config)
        rows.append(row)
        environments[row['instance_id']] = {**original['environments'][row['instance_id']],
                                             'configuration': row['configuration']}
        for role in ('actor', 'controller', 'volume', 'score'):
            key = f"{role}-{row['slot_index']}"
            resource = copy.deepcopy(proposed_resources[key])
            resource.pop('proposal_only', None)
            resource.pop('execution_authorized', None)
            resources[key] = resource
    inventory = scope.retain(scope.INVENTORY_FILE, {'rows': rows, 'user_grant': grant,
        'original_to_recovery': proposal['original_to_recovery'], 'new_attempts': True})
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT), 'rows': rows,
        'generation_rows': rows, 'panel': reference(scope.PANEL_FILE), 'matrix': reference(scope.PANEL_FILE),
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'constraints': scope.CONSTRAINTS,
        'resources': resources, 'resource_role_counts': {'actor': 2, 'controller': 2, 'volume': 2, 'score': 2},
        'environments': environments,
        'environment_sources': {t: original['environment_sources'][t] for t in environments},
        'diagnostics': [], 'score_recoveries': [], 'original_plan': reference(scope.ORIGINAL_PLAN_FILE),
        'prior_stage_plan': reference(scope.PRIOR_PLAN_FILE), 'inventory': inventory,
        'user_grant': grant, 'dispatch_admission': declaration(scope.BATCH_ROOT),
        'old_results_preserved': True, 'old_stopped_candidates_used_as_model_input': False}
    scope.validate_plan(plan)
    plan_ref = scope.retain(scope.PLAN_FILE, plan)
    recovery = {'version': scope.VERSION, 'original_plan': reference(scope.ORIGINAL_PLAN_FILE),
        'prior_preparation_qualification': reference(scope.ORIGINAL_BATCH_ROOT/'diagnostic-1/result.json'),
        'prior_API_qualification': reference(scope.ORIGINAL_BATCH_ROOT/'api-qualification/result.json'),
        'original_to_recovery': proposal['original_to_recovery'], 'new_generation_attempts': 2,
        'old_episodes_resumed': False, 'original_records_overwritten': False,
        'new_neutral_calls': 0, 'new_diagnostics': 0, 'new_controls': 0,
        'cash_amendment': reference(scope.CASH_AMENDMENT_FILE)}
    return {'plan': plan_ref, 'recovery': scope.retain(scope.RECOVERY_FILE, recovery), 'user_grant': grant}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
