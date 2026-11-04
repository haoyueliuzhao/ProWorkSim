"""Freeze a reviewable independent-recovery proposal; never authorize or run it."""
from __future__ import annotations

from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

from proworksim.software_benchmark_alignment_contract_v117 import validate_condition, validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'runs/software-benchmark-v118/project-repaired-r1'
OUTPUT = ROOT/'artifacts/software-benchmark-v121/independent-recovery-proposal-r1'
INVENTORY = ROOT/'artifacts/software-benchmark-v120/recovery-inventory-r1'
VERSION = 'v121-independent-system-failure-recovery-proposal-r1'
SEED_BASE = 20261104012100
PUBLIC_FIELDS = ('instance_id', 'repo', 'base_commit', 'problem_statement')


def read(ref):
    return json.loads(checked(ref).read_bytes())


def main():
    if OUTPUT.exists():
        raise ValueError('Do not overwrite the first independent-recovery proposal')
    hold_ref = reference(INVENTORY/'consumed-generation-hold.json')
    hold, inventory = read(hold_ref), read(reference(INVENTORY/'summary.json'))
    records = sorted(hold['rows'], key=lambda item: item['row']['slot_index'])
    if (len(records) != 27 or hold['automatic_model_resampling_authorized'] is not False
            or any(item['classification'] != 'provider_attempt_consumed'
                   or item['provider_request_count'] <= 0 for item in records)):
        raise ValueError('Include all and only the original 27 consumed model attempts')
    prior_plan_ref = reference(BATCH/'execution-plan-v119.json')
    prior_plan = read(prior_plan_ref)
    first_stage_ref = reference(BATCH/'execution-plan-v120.json')
    first_stage = read(first_stage_ref)
    expected_original = {item['row']['slot_id'] for item in records}
    if expected_original & {row['slot_id'] for row in first_stage['rows']} or len(first_stage['rows']) != 23:
        raise ValueError('The independent recovery cannot overlap the 23 first-call continuation rows')
    condition_ref = reference(BATCH/'conditions/PROJECT.json')
    condition = read(condition_ref)
    validate_condition(condition)
    runtime_source_ref = reference(BATCH/'runtime-sources-v120.json')
    runtime_bundle_ref = reference(ROOT/'runs/software-benchmark-v120/sdk-bundle-r1/manifest.json')
    new_rows, mapping, configs, resources, public_tasks, environments = [], [], {}, {}, [], {}
    old_seeds = {row['seed'] for row in prior_plan['rows']}
    old_ids = {row['slot_id'] for row in prior_plan['rows']}
    absent = []
    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT/'configs').mkdir()
    for offset, held in enumerate(records):
        old = held['row']
        if prior_plan['rows'][old['task_index']] != old:
            raise ValueError('The held original row differs from its frozen plan')
        source = read(old['configuration'])
        index, seed = 8500+offset, SEED_BASE+offset
        slot = f"v117:{old['instance_id']}:{old['condition_id']}:{seed}"
        if seed in old_seeds or slot in old_ids:
            raise ValueError('Independent recovery must have a new identity and bookkeeping seed')
        original_result = read(held['original_result'])
        if original_result['slot_id'] != old['slot_id'] or original_result['status'] != 'technical_unknown':
            raise ValueError('Do not replace or silently relabel the original stopped attempt')
        row = {**copy.deepcopy(old), 'logical_index': offset+1, 'slot_index': index,
            'slot_id': slot, 'seed': seed, 'replicate': 1, 'repeat_index': 1,
            'provider_seed_sent': False, 'panel_kind': 'independent_system_failure_recovery_27',
            'analysis_endpoint': 'independent_recovery_v121',
            'original_slot_id': old['slot_id'], 'original_slot_index': old['slot_index'],
            'old_result_overwritten': False, 'execution_authorized': False}
        validate_plan_identity(row)
        config = {**copy.deepcopy(source),
            **{key: row[key] for key in ('logical_index', 'slot_index', 'slot_id', 'seed', 'replicate',
                                        'repeat_index', 'panel_kind')},
            'version': 'v121-independent-recovery-configuration-proposal-r1',
            'preparation_only': True, 'execution_authorized': False,
            'analysis_endpoint': 'independent_recovery_v121',
            'independent_recovery': {'original_row': old, 'original_result': held['original_result'],
                'provider_attempts_already_consumed': held['provider_request_count'],
                'original_accounting_retained': True, 'original_attempt_overwritten': False,
                'resume_original_conversation': False, 'reuse_old_worktree_or_feedback': False},
            'runtime_reuse_proposal': {'target_execution_layer': 'v120',
                'frozen_existing_sources': runtime_source_ref, 'frozen_existing_bundle': runtime_bundle_ref,
                'v121_scope_manager_and_qualification_bindings_implemented': False,
                'this_proposal_is_not_a_deployed_runtime': True}}
        if config['public_task'] != source['public_task'] or set(config['public_task']) != set(PUBLIC_FIELDS):
            raise ValueError('Only the unchanged public task may enter the actor')
        row['configuration'] = write_new(OUTPUT/'configs'/f'{index}.json', config)
        configs[str(index)] = row['configuration']
        new_rows.append(row)
        public_tasks.append({key: source['public_task'][key] for key in PUBLIC_FIELDS})
        qualification_ref = reference(BATCH/'grading-coordinator-v119/qualifications'/(old['instance_id']+'.json'))
        qualified = read(qualification_ref)
        if qualified['instance_id'] != old['instance_id'] or qualified.get('passed') is not True:
            raise ValueError('Independent recovery requires completed original environment qualification')
        environments[old['instance_id']] = {'proposed_configuration': row['configuration'],
            'qualified_existing_configuration': prior_plan['environments'][old['instance_id']]['configuration'],
            'qualification': qualification_ref, 'qualification_plan': prior_plan_ref,
            'fresh_gold_empty_controls_proposed': 0,
            'future_runtime_rebinding_and_exact_equivalence_check_required': True}
        mapping.append({'instance_id': old['instance_id'], 'original_slot_id': old['slot_id'],
            'original_slot_index': old['slot_index'], 'original_seed': old['seed'],
            'original_result': held['original_result'], 'new_slot_id': slot,
            'new_slot_index': index, 'new_seed': seed, 'provider_seed_sent': False,
            'new_configuration_proposal': row['configuration'],
            'old_provider_calls': held['provider_request_count'],
            'old_settled_cost_nanoyuan': held['settled_cost_nanoyuan'],
            'old_unresolved_reservation_nanoyuan': held['unresolved_reservation_nanoyuan']})
        for role in ('actor', 'controller', 'volume', 'score', 'delivery_score'):
            prefix = 'delivery-score' if role == 'delivery_score' else role
            old_key, new_key = f'{prefix}-{old["slot_index"]}', f'{prefix}-{index}'
            resource = copy.deepcopy(prior_plan['resources'][old_key])
            resource.update(slot_id=slot, proposal_only=True, execution_authorized=False)
            resources[new_key] = resource
            for path in (BATCH/'resource-claims'/(new_key+'.json'),
                         BATCH/'episodes'/str(index)):
                if path.exists():
                    raise ValueError('A proposed physical identity already exists: '+str(path))
                absent.append(str(path))
    assert len(new_rows) == len(public_tasks) == len(environments) == 27
    assert len({row['slot_id'] for row in new_rows}) == 27
    assert len({row['seed'] for row in new_rows}) == 27
    assert {row['original_slot_id'] for row in new_rows} == expected_original
    roles = dict(Counter(resource['role'] for resource in resources.values()))
    assert roles == {'actor': 27, 'controller': 27, 'volume': 27, 'score': 27, 'delivery_score': 27}
    panel_ref = write_new(OUTPUT/'panel.json', {'version': VERSION,
        'status': 'proposal_only_not_authorized', 'selection': 'All 27 provider-called technical-unknown attempts in the frozen hold inventory; no score-based selection',
        'source_inventory': hold_ref, 'planned_distinct_tasks': 27, 'planned_new_generations': 27,
        'model': 'deepseek-flash', 'thinking': False, 'arm': 'PROJECT', 'single_agent': True,
        'condition': condition_ref, 'task_ids': [row['instance_id'] for row in new_rows],
        'repository_counts': dict(Counter(task['repo'] for task in public_tasks)),
        'rows': new_rows, 'public_tasks': public_tasks, 'actor_public_fields': list(PUBLIC_FIELDS),
        'seed_base': SEED_BASE, 'seed_rule': 'base + original held-task order offset 0..26',
        'provider_seed_sent': False, 'provider_seed_reproducibility_claim': False,
        'independent_initial_states': True, 'old_worktrees_feedback_or_conversations_reused': False,
        'original_results_overwritten': False, 'new_model_calls_authorized': 0,
        'runtime_authorized_by_this_file': False})
    mapping_ref = write_new(OUTPUT/'original-to-recovery.json', {'version': VERSION, 'rows': mapping})
    resources_ref = write_new(OUTPUT/'resource-identities.json', {'version': VERSION,
        'resources': resources, 'resource_role_counts': roles, 'planned_new_containers': 108,
        'planned_new_named_volumes': 27, 'physical_identity_range': [8500, 8526],
        'runtime_object_IDs_assigned': False, 'scope_implementation_created': False,
        'physical_keys_absent_at_preparation': sorted(set(absent))})
    environments_ref = write_new(OUTPUT/'environment-bindings.json', {'version': VERSION,
        'environments': environments, 'CA_profile': reference(BATCH/'recovery-v116/ca-profile.json')
            if (BATCH/'recovery-v116/ca-profile.json').exists()
            else reference(ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'),
        'network_resolution': reference(BATCH/'network-resolution.json'),
        'fresh_controls': 0, 'new_diagnostics': 0, 'new_neutral_API_calls': 0})
    budgets = {'model_input_plus_output_tokens_per_episode': 5_000_000,
        'new_generation_token_upper_bound': 135_000_000, 'upper_bound_is_expected_consumption': False,
        'cumulative_API_cap_CNY': '350.00', 'additional_API_cash': '0',
        'ledger_path': inventory['ledger_snapshot']['path'],
        'known_remaining_before_v120_first_generation_stage_CNY': '179.63993376',
        'balance_evidence': reference(INVENTORY/'summary.json'),
        'current_or_future_remaining_balance_claimed': False,
        'must_read_remaining_cash_after_v120_cleanup': True,
        'old_settled_and_uncertain_reservations_retained': True,
        'cash_cap_guarantees_completion_of_all_27': False,
        'on_cash_exhaustion': 'Stop new dispatch, preserve partial/unknown results; no automatic cap increase'}
    runtime = {'maximum_generation_pairs': 16, 'maximum_graders': 2,
        'maximum_combined_reserved_CPU': 112, 'maximum_combined_reserved_memory_GiB': 576,
        'maximum_NEW_containers': 108, 'maximum_NEW_named_volumes': 27,
        'actor_per_container': {'CPU': 4, 'memory_GiB': 16},
        'controller_per_container': {'CPU': 2, 'memory_GiB': 16},
        'grader_per_container': {'CPU': 4, 'memory_GiB': 16},
        'coordinator': {'CPU': 8, 'memory_GiB': 32, 'new_owner_parallel_to_v120': False,
                        'proposed_existing_user_unit': 'proworksim-v118-project.service'},
        'container_network': 'none', 'cap_drop': ['ALL'], 'privileged': False,
        'host_bind_mounts': False, 'published_host_ports': False, 'GPU': False,
        'host_configuration_mount_network_driver_or_daemon_changes': False,
        'only_new_owned_objects_managed': True,
        'private_Request_grading_capabilities': {
            'psf__requests-2931': ['NET_ADMIN'], 'psf__requests-1921': ['NET_ADMIN', 'NET_BIND_SERVICE']},
        'TLS_scoring_task': 'psf__requests-1921', 'maximum_new_TLS_sessions': 2,
        'per_TLS_session_connection_limit': 512, 'per_TLS_session_application_payload_MiB': 64,
        'maximum_new_TLS_connections': 1024, 'maximum_new_TLS_application_payload_MiB': 128,
        'TLS_destination': 'Same frozen httpbin.org public IP, ports 80/443; strict certificate/hostname verification',
        'TLS_jobs_serialized_inside_two_grading_lanes': True,
        'actor_external_network_or_answer_search': False,
        'model_API_route': 'Direct official DeepSeek TLS through existing trusted broker; no proxy',
        'public_HTTP_fixture': 'Existing private actor loopback only; no host listener',
        'cumulative_resource_accounting': {
            'historical_container_conservative_upper_bound': 70,
            'v120_first_generation_maximum_containers': 92,
            'this_recovery_maximum_containers': 108,
            'cumulative_maximum_containers': 270, 'previous_cumulative_authority_ceiling': 304,
            'historical_containers_70_claimed_as_actual_creations': False,
            'historical_named_volumes': 33, 'v120_maximum_named_volumes': 23,
            'this_recovery_maximum_named_volumes': 27, 'cumulative_maximum_named_volumes': 83,
            'resource_totals_are_lifecycle_counts_not_simultaneous_objects': True}}
    gates = {'explicit_user_authorization_for_27_NEW_model_attempts_required': True,
        'explicit_scope_for_future_Docker_and_owner_operations_required': True,
        'v120_first_generation_stage_must_be_final': True,
        'v120_pending_generation_and_grading_jobs_must_equal_zero': True,
        'v120_retained_objects_active_claims_and_owner_leases_must_equal_zero': True,
        'v120_all_owned_cleanup_evidence_required': True,
        'no_two_API_owners_simultaneously': True,
        'source_and_scoring_qualification_rebinding_must_be_frozen_before_launch': True,
        'new_prepared_manifest_must_match_final_runtime_source': True,
        'all_old_27_results_bills_and_uncertain_reservations_retained': True,
        'model_or_scoring_exception_isolated_without_retry': True,
        'shared_integrity_or_unknown_cleanup_stops_new_dispatch': True,
        'current_predecessor_gate_satisfied': False,
        'no_automatic_launch_after_predecessor_finishes': True}
    metrics = {'new_results_endpoint': 'independent_recovery_v121',
        'old_technical_unknown_results_overwritten': False,
        'resume_or_replay_original_conversation_claim': False,
        'original_primary_attempt_success_rate_replaced': False,
        'best_of_old_and_new_candidates_selected': False,
        'code_and_legal_delivery_scored_separately': True,
        'report_per_task_and_group_actual_input_output_cache_and_total_tokens': True,
        'report_mean_denominator_and_partial_usage_lower_bounds': True,
        'bill_old_and_new_requests_once_each': True,
        'combine_with_23_first_calls_only_under_an_explicit_repaired_protocol_label': True}
    proposal = {'version': VERSION, 'status': 'awaiting_specific_user_authorization',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'One independent new attempt for every one of the 27 previously called tasks stopped by systemic tool-argument comparison failure',
        'panel': panel_ref, 'original_to_recovery': mapping_ref, 'resource_identities': resources_ref,
        'environment_bindings': environments_ref, 'configuration_proposals': configs,
        'proposed_model': 'deepseek-flash', 'thinking': False, 'condition': condition_ref,
        'proposed_execution_layer_reuse': {'version': 'v120', 'sources': runtime_source_ref,
            'bundle': runtime_bundle_ref, 'v121_implementation_deployed': False,
            'v121_scope_manager_or_authorization_created': False},
        'runtime_limits': runtime, 'generation_and_cash_budget': budgets, 'launch_gates': gates,
        'reporting_contract': metrics, 'preceding_23_task_plan': first_stage_ref,
        'no_outcome_based_task_selection': True, 'no_new_controls_diagnostics_or_neutral_calls': True,
        'current_authorization': {'approved': False, 'new_model_attempts': 0,
            'new_Docker_objects': 0, 'new_services': 0, 'new_cash': 0},
        'preparation_operations': {'API_calls': 0, 'model_calls': 0, 'Docker_operations': 0,
            'GPU_operations': 0, 'network_connections': 0, 'existing_files_changed': False},
        'preparation_source': reference(__file__)}
    proposal_ref = write_new(OUTPUT/'proposal.json', proposal)
    text = f'''# 27 题独立恢复提案（待授权，未运行）

对 v119 已经调用模型、因系统性接口问题停止的 **全部 27 题**，各新运行一次。题单直接来自封存库存，没有根据分数或“接近成功”挑选。这是新的独立尝试，不是原会话续接；原结果、用量和未定预约全部保留。

- **条件**：DeepSeek Flash，非思考模式，PROJECT 单 Agent，复用 v120 修复后的执行层；每题最多 500 万输入＋输出 token，27 题合计上限 **1.35 亿**。上下文 131,072、输入 98,304、单次输出最多 32,768，原调用与时间限制保持。
- **初态与身份**：恢复原公开仓库基线，不带入旧补丁、历史反馈或工作树。物理编号 8500–8526；固定新 seed 为 `{SEED_BASE}` 加 0–26，仅用于本地身份，不发送给 API，也不承诺可重复生成。新逻辑 ID 沿现有 v117 接口格式，均与旧回合不同。
- **启动顺序**：必须等待 v120 的 23 个首次生成任务结束、评分队列清空、全部本轮对象和 owner 释放，再取得本提案的明确授权。不会同时运行两个 API owner，也不会因前阶段结束而自动启动。
- **资源上限**：新增最多 **108 个容器、27 个专用卷**；最多 16 个生成 pair＋2 个评分，合计不超过 112 CPU／576 GiB。不新增环境控制、诊断或中性 API 调用；复用 v119 已通过的环境资格。只操作新建项目对象，不改变共享服务器配置。容器生命周期数量保守上界为 70＋92＋108＝**270**，低于既有累计容器上限 304；卷累计上界为 **83**。这里的旧 70 是保守计量上界，不是声称实际创建数。
- **现金**：累计 API 上限仍 **350 元**，不增额。v119 收口时已知剩余 179.63993376 元；23 题阶段继续消耗这笔余额，恢复启动前必须重新读取实际余额。原未定预约不退款或清零，不能保证现金足以完成全部 27 题。

评分沿用官方规则，分别报告代码通过与合法交付；记录每题及全组实际输入、输出、缓存、总 token 与费用。新结果单列为独立恢复，不覆盖旧技术未知，也不在旧、新候选间择优。如与 23 个首次生成结果组成修复后汇总，将明确两个来源阶段及分母。

Requests1921 的评分继续使用已冻结、严格校验证书和主机名的受限 HTTP/TLS 通道；至多 2 个新评分 session、合计 1,024 次连接／128 MiB 应用载荷。Requests2931 仍仅使用私有环境内公开 fixture。模型侧不提供联网搜索或未受管 shell。

当前已准备具体题单、27 份配置与资源身份；**没有实现或部署 v121 调度器／scope，没有创建运行授权，也没有发起模型、容器或评分**。后续仍需冻结新运行绑定并核验最终 manifest，才能按授权执行。

[完整提案](proposal.json) · [27题公开面板](panel.json) · [旧／新回合映射](original-to-recovery.json) · [资源身份](resource-identities.json) · [环境资格来源](environment-bindings.json)
'''
    (OUTPUT/'review.md').write_text(text)
    write_new(OUTPUT/'preparation-check.json', {'version': VERSION, 'passed': True,
        'all_27_original_called_rows_included': True, 'new_IDs_and_seeds_unique': True,
        'new_IDs_and_seeds_disjoint_from_original_50': True,
        'public_tasks_unchanged': True, 'existing_v117_identity_contract_validated': True,
        'new_configurations': 27, 'new_container_identities': 108, 'new_volume_identities': 27,
        'proposal': proposal_ref, 'runtime_authorized': False, 'model_calls': 0, 'Docker_operations': 0})
    print(json.dumps({'proposal': proposal_ref, 'review': str(OUTPUT/'review.md'),
        'new_attempts_proposed': 27, 'new_attempts_authorized': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
