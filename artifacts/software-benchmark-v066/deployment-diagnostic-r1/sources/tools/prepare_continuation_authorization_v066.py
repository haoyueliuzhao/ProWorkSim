"""Seal only the authorized continuation of the original v064 experiment.

Preparation writes project files only. It never starts a service, container,
GPU, model request or network connection, and does not release the shared hold.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_sdk_bundle_v064 as sdk
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, BATCH = policy.ROOT, policy.BATCH_ROOT
OUT = ROOT / 'artifacts/software-benchmark-v066/runtime-authorization-r1'


def tool_module(name):
    spec = importlib.util.spec_from_file_location('v066_prepare_' + name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dependency_sources():
    old_index = policy.PREDECESSOR_ROOT / 'runtime-sources.json'
    previous = json.loads(old_index.read_bytes())
    sources = {row['path']: row for row in previous['files']}
    for item in sources.values():
        policy.checked(item)
    paths = {old_index, policy.RESUME_FILE,
        policy.PREDECESSOR_ROOT / 'coordinator/run-summary.json',
        policy.PREDECESSOR_ROOT / 'api-qualification/result.json',
        ROOT / 'artifacts/software-benchmark-v066/recovery-preparation-r1/predecessor-evidence.json'}
    paths.update((ROOT / 'src/proworksim').glob('*v066*.py'))
    paths.update((ROOT / 'tools').glob('*v066*.py'))
    for path in paths:
        sources[str(path.resolve())] = reference(path)
    return [sources[key] for key in sorted(sources)]


def prepare(*, record_user_authorization=False):
    if (policy.COORDINATOR_RUN_ROOT / 'execution-started.json').exists() or list((BATCH / 'resource-claims').glob('*.json')):
        raise ValueError('An entered continuation may not be silently resealed or replayed')
    policy.previous_runtimes_closed()
    plan = policy.create_plan()
    bundle = sdk.prepare_bundle()  # Reuse the unchanged, already-probed SDK archive.
    source_ref = policy.retain(policy.SOURCE_INDEX_FILE, {
        'version': 'v064-runtime-sources-r1', 'continuation_revision': 'v066',
        'files': dependency_sources(), 'actor_bundle': reference(sdk.OUTPUT / 'manifest.json'),
        'old_model_visible_sources_changed': False, 'shared_host_configuration_changed': False})
    coordinator = tool_module('run_full_benchmark_v066').prepare()
    unit = tool_module('launch_full_benchmark_v066').prepare()
    inventory = policy.load(reference(policy.RESUME_FILE))
    counts = plan['resource_role_counts']
    proposal = {'version': policy.VERSION, 'plan': reference(policy.PLAN_FILE),
        'continuation_inventory': reference(policy.RESUME_FILE),
        'sources': policy.sources(), 'constraints': policy.CONSTRAINTS,
        'operations': sorted(policy.OPERATIONS), 'coordinator_plan': coordinator,
        'coordinator_unit': unit, 'unchanged_SDK_archive': bundle['archive'],
        'predecessor_summary': inventory['predecessor_summary'],
        'actual_allowed_resource_counts': counts,
        'actual_new_container_upper_bound': sum(counts.get(name, 0) for name in
            ('actor', 'controller', 'score', 'delivery_score', 'control')),
        'experiment': {'original_panel_episodes': 6000, 'original_groups': 12,
            'same_tasks_seeds_model_inference_and_tool_configuration': True,
            'allowed_original_continuation_attempts': plan['remaining_generation_slots'],
            'proved_zero_generation_recovery_slots': inventory['retry_zero_generation'],
            'remaining_original_token_upper_bound': plan['remaining_original_token_upper_bound'],
            'original_API_total_cash_cap_CNY': '1500.00',
            'API_ledger': str(policy.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'),
            'new_API_qualification_calls': 0, 'new_API_metadata_calls': 0,
            'old_entered_model_attempts_replayed': False, 'old_results_overwritten': False,
            'v065_organization_evaluations_started': False},
        'deployment_revision': {'controller_memory_GiB': 16,
            'actor_plus_controller_reserved_GiB': 32,
            'combined_cpu_limit': 152, 'combined_memory_GiB': 832,
            'concurrency_falls_when_combined_capacity_requires': True,
            'qwen_host_request_journal_before_forwarding': True,
            'local_technical_failures_do_not_stop_other_episodes': True,
            'API_provider_pause_does_not_stop_Qwen': True,
            'global_stop_retained_for_shared_integrity_or_unproven_cleanup': True},
        'authorization_basis': {
            'user_request': '处理并恢复实验，此外健壮度太差，因为这么一个小问题就导致12组实验全部停止',
            'original_batch_request': '完整500题，500万/750万/1000万，REF和PROJECT，本地Qwen和DeepSeek，共十二组，本轮实验开放权限',
            'original_API_budget_reply': '1500', 'original_API_thinking_reply': '采用思考模式'},
        'boundaries': {'owned_new_objects_only': True, 'actor_controller_network_none': True,
            'no_host_directory_binds_or_privileged_containers': True,
            'same_predeclared_Requests_grading_network_only': True,
            'no_shared_mount_network_driver_daemon_linger_or_existing_service_changes': True,
            'ordinary_user_model_and_coordinator_units_only': True,
            'shared_incident_hold_released': False},
        'runtime_operations_in_preparation': 0}
    OUT.mkdir(parents=True, exist_ok=True)
    proposal_ref = policy.retain(OUT / 'proposal.json', proposal)
    auth = {'version': policy.VERSION, 'status': 'approved' if record_user_authorization else 'pending',
        'automatic_release': False, 'constraints': policy.CONSTRAINTS,
        'plan': reference(policy.PLAN_FILE), 'proposal': proposal_ref, 'sources': policy.sources(),
        'explicit_rootful_authorization': (
            '用户明确要求处理并恢复已授权的12组评测；只按本提案建立续跑专属隔离容器/专用卷及普通用户模型/调度服务，'
            '不修改共享服务器或既有服务。保留原6000逻辑身份和1500元唯一API账本，不自动重采已入模型回合。'
            if record_user_authorization else None),
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'shared_incident_hold_released': False}
    if policy.AUTHORIZATION_FILE.exists():
        raise ValueError('An existing continuation grant cannot be silently replaced')
    saved = write_new(OUT / ('approved-authorization.json' if record_user_authorization else 'pending-authorization.json'), auth)
    atomic_write(policy.AUTHORIZATION_FILE, json_bytes(auth))
    return {'proposal': proposal_ref, 'authorization': saved, 'source_index': source_ref,
            'remaining_original_slots': plan['remaining_generation_slots'], 'runtime_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-user-authorization', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(record_user_authorization=args.record_user_authorization), ensure_ascii=False))
