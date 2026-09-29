"""Read-only R1 report: old failed costs, exact-window restoration and new work.

Never replay, rescore, load weight tensors or overwrite the original v025 report.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts.composition_evidence_v025 import checked, endpoint
from scripts.report_domain_v022 import calls, read, reference, resources
from scripts.report_learning_v023 import auxiliary, index_progress, outcome

VERSION = 'member-composition-recovery-report-v0.25-R1'
STAGES = ('train_base', 'confirm_base', 'next_base')
CAPS = {'train_base': 72000, 'confirm_base': 16200, 'next_base': 3600}


def same_ref(a, b):
    return isinstance(a, dict) and isinstance(b, dict) and a.get('path') == b.get('path') and a.get('sha256') == b.get('sha256')


def terminal(state, supervisor_closed):
    if state.get('attempted') is False:
        return supervisor_closed and state.get('ended_at') is not None
    return (state.get('status') in {'complete', 'stopped', 'failed', 'supervisor_error'}
            and state.get('ended_at') is not None and state.get('exit_code') is not None)


def validate_catalog(catalog):
    slots, cases = catalog['confirmation_slots'], catalog['confirmation_cases']
    if (len(slots) != 12 or len(cases) != 6 or len({c['case_id'] for c in cases}) != 6
            or Counter(c['task'] for c in cases) != Counter(joint_a=2, joint_b=2, maintenance=2)
            or len({s['slot_id'] for s in slots}) != 12 or len({(s['case_id'], s['seed']) for s in slots}) != 12):
        raise ValueError('R1 must retain the exact twelve original confirmation slots')
    for case in cases:
        repeats = [s for s in slots if s['case_id'] == case['case_id']]
        if len(repeats) != 2 or {s['repeat_index'] for s in repeats} != {0, 1} or any(s['seed'] != s['sampling_seed'] for s in repeats):
            raise ValueError('Confirmation retains two fixed repeats of each original situation')
    if (len(catalog['continuation_slots']) != 2 or len(catalog['training_window']['slots']) != 16
            or Counter(s['task'] for s in catalog['training_window']['slots']) != Counter(joint_a=8, joint_b=8)):
        raise ValueError('R1 is sixteen old support records plus two new continuation slots')


def original_evidence(plan):
    root = Path(plan['original_run']).resolve()
    supervisor = read_json(checked(plan['original_supervisor']))
    old_report = read_json(checked(plan['original_report']))
    old_plan = read_json(checked(plan['original_plan']))
    common = read_json(checked(plan['original_support_complete']))
    if (Path(old_report['run_root']).resolve() != root or old_report.get('execution_terminal') is not True
            or old_report.get('source') != supervisor.get('source') or common.get('source') != supervisor.get('source')
            or not same_ref(supervisor['plan'], plan['original_plan'])
            or not same_ref(old_report['references']['plan'], plan['original_plan'])
            or not same_ref(old_report['references']['supervisor'], plan['original_supervisor'])
            or not same_ref(plan['catalog'], old_report['references']['catalog'])
            or not supervisor.get('ended_at')):
        raise ValueError('Original run/source/terminal report binding differs')
    support = read_json(checked(common['support']))
    entries = read_json(checked(common['entries']))
    original_admission = read_json(root/'train_base/actual/update/admission.json')
    if (support.get('selected_block') is not None or old_report.get('support', {}).get('selected_block') is not None
            or len(entries) != 16 or original_admission.get('slot_count') != 16
            or len(original_admission.get('decisions', [])) != 283):
        raise ValueError('This R1 is only the original no-supported-block sixteen-slot/283-decision window')
    # No new interpretation of old failure labels or incomplete counters.
    cost = old_report['accounting'].get('final_gpu_seconds')
    if (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0
            or not math.isclose(cost, supervisor.get('terminated_gpu_seconds', -1), rel_tol=0, abs_tol=1e-6)):
        raise ValueError('Original closed cost must remain an actual finite quantity')
    for name in ('confirm_base', 'next_base'):
        if read(root/name/'actual/progress.json', []) or read(root/name/'actual/collection/progress.json', []):
            raise ValueError('R1 cannot relabel already executed old confirmation/continuation as new')
    return {'run_root': str(root), 'source': supervisor['source'], 'report_kind': old_report['report_kind'],
            'original_failed_gpu_seconds': cost, 'original_budget_accounting': old_report['accounting'],
            'original_support_episode_count': len(entries), 'original_admitted_decisions': len(original_admission['decisions']),
            'support': support, 'support_complete': common,
            'prior_training_consumptions_started': old_report['training_episode_consumptions_started'],
            'closed_new_episode_counts': old_report['closed_new_episode_counts'],
            'new_actor_steps_last_reported': old_report['new_actor_steps'],
            'new_critic_steps_last_reported': old_report['new_critic_steps'],
            'references': {key: plan[key] for key in ('original_supervisor', 'original_report', 'original_plan', 'original_support_complete')},
            'old_plan_nominal_gpu_seconds': old_plan['internal_gpu_seconds']}


def closed_episode_count(folder, slots):
    count = 0
    for slot in slots:
        manifest = read(folder/slot['slot_id']/'episode/manifest.json')
        if manifest and manifest.get('status') == 'closed':
            if manifest.get('scenario', {}).get('variation', {}).get('online_case', {}).get('case_id') != slot['case_id']:
                raise ValueError('A new closed episode boundary differs from its planned case')
            count += 1
    return count


def confirmation(root, catalog, actor):
    folder = root/'confirm_base/actual'
    progress = read(folder/'progress.json', [])
    by_id = index_progress(progress, catalog['confirmation_slots'])
    states, rows = {}, []
    for slot in catalog['confirmation_slots']:
        row = by_id.get(slot['slot_id'])
        if row and row.get('assessment_ref'):
            if read_json(checked(row['assessment_ref'])) != row.get('assessment'):
                raise ValueError('R1 saved assessment changed from its referenced original bytes')
        if row and row.get('status') == 'closed':
            preparation = read(folder/slot['slot_id']/'preparation.json', {})
            if (not row.get('assessment_ref')
                    or preparation.get('prepared_business_state_sha256') != row.get('initial_business_state_sha256')
                    or preparation.get('prepared_business_state_hash_format') != 'canonical-keys-v025-all-original-business-fields-and-immutable-file-bytes'):
                raise ValueError('R1 confirmation initial state is not its actual canonical v025 preparation')
        value = row.get('initial_business_state_sha256') if row else None
        if value and states.setdefault(slot['case_id'], value) != value:
            raise ValueError('Two repeats changed the declared initial situation')
        result = outcome(row, actor)
        rows.append({**slot, 'outcome': result, 'initial_business_state_sha256': value,
                     'assessment_reference': row.get('assessment_ref') if row else None,
                     'auxiliary': auxiliary(row.get('assessment', {}) if row else {}, trusted=result['known'], task=slot['task'])})

    def totals(items):
        known = sum(x['outcome']['known'] for x in items)
        completed = sum(x['outcome']['value'] is True for x in items)
        return {'planned': len(items), 'known': known, 'unknown': len(items)-known,
                'complete_responsibilities': completed, 'completed_fraction': completed/len(items) if known == len(items) else None,
                'descriptive_known_fraction': completed/known if known else None}

    cases = {c['case_id']: c for c in catalog['confirmation_cases']}
    groups = {}
    for row in rows:
        case = cases[row['case_id']]
        label = (row['task'] if row['task'] == 'joint_a' else
                 'joint_b_' + case['prepared_submission'] if row['task'] == 'joint_b' else
                 'maintenance_changed' if case['maintenance']['expected_result_change'] else 'maintenance_unchanged')
        groups.setdefault(label, []).append(row)
    return {**totals(rows), 'rows': rows, 'started_progress_rows': len(progress),
            'closed_new_episode_boundaries': closed_episode_count(folder, catalog['confirmation_slots']), 'structures': {t: totals([r for r in rows if r['task'] == t]) for t in ('joint_a', 'joint_b', 'maintenance')},
            'business_conditions': {label: totals(items) for label, items in groups.items()},
            'no_before_checkpoint_observations': True, 'parameter_learning_effect': None,
            'interpretation': 'One recovered F0 endpoint on the twelve originally unexecuted confirmation slots. Counts are descriptive, not a paired parameter-gain or configured-versus-base estimate.'}


def restoration_evidence(root, original, recovery_binding):
    path = root/'train_base/actual/restoration-proof.json'
    proof = read(path)
    if proof is None:
        return {'available': False, 'qualified': None, 'reference': None, 'proof': None}
    if proof.get('version') != 'same-unstepped-composition-recovery-v0.25-R1' or Path(proof.get('original_run', '')).resolve() != Path(original['run_root']):
        raise ValueError('Restoration proof binds a different recovery or original run')
    for ref in proof['inputs'].values():
        checked(ref)
    no_step, restore = proof['no_step_proof'], proof['restoration']
    admission, comp = proof['admission_reconstruction'], proof['composition_reconstruction']
    qualified = (proof.get('original_source') == original['source']
        and no_step.get('admitted') is True and no_step.get('worker_original_identity_dead') is True
        and no_step.get('optimizer_steps_this_attempt') == 0
        and no_step.get('scheduled_decisions') == 283
        and restore.get('exact_state_restored') is True
        and restore.get('state_tensor_digest') == restore.get('restored_state_tensor_digest')
        and bool(restore.get('state_tensor_digest'))
        and restore.get('actor_steps_before_window') == 2 and restore.get('critic_steps_before_window') == 2
        and restore.get('partial_gradients_reused') is False and restore.get('new_training_model_calls') == 0
        and restore.get('begin_window_called') is False
        and set(restore.get('restored_components', [])) == {'actor', 'critic', 'actor_optimizer', 'critic_optimizer', 'CPU/CUDA RNG'}
        and admission.get('exactly_equal') is True and admission.get('scheduled_slots') == 16
        and admission.get('admitted_decisions') == 283
        and admission.get('sha256') == proof['inputs']['admission']['sha256']
        and same_ref(admission.get('original'), proof['inputs']['admission'])
        and comp.get('exactly_equal') is True and comp.get('all_unit_weights') is True
        and math.isclose(proof.get('original_total_gpu_seconds', -1), original['original_failed_gpu_seconds'], rel_tol=0, abs_tol=1e-6))
    checked(restore['new_checkpoint'])
    if not same_ref(proof['inputs']['entries'], original['support_complete']['entries']):
        raise ValueError('Restoration uses a different raw support collection')
    if recovery_binding and recovery_binding.get('inputs') and proof['inputs'] != recovery_binding['inputs']:
        raise ValueError('Restoration input references changed from the frozen R1 binding')
    return {'available': True, 'qualified': bool(qualified), 'reference': reference(path), 'proof': proof,
            'scope': 'Saved exact-state restoration and original no-step proof. Reporter hashes referenced bytes, never loads tensors or inspects a terminated live model.'}


def report(root):
    root = Path(root).resolve()
    supervisor = read_json(root/'supervisor.json')
    plan = read_json(checked(supervisor['plan']))
    if plan.get('internal_gpu_seconds') != sum(CAPS.values()):
        raise ValueError('R1 requires its new exact 25.5 GPU-hour budget')
    original = original_evidence(plan)
    catalog = read_json(checked(plan['catalog']))
    validate_catalog(catalog)
    source = supervisor['source']
    closed = bool(supervisor.get('ended_at')) and supervisor.get('status') in {'complete', 'closed_with_incomplete_stages', 'supervisor_error'}
    stages, costs = {}, {}
    for name in STAGES:
        folder = root/name
        state, worker = read(folder/'state.json', {}), read(folder/'actual/report.json', {})
        for field in ('source_before', 'source_after'):
            if worker.get(field) not in (None, source):
                raise ValueError('R1 worker source differs from the new frozen supervisor')
        ended = terminal(state, closed)
        elapsed = state.get('elapsed_gpu_seconds')
        if elapsed is not None and (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0):
            raise ValueError('R1 stage cost must be nonnegative and finite')
        costs[name] = elapsed if ended and elapsed is not None else 0 if ended and state.get('attempted') is False else None
        stages[name] = {'terminal': ended, 'state': state, 'worker_status': worker.get('status'),
            'worker_source_unchanged': worker.get('source_unchanged'), 'worker_error': worker.get('error'),
            'actual_final_actor_identity': worker.get('final_actor_identity'),
            'resources': resources(folder/'resources.jsonl', state), 'resident_calls': calls(folder/'actual'),
            'references': {name: reference(folder/name) for name in ('state.json', 'actual/report.json', 'model.log')}}
    execution_terminal = closed and all(s['terminal'] for s in stages.values())
    restored = restoration_evidence(root, original, plan.get('recovery'))
    end = endpoint(root, 'base', source)
    train_folder = root/'train_base/actual'
    update = read(train_folder/'update/report.json', {})
    admission = read(train_folder/'update/admission.json')
    comp = read(train_folder/'update/composition-admission.json')
    losses = read(train_folder/'update/losses.json')
    saved = end.get('saved_metadata', {})
    original_admission_equal = None
    original_composition_equal = None
    if restored['available']:
        refs = restored['proof']['inputs']
        original_admission_equal = (reference(train_folder/'update/admission.json')['sha256'] == refs['admission']['sha256']
                                    if admission is not None else None)
        original_composition_equal = (reference(train_folder/'update/composition-admission.json')['sha256'] == refs['composition_admission']['sha256']
                                      if comp is not None else None)
    unit = None
    if comp is not None:
        unit = (comp.get('Q_equals_B') is True and not comp.get('changed_blocks')
                and comp.get('original_normalization_preserved') is True
                and len(comp.get('rows', [])) == 283 and all(r['weight'] == 1 for r in comp['rows']))
    rows_match = None
    if losses is not None and comp is not None:
        def ids(row):
            return row['slot_id'], row['member_id'], row['call_id']
        rows_match = (len(losses) == 283 and [ids(r) for r in losses] == [ids(r) for r in comp['rows']]
                      and all(r.get('composition_weight') == 1 for r in losses))
    train_complete = (restored['qualified'] is True and unit is True and rows_match is True
        and original_admission_equal is True and original_composition_equal is True
        and update.get('status') == 'updated' and update.get('actor_optimizer_steps') == 1 and update.get('critic_optimizer_steps') == 1
        and update.get('backward_decisions_completed') == 283
        and saved.get('actor_steps') == 3 and saved.get('critic_steps') == 3
        and saved.get('actor_identity') == update.get('after_actor_identity'))
    confirm = confirmation(root, catalog, end['actor_identity'])
    next_folder = root/'next_base/actual'
    continuation_rows = read(next_folder/'collection/progress.json', [])
    index_progress(continuation_rows, catalog['continuation_slots'])
    guard = read(next_folder/'state-guard.json')
    next_complete = (len(continuation_rows) == 2 and all(r.get('status') == 'closed' for r in continuation_rows)
                     and guard and guard.get('learning_unchanged') is True and guard.get('rng_restored_exactly') is True)
    protocol = bool(execution_terminal and train_complete and confirm['known'] == 12 and next_complete
        and all(s['state'].get('status') == 'complete' and s['worker_status'] == 'complete'
                and s['worker_source_unchanged'] is True for s in stages.values())
        and all(stages[s]['actual_final_actor_identity'] == end['actor_identity'] for s in ('confirm_base', 'next_base')))
    new_cost = math.fsum(costs.values()) if execution_terminal and all(v is not None for v in costs.values()) else None
    known_cost = math.fsum(v for v in costs.values() if v is not None)
    continuation_closed = closed_episode_count(next_folder/'collection', catalog['continuation_slots'])
    return {'version': VERSION, 'generated_at_epoch': time.time(), 'run_root': str(root), 'source': source,
        'report_kind': 'closed_no_supported_block_recovery_complete' if protocol else 'closed_incomplete' if execution_terminal else 'snapshot',
        'execution_terminal': execution_terminal, 'recovery_protocol_complete': protocol,
        'planned_primary_composition_difference': None, 'parameter_learning_effect': None,
        'primary_reason': 'The original window has no supported reconfigurable block, no configured branch, and no pre-update observations of these confirmation slots. R1 provides a recovered F0 and descriptive new work only.',
        'original': original, 'restoration': restored, 'endpoint': end,
        'training': {'complete': bool(train_complete), 'update': update,
            'original_training_episodes_reused': 16, 'new_training_episodes_sampled': 0,
            'scheduled_decisions_to_recompute': 283, 'actual_backward_decisions_completed': update.get('backward_decisions_completed'),
            'raw_episode_consumptions_this_recovery_started': 16 if admission is not None else 0,
            'all_composition_weights_are_one': unit, 'actual_losses_match_composition_rows': rows_match,
            'actual_update_admission_equals_original_bytes': original_admission_equal,
            'actual_composition_admission_equals_original_bytes': original_composition_equal,
            'new_actor_steps': update.get('actor_optimizer_steps') if train_complete else None,
            'new_critic_steps': update.get('critic_optimizer_steps') if train_complete else None,
            'partial_persisted_counts_are_terminal': bool(train_complete),
            'references': {name: reference(train_folder/name) for name in ('restoration-proof.json', 'update/report.json', 'update/admission.json',
                'update/composition-admission.json', 'update/losses.json', 'work-signals.json', 'checkpoint-final/checkpoint.json')}},
        'confirmation': confirm,
        'continuation': {'planned': 2, 'closed_new_episodes': continuation_closed, 'rows': continuation_rows,
            'state_guard': guard, 'zero_extra_updates_verified': bool(next_complete), 'support': read(next_folder/'support.json')},
        'counts': {'original_new_training_episodes': 16, 'R1_new_training_episodes': 0,
            'R1_confirmation_known': confirm['known'], 'R1_continuation_closed': continuation_closed,
            'R1_new_episodes_closed': confirm['closed_new_episode_boundaries']+continuation_closed, 'R1_new_episode_upper_bound': 14,
            'original_training_consumptions_started': original['prior_training_consumptions_started'],
            'R1_repeated_training_consumptions_started': 16 if admission is not None else 0,
            'cumulative_training_consumptions_started': original['prior_training_consumptions_started']+(16 if admission is not None else 0)},
        'stages': stages, 'accounting': {'original_failed_gpu_seconds': original['original_failed_gpu_seconds'],
            'R1_gpu_seconds_by_stage': costs, 'R1_known_terminated_gpu_seconds': known_cost, 'R1_final_gpu_seconds': new_cost,
            'cumulative_known_terminated_gpu_seconds': original['original_failed_gpu_seconds']+known_cost,
            'cumulative_final_gpu_seconds': original['original_failed_gpu_seconds']+new_cost if new_cost is not None else None,
            'R1_budget_gpu_seconds': plan['internal_gpu_seconds'], 'R1_resource_caps': plan.get('resource_caps', CAPS),
            'model_api_calls': 0, 'external_model_episodes': 0,
            'scope': 'Original failure and R1 recomputation/load/failed-stage costs are additive; old unused budget is not reused. Raw slot sampling and repeated training consumption are separate.'},
        'references': {'supervisor': reference(root/'supervisor.json'), 'plan': supervisor['plan'],
            'catalog': plan['catalog'], 'source_pin': plan.get('source_pin'), 'reporter': reference(Path(__file__))},
        'scope': 'Read-only immutable assessments and stored state/weight metadata. Old run and old reports remain unchanged. No scoring/world replay or tensor loading. Full-work observations do not establish parameter gain or an ID-VTDO configuration effect.'}


def markdown(r):
    def show(value):
        return '未知/未完成' if value is None else str(value)
    a, train, c = r['accounting'], r['training'], r['confirmation']
    lines = ['# v0.25 R1：同一未步进窗口恢复与后续工作', '',
        f"状态：`{r['report_kind']}`；执行已终止：{r['execution_terminal']}。原 v0.25 失败记录和分数保持原样。", '',
        f"原窗口无可重配块。本轮恢复其同一个完整学习状态，重算原16条经历的283个决定；新采样训练经历为0，不把重算当新数据。恢复证据合格：{show(r['restoration']['qualified'])}。",
        f"原16条材料再次训练消费：{train['raw_episode_consumptions_this_recovery_started']}；已完成反向：{show(train['actual_backward_decisions_completed'])}/283；新actor/critic步进：{show(train['new_actor_steps'])}/{show(train['new_critic_steps'])}。未闭合时保存的计数只是进度。", '',
        '预定配置主点估计和参数学习收益均为 null：没有配置分支，也没有这些确认情境的更新前配对评价。本次确认只能描述恢复后 F0 的工作情况，不能据此声称 ID-VTDO 增量或参数改善。', '',
        f"新确认已知{c['known']}/12，完整职责{c['complete_responsibilities']}；全12槽完成比例：{show(c['completed_fraction'])}。未知不填0；未执行不是失败。", '',
        '| 业务条件 | 已知 / 计划 | 完整职责 |', '|---|---:|---:|']
    for label, values in c['business_conditions'].items():
        lines.append(f"| {label} | {values['known']}/{values['planned']} | {values['complete_responsibilities']} |")
    lines += ['', f"新后继交互已闭合{r['continuation']['closed_new_episodes']}/2；无额外更新证据：{r['continuation']['zero_extra_updates_verified']}。R1新增episode最多14，原支持采集16条单列。", '',
        '| 成本 | GPU 小时 |', '|---|---:|', f"| 原失败执行（保留） | {a['original_failed_gpu_seconds']/3600:.6f} |",
        f"| R1 已终止阶段下界 | {a['R1_known_terminated_gpu_seconds']/3600:.6f} |",
        f"| R1 完整成本 | {show(a['R1_final_gpu_seconds']/3600 if a['R1_final_gpu_seconds'] is not None else None)} |",
        f"| 原失败＋R1累计完整成本 | {show(a['cumulative_final_gpu_seconds']/3600 if a['cumulative_final_gpu_seconds'] is not None else None)} |", '',
        'R1新预算为25.5 GPU小时：重算20、确认4.5、后继1；更新任务最多18小时，整体wall最多48小时，单模型实例，无自动再次恢复。所有失败、重算和加载计费，原预算余额不延用。', '',
        '恢复证明保留原未步进判据、完整actor/critic/两优化器/RNG恢复摘要、原entries/composition SHA及admission逐字一致性；不复用中断梯度。报告器只读取这些证据，不加载tensor或重新评分。', '',
        f"原实验：`{r['original']['run_root']}`。本次R1：`{r['run_root']}`。详细原件引用、每阶段资源竞争、完整/部分成果与未知状态见同名JSON。", '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--require-terminal', action='store_true')
    args = parser.parse_args()
    r = report(args.run)
    outputs = [args.output_json.resolve(), args.output_md.resolve()]
    old = Path(r['original']['run_root'])
    if len(set(outputs)) != 2 or any(p.is_relative_to(args.run.resolve()) or p.is_relative_to(old) for p in outputs):
        raise ValueError('R1 reports must be separate from both raw runs')
    old_report_path = Path(r['original']['references']['original_report']['path']).resolve()
    if any(p in {old_report_path, old_report_path.with_suffix('.md')} for p in outputs):
        raise ValueError('R1 must not overwrite either original terminal report')
    if args.require_terminal and not r['execution_terminal']:
        raise ValueError('R1 stages have not all terminated')
    for p in outputs:
        p.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(r, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    outputs[1].write_text(markdown(r))
    print(json.dumps({'report_kind': r['report_kind'], 'confirmation_known': r['confirmation']['known'],
                      'R1_final_gpu_seconds': r['accounting']['R1_final_gpu_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
