"""Read-only support, actual actor weights, independent confirmation and costs."""
import argparse
import json
import math
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts.composition_evidence_v025 import endpoint, paired_evaluations, read_evaluations, terminal
from scripts.composition_evidence_v025 import checked
from scripts.report_domain_v022 import calls, read, reference, resources
from scripts.run_composition_v025 import ORDER

ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def branch_evidence(root, label, end, common):
    folder = root / ('train_' + label) / 'actual'
    update = read(folder / 'update/report.json', {})
    consumption = read(folder / 'consumption.json')
    composition = read(folder / 'composition.json')
    admission = read(folder / 'update/composition-admission.json')
    losses = read(folder / 'update/losses.json')
    weights_match, target_rows = None, []
    if composition is not None and update.get('composition_materialization'):
        if read_json(checked(update['composition_materialization'])) != composition:
            raise ValueError('Declared composition differs from the actual update artifact')
    if update.get('composition_admission') and read_json(checked(update['composition_admission'])) != admission:
        raise ValueError('Saved row composition admission differs')
    if admission and losses is not None:
        by_id = {(r['slot_id'], r['member_id'], r['call_id']): r for r in admission['rows']}
        keys = [(r['slot_id'], r['member_id'], r['call_id']) for r in losses]
        if len(set(keys)) != len(keys) or set(keys) != set(by_id):
            raise ValueError('Actual backward row/member inventory differs from composition')
        weights_match = all(math.isclose(row['composition_weight'], by_id[key]['weight'], rel_tol=0, abs_tol=0)
                            for row, key in zip(losses, keys))
        target_rows = [{**by_id[key], 'actor_loss': row['actor_loss'], 'critic_loss': row['critic_loss']}
                       for row, key in zip(losses, keys)]
    same_origin = None
    if consumption and common:
        same_origin = (consumption['raw_entries'] == common['entries']
            and consumption['declaration'] == common['declaration']
            and consumption['support'] == common['support']
            and consumption['restored_state_tensor_digest'] == common['origin_checkpoint']['state_tensor_digest']
            and consumption['same_complete_origin'] is True)
    counts_match = None
    if end['available'] and update:
        meta = end['saved_metadata']
        counts_match = (meta['actor_steps'] == 2 + update.get('actor_optimizer_steps', 0)
            and meta['critic_steps'] == 2 + update.get('critic_optimizer_steps', 0)
            and update.get('after_actor_identity') == end['actor_identity'])
    ready = (update.get('status') in ACCEPTED and end['available'] and counts_match is True
             and same_origin is True and admission is not None)
    if update.get('status') == 'updated':
        ready = ready and weights_match is True
    return {'status': update.get('status'), 'qualified_closed_update': ready,
        'same_complete_origin': same_origin, 'actual_weights_match_backward_records': weights_match,
        'checkpoint_steps_match_update': counts_match, 'update': update,
        'composition': composition, 'composition_admission': admission,
        'actual_backward_rows': target_rows, 'consumption': consumption,
        'nonunit_backward_decisions': sum(row['weight'] != 1 for row in target_rows),
        'nonzero_nonunit_actor_loss_decisions': sum(row['weight'] != 1 and row['actor_loss'] != 0 for row in target_rows),
        'unweighted_admission_reference': reference(folder / 'update/admission.json'),
        'references': {name: reference(folder / name) for name in ('consumption.json', 'composition.json',
            'update/report.json', 'update/composition-admission.json', 'update/losses.json', 'work-signals.json')}}


def report(root):
    root = Path(root).resolve()
    supervisor = read_json(root / 'supervisor.json')
    plan = read_json(checked(supervisor['plan']))
    catalog = read_json(checked(plan['catalog']))
    source = supervisor['source']
    stages = {}
    for stage in ORDER:
        folder = root / stage
        state = read(folder / 'state.json', {})
        worker = read(folder / 'actual/report.json', {})
        if worker.get('source_before') not in (None, source) or worker.get('source_after') not in (None, source):
            raise ValueError('A worker used a different source tree')
        stages[stage] = {'state': state, 'worker_status': worker.get('status'),
            'worker_error': worker.get('error'), 'source_unchanged': worker.get('source_unchanged'),
            'actual_new_episodes': worker.get('actual_new_episodes'),
            'resources': resources(folder / 'resources.jsonl', state),
            'resident_calls': calls(folder / 'actual'),
            'references': {name: reference(folder / name) for name in ('state.json', 'actual/report.json', 'model.log')}}
    execution_terminal = bool(supervisor.get('ended_at')) and all(terminal(s['state']) for s in stages.values())
    common = read(root / 'support-complete.json')
    support = read_json(checked(common['support'])) if common else read(root / 'support/actual/support.json')
    if common:
        if common['source'] != source:
            raise ValueError('Support collection completion source differs')
        for key in ('entries', 'declaration', 'admission', 'origin'):
            checked(common[key])
    decision = read(root / 'configuration-decision.json')
    if decision and (decision['source'] != source or decision['confirmation_outcomes_used'] is not False):
        raise ValueError('Configuration was not fixed independently of confirmation')
    ends = {label: endpoint(root, label, source) for label in ('origin', 'base', 'probe', 'configured')}
    branches = {label: branch_evidence(root, label, ends[label], common) for label in ('base', 'probe', 'configured')}
    development = {label: read_evaluations(root, 'dev_' + label, catalog['development_slots'],
                   ends[label]['actor_identity']) for label in ('base', 'probe')}
    confirmation = {label: read_evaluations(root, 'confirm_' + label, catalog['confirmation_slots'],
                    ends[label]['actor_identity']) for label in ('base', 'configured')}
    comparisons = {'development_probe_minus_base': paired_evaluations(development['base'], development['probe']),
                   'confirmation_configured_minus_base': paired_evaluations(confirmation['base'], confirmation['configured'])}
    if decision and decision.get('development_required'):
        for label in ('base', 'probe'):
            if decision['development_evidence'][label] != development[label]:
                raise ValueError('Development evidence changed after configuration decision')
    if decision:
        for stage in ('confirm_base', 'confirm_configured'):
            start = stages[stage]['state'].get('started_at')
            if start is not None and start < decision['decided_at']:
                raise ValueError('Independent confirmation began before configuration was fixed')
    for label, branch in branches.items():
        comp = branch['composition']
        if comp is not None:
            if label == 'base' and comp['Q_equals_B'] is not True:
                raise ValueError('Base comparison changed its composition')
            if label == 'configured' and (not decision or comp['q_by_xi'] != decision['q_by_xi'] or comp['Q_equals_B']):
                raise ValueError('Formal configuration differs from the frozen development decision')
            if branch['consumption'] and read_json(checked(branch['consumption']['composition'])) != comp:
                raise ValueError('Consumption refers to different composition bytes')
    admission_refs = [v['unweighted_admission_reference'] for v in branches.values() if v['qualified_closed_update']]
    same_prepared = (all(admission_refs) and len({r['sha256'] for r in admission_refs}) == 1) if admission_refs else None
    continuations = {}
    for label in ('base', 'configured'):
        folder = root / ('next_' + label) / 'actual'
        progress = read(folder / 'collection/progress.json', [])
        guard = read(folder / 'state-guard.json')
        continuations[label] = {'closed_new_episodes': sum(r.get('status') == 'closed' for r in progress),
            'progress': progress, 'support': read(folder / 'support.json'), 'guard': guard,
            'zero_extra_updates_verified': bool(guard and guard['learning_unchanged'] and guard['rng_restored_exactly'])}
    support_progress = read(root / 'support/actual/collection/progress.json', [])
    protocol_complete = execution_terminal and all(s['state'].get('status') in {'complete', 'not_required'} for s in stages.values())
    configured = bool(decision and decision['changed'])
    comparison = comparisons['confirmation_configured_minus_base']['overall']
    primary_ready = (protocol_complete and configured and decision.get('development_complete') is True
        and branches['base']['qualified_closed_update'] and branches['probe']['qualified_closed_update']
        and branches['configured']['qualified_closed_update'] and same_prepared is True
        and comparison['known_pairs'] == 12
        and branches['configured']['nonunit_backward_decisions'] > 0)
    if not execution_terminal:
        kind = 'snapshot'
    elif not protocol_complete:
        kind = 'closed_incomplete'
    elif not support or support['selected_block'] is None:
        kind = 'closed_no_supported_block'
    elif not configured:
        kind = 'closed_no_configuration_change'
    else:
        kind = 'final_complete_configuration_comparison' if primary_ready else 'closed_incomplete_configuration_evidence'
    gpu = {k: v['state'].get('elapsed_gpu_seconds', 0) for k, v in stages.items()}
    new_counts = {'support': sum(r.get('status') == 'closed' for r in support_progress),
        'development': sum(v['known'] for v in development.values()),
        'confirmation': sum(v['known'] for v in confirmation.values()),
        'continuation': sum(v['closed_new_episodes'] for v in continuations.values())}
    return {'version': 'member-composition-report-v0.25', 'generated_at_epoch': time.time(),
        'run_root': str(root), 'report_kind': kind, 'execution_terminal': execution_terminal,
        'protocol_complete_for_executed_branch': protocol_complete,
        'planned_primary_composition_difference': comparison['mean_difference'] if primary_ready else None,
        'primary_reason': None if primary_ready else 'No complete independent configured-versus-base comparison; missing or unexecuted is not zero.',
        'configuration_changed': configured, 'support': support, 'support_progress': support_progress,
        'common_collection': common, 'decision': decision, 'endpoints': ends, 'branches': branches,
        'actual_raw_admissions_equal_across_completed_consumers': same_prepared,
        'development': development, 'confirmation': confirmation, 'comparisons': comparisons,
        'continuations': continuations, 'closed_new_episode_counts': new_counts,
        'closed_new_episodes_total': sum(new_counts.values()),
        'training_episode_consumptions_started': 16*sum(v['consumption'] is not None for v in branches.values()),
        'new_actor_steps': sum(v['update'].get('actor_optimizer_steps', 0) for v in branches.values()),
        'new_critic_steps': sum(v['update'].get('critic_optimizer_steps', 0) for v in branches.values()),
        'stages': stages, 'accounting': {'gpu_seconds_by_stage': gpu,
            'terminated_gpu_seconds': sum(gpu.values()), 'final_gpu_seconds': sum(gpu.values()) if execution_terminal else None,
            'budget_gpu_seconds': plan['internal_gpu_seconds'], 'external_model_episodes': 0, 'model_api_calls': 0,
            'wall_seconds': supervisor['ended_at']-supervisor['started_at'] if supervisor.get('ended_at') else None},
        'source': source, 'references': {'supervisor': reference(root / 'supervisor.json'),
            'plan': supervisor['plan'], 'catalog': plan['catalog'], 'source_pin': plan['source_pin'],
            'decision': reference(root / 'configuration-decision.json')},
        'scope': 'Existing immutable outcomes/weights/state metadata only; no model, replay, grader or tensor load. Conditional v024 MC start, one current training window, one member block, noisy development and six independent confirmation situations. No broad information-structure or efficiency superiority claim.'}


def markdown(r):
    a = r['accounting']
    lines = ['# v0.25 当前经验支持与成员配置实验', '',
        f"状态：`{r['report_kind']}`；执行终止：{r['execution_terminal']}。",
        f"实际闭合新episode：{r['closed_new_episodes_total']}（支持/开发/确认/后继分别{list(r['closed_new_episode_counts'].values())}）；训练消费{r['training_episode_consumptions_started']}，新actor/critic步骤{r['new_actor_steps']}/{r['new_critic_steps']}。", '',
        f"预定配置−基础主点估计：{r['planned_primary_composition_difference']}；配置是否改变：{r['configuration_changed']}。",
        '无支持或最终保持Q=B时，不制造相同配置的重复模型比较；未执行不是零效果，未知不是负贡献。', '',
        '| 精确情境 / 成员 | M | n+ | v | 各类n | b | 自由度 |', '|---|---:|---:|---:|---|---|---:|']
    for xi, support in (r['support'] or {}).get('supports_by_xi', {}).items():
        for member, b in support['blocks'].items():
            lines.append(f"| {xi} / {member} | {b['M']} | {b['n_positive']} | {b['v']:.3f} | {b['n_by_class']} | {b['b']} | {b['composition_degrees_of_freedom']} |")
    lines += ['', f"预定顺序选中块：{(r['support'] or {}).get('selected_block')}。",
        f"配置决定：{(r['decision'] or {}).get('reason')}；开发差分贡献：{(r['decision'] or {}).get('contribution_estimate')}。", '',
        '| 确认端点 | 已知 / 12 | 完整职责 |', '|---|---:|---:|']
    for label, values in r['confirmation'].items():
        lines.append(f"| {label} | {values['known']}/12 | {values['completed']} |")
    lines += ['', '确认端点未执行时，上表完整职责计数不构成0/12成绩。JSON保留每个槽的未知、部分成果与复核有效性。', '',
        '| 分支 | 更新状态 | 同完整起点 | 反向权重匹配 | 非单位权重决定 |', '|---|---|---|---|---:|']
    for label, b in r['branches'].items():
        lines.append(f"| {label} | {b['status']} | {b['same_complete_origin']} | {b['actual_weights_match_backward_records']} | {b['nonunit_backward_decisions']} |")
    lines += ['', '只有合格成员分支actor项乘q/b；原奖励/优势/PPO比率/critic及槽、成员、本人token分母保持。共同原轨迹分别消费，不冒充新样本。', '',
        '| 阶段 | 状态 | GPU小时 |', '|---|---|---:|']
    for stage, value in r['stages'].items():
        lines.append(f"| {stage} | {value['state'].get('status')} | {a['gpu_seconds_by_stage'][stage]/3600:.6f} |")
    lines += ['', f"已结算成本{a['terminated_gpu_seconds']/3600:.6f} GPU小时，新上限58；外部模型/API为0。加载、试训、开发、失败和并行卡占用全部计入。",
        '后继交互仅新策略rollout与支持诊断，无第二次优化。一般元调权强基线、独立训练seed、跨来源与图特征贡献均未在本轮检验。', '',
        '原始证据、配置和逐成员权重、完整起点、端点配对、资源竞争及停止原因见同名JSON。此报告只读原记录，没有补采、重评分或改写旧实验。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--require-terminal', action='store_true')
    args = parser.parse_args()
    root = args.run.resolve()
    if any(p.resolve().is_relative_to(root) for p in (args.output_json, args.output_md)):
        raise ValueError('Reports must not mutate the raw experiment directory')
    result = report(root)
    if args.require_terminal and not result['execution_terminal']:
        raise ValueError('The experiment is still running; do not call this a terminal report')
    for path, content in ((args.output_json, json.dumps(result, ensure_ascii=False, indent=2)+'\n'),
                          (args.output_md, markdown(result))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(json.dumps({'report_kind': result['report_kind'], 'closed_new_episodes': result['closed_new_episodes_total'],
                      'primary': result['planned_primary_composition_difference']}))


if __name__ == '__main__':
    main()
