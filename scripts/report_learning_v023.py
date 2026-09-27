"""Read existing v023 artifacts only: fixed pairs, signed work signals and costs.

No world replay, grading, model call, checkpoint tensor load or reward rewrite.
A live snapshot never becomes a final report; unknown outcomes retain all slots.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

from scripts.report_domain_v022 import calls, pick, read, reference, resources

VERSION = 'paired-work-learning-report-v0.23'
STAGES = ('train', 'train_recovery', 'eval_initial', 'eval_final', 'external_initial', 'external_final')
INTERNAL_STAGES = ('train', 'train_recovery', 'eval_initial', 'eval_final')
EXTERNAL_STAGES = ('external_initial', 'external_final')
TASKS = ('joint_a', 'joint_b', 'maintenance')
ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def pinned(ref):
    if not isinstance(ref, dict) or not ref.get('path') or not ref.get('sha256'):
        raise ValueError('A frozen artifact reference is required')
    path = Path(ref['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
        raise ValueError('Frozen artifact identity differs: ' + str(path))
    return read(path)


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def validate_catalog(catalog):
    slots, cases = catalog['evaluation_slots'], catalog['evaluation_cases']
    if (len(slots) != 24 or len(cases) != 12 or len({x['case_id'] for x in cases}) != 12
            or Counter(x['task'] for x in cases) != Counter(dict.fromkeys(TASKS, 4))
            or len({x['slot_id'] for x in slots}) != 24
            or len({(x['case_id'], x['seed']) for x in slots}) != 24):
        raise ValueError('Expected twelve cases, three equal structures and twenty-four fixed pairs')
    case_by_id = {x['case_id']: x for x in cases}
    for case_id, case in case_by_id.items():
        here = [x for x in slots if x['case_id'] == case_id]
        if (len(here) != 2 or {x['repeat_index'] for x in here} != {0, 1}
                or any(x['task'] != case['task'] or x['seed'] != x['sampling_seed'] for x in here)):
            raise ValueError('Each declared situation requires two fixed seed repeats')
    windows = catalog['training_windows']
    if (len(windows) != 4 or {w['window_index'] for w in windows} != set(range(4))
            or len({w['window_id'] for w in windows}) != 4
            or any(len(w['slots']) != 6 for w in windows)):
        raise ValueError('Four original six-slot windows are required')
    return slots


def index_progress(rows, declared):
    if not isinstance(rows, list):
        raise ValueError('Progress must be an ordered list')
    contracts = {x['slot_id']: x for x in declared}
    indexed = {}
    for row in rows:
        key = row.get('slot_id')
        if key not in contracts or key in indexed:
            raise ValueError('Unknown or repeated planned evaluation slot')
        for name, expected in contracts[key].items():
            if row.get(name) != expected:
                raise ValueError(f'Observed slot changes frozen {name}: {key}')
        indexed[key] = row
    return indexed


def outcome(row, expected_actor=None):
    """Read trustworthy completed assessment only; its default False is not zero."""
    if row is None:
        return {'known': False, 'value': None, 'reason': 'not_observed'}
    assessment, guard = row.get('assessment', {}), row.get('evaluation_guard', {})
    valid = (row.get('status') == 'closed' and assessment.get('eligible') is True
             and assessment.get('independent_assessability') == 'known'
             and type(assessment.get('completed')) is bool
             and guard.get('learning_unchanged') is True and guard.get('rng_restored_exactly') is True
             and isinstance(row.get('initial_business_state_sha256'), str)
             and bool(row.get('initial_business_state_sha256'))
             and expected_actor is not None and row.get('actor_identity') == expected_actor)
    value = assessment.get('completed') if valid else None
    full = assessment.get('work_components', {}).get('full_responsibility')
    if valid and type(full) is bool and full != value:
        raise ValueError('Saved full-responsibility predicates disagree')
    return {'known': valid, 'value': value, 'reason': None if valid else 'unfinished_unknown_or_failed_identity_guard',
            'status': row.get('status'), 'actor_matches_endpoint': row.get('actor_identity') == expected_actor if expected_actor is not None else None,
            'evaluation_guard': guard, 'exclusions': assessment.get('exclusions'),
            'reward': assessment.get('reward') if valid and finite(assessment.get('reward')) else None}


def auxiliary(assessment, *, trusted, task):
    """Only predicates exposed by saved assessment; absent distinctions stay null."""
    if not trusted:
        return {'available': False, 'reason': 'unknown_or_untrusted_outcome', 'correct_content_only': None,
                'correct_fixed_product': None, 'formal_review_absent': None, 'invalid_approvals': None,
                'unsupported_approvals': None, 'wrong_content_approvals_with_complete_evidence': None,
                'invalid_issues': None}
    facts = assessment.get('facts', {})
    judgments = facts.get('judgments')
    review_known = isinstance(judgments, list) and task in ('joint_b', 'maintenance')
    approvals = [j for j in judgments if j.get('action') == 'approve'] if review_known else []
    issues = [j for j in judgments if j.get('action') == 'raise_issue'] if review_known else []
    product = assessment.get('work_components', {}).get('business_product')
    return {'available': True, 'correct_content_only': None,
            'correct_content_only_reason': 'Saved assessment combines correct content with fixed-product provenance; no separate pure-content predicate is exposed.',
            'correct_fixed_product': product if type(product) is bool else None,
            'current_correct_build_witness': bool(facts['current_correct_build']) if 'current_correct_build' in facts else None,
            'formal_review_absent': not judgments if review_known else None,
            'invalid_approvals': sum(j.get('valid') is False for j in approvals) if review_known else None,
            'unsupported_approvals': sum(not j.get('read_evidence') for j in approvals) if review_known else None,
            'wrong_content_approvals_with_complete_evidence': sum(j.get('valid') is False and bool(j.get('read_evidence')) for j in approvals) if review_known else None,
            'invalid_issues': sum(j.get('valid') is False for j in issues) if review_known else None,
            'wrong_content_issue_count': None,
            'wrong_content_issue_count_reason': 'Invalid issue may reflect content, location or evidence; the saved valid flag does not identify the cause.',
            'judgments': judgments if review_known else None,
            'maintenance_event_triggered': facts.get('maintenance_event_triggered'),
            'actual_result_change_required': facts.get('actual_result_change_required'),
            'components': assessment.get('components', []),
            'scope': 'Formal-review absence means no successful formal judgment, not absence of all reading. Joint A has no reviewer responsibility. Invalid approval and unsupported approval overlap.'}


def bounded_mean(pairs):
    differences = [p['difference'] for p in pairs if p['known_pair']]
    count, unknown = len(pairs), len(pairs) - len(differences)
    total = math.fsum(differences)
    return {'planned_pairs': count, 'known_pairs': len(differences), 'unknown_pairs': unknown,
            'mean_difference': total / count if count and not unknown else None,
            'known_pair_mean_descriptive_only': total / len(differences) if differences else None,
            'full_denominator_bounds': [(total-unknown)/count, (total+unknown)/count] if count else None}


def pair_evaluations(catalog, before, after, *, initial_actor, final_actor):
    slots = validate_catalog(catalog)
    indexed = {'initial': index_progress(before, slots), 'final': index_progress(after, slots)}
    pairs = []
    for slot in slots:
        left, right = [indexed[label].get(slot['slot_id']) for label in ('initial', 'final')]
        hashes = [r.get('initial_business_state_sha256') if r else None for r in (left, right)]
        if all(hashes) and hashes[0] != hashes[1]:
            raise ValueError('Paired initial business states differ: ' + slot['slot_id'])
        first, last = outcome(left, initial_actor), outcome(right, final_actor)
        known = first['known'] and last['known'] and bool(hashes[0]) and hashes[0] == hashes[1]
        pairs.append({**slot, 'initial': first, 'final': last, 'initial_business_state_sha256': hashes,
                      'known_pair': known, 'difference': int(last['value'])-int(first['value']) if known else None,
                      'auxiliary': {label: auxiliary(row.get('assessment', {}) if row else {}, trusted=known_side['known'], task=slot['task'])
                                    for label, row, known_side in [('initial', left, first), ('final', right, last)]}})
    # Both repeats of one exact situation must also share the initial business state.
    for label, rows in indexed.items():
        by_case = {}
        for row in rows.values():
            value = row.get('initial_business_state_sha256')
            if value:
                previous = by_case.setdefault(row['case_id'], value)
                if value != previous:
                    raise ValueError(label + ' repeats changed the declared situation')
    groups = {task: bounded_mean([p for p in pairs if p['task'] == task]) for task in TASKS}
    overall = bounded_mean(pairs)
    macro = math.fsum(g['mean_difference'] for g in groups.values())/3 if all(g['mean_difference'] is not None for g in groups.values()) else None
    cases = [{'case_id': case['case_id'], 'task': case['task'], **bounded_mean([p for p in pairs if p['case_id'] == case['case_id']])}
             for case in catalog['evaluation_cases']]
    return {'primary': overall, 'structure_macro_difference': macro,
            'structure_macro_bounds': [math.fsum(g['full_denominator_bounds'][i] for g in groups.values())/3 for i in (0, 1)],
            'structures': groups, 'cases': cases, 'pairs': pairs, 'independent_situations': 12,
            'planned_evaluation_episodes': 48, 'source_families': 1,
            'interpretation': 'Full responsibility only. Twelve situations with two paired seed repeats; 48 endpoint episodes are not 48 independent tests. Pairing fixes case, Torch sampling seed and initial business state, not every wire message or token. StaffRuntime run_id uses UUID; its request_key-derived command identifiers and response_sha256 can enter subsequent actual tool inputs. This uncontrolled Gamma randomness, two repeats and one training seed limit deterministic attribution to parameter updates. The planned paired estimand remains unchanged. No significance, power, source-generalization or ID-VTDO claim.',
            'pairing_boundary': {'controlled': ['case', 'Torch_sampling_seed', 'initial_business_state'],
                'wire_or_token_identity_guaranteed': False,
                'uncontrolled_gamma_path': 'StaffRuntime.run_id UUID -> request_key -> command identifiers; actual response digests may enter subsequent role inputs',
                'world_identifier_mechanism_changed': False,
                'parameter_update_only_deterministic_attribution': False}}


def stage_terminal(state, supervisor_closed):
    if state.get('attempted') is False and supervisor_closed:
        return True
    return (state.get('ended_at') is not None and state.get('exit_code') is not None
            and state.get('status') in {'complete', 'stopped', 'supervisor_error', 'failed'})


def training_report(root, catalog):
    marker = read(root / 'training-complete.json', {})
    recovery_progress = root / 'train_recovery/actual/training-progress.json'
    if marker.get('progress'):
        observed = pinned(marker['progress'])
        folder = Path(marker['progress']['path']).parent
    else:
        folder = recovery_progress.parent if recovery_progress.is_file() else root / 'train/actual'
        observed = read(folder / 'training-progress.json', [])
    declared = {x['window_id']: x for x in catalog['training_windows']}
    by_id = {}
    for row in observed:
        if row.get('window_id') not in declared or row['window_id'] in by_id:
            raise ValueError('Unknown or repeated training window')
        if row.get('window_index') != declared[row['window_id']]['window_index']:
            raise ValueError('Training window index differs')
        by_id[row['window_id']] = row
    windows = []
    for contract in catalog['training_windows']:
        row = by_id.get(contract['window_id'], {})
        here = Path(row['entries']['path']).parent if row.get('entries', {}).get('path') else folder / f"window-{contract['window_index']}"
        slots = read(here / 'progress.json', [])
        index_progress(slots, contract['slots'])
        update = read(here / 'update/report.json', {})
        signals = read(here / 'work-signals.json', row.get('signals'))
        post = read(here / 'update/post-update-sampled-policy.json')
        accepted = update.get('status') in ACCEPTED
        closed = row.get('status') == 'closed' and len(slots) == 6 and all(s.get('status') == 'closed' for s in slots) and accepted
        windows.append({'window_id': contract['window_id'], 'window_index': contract['window_index'],
            'status': row.get('status', 'not_observed'), 'complete': closed, 'planned_slots': 6,
            'observed_slots': slots, 'update': pick(update, ('status', 'stage', 'actor_optimizer_steps',
                'critic_optimizer_steps', 'actor_steps_total', 'critic_steps_total', 'changed_actor_elements',
                'backward_decisions_completed', 'admitted_decisions', 'admitted_output_tokens',
                'before_actor_identity', 'after_actor_identity', 'post_update_additional_actor_forwards')),
            'last_persisted_step_counts_are_terminal': closed,
            'work_signals': signals,
            'post_update_probability': {**pick(post, ('selection', 'same_parameter_probability_gate',
                'maximum_decisions', 'before_actor_identity', 'after_actor_identity', 'full_distribution_kl_computed')),
                'decisions': [pick(d, ('call_id', 'task', 'member_id', 'sampled_output_tokens', 'sampled_ratio_range',
                    'mean_new_minus_old_logprob', 'mean_abs_logprob_delta', 'sampled_old_to_new_logratio_mean',
                    'sampled_k3_ratio_minus_logratio_minus_one', 'sampled_ratio_outside_clip_fraction')) for d in post.get('decisions', [])]}
                if post is not None else None,
            'references': {name: reference(here / name) for name in ('progress.json', 'entries.json', 'declaration.json',
                'work-signals.json', 'update/report.json', 'update/admission.json', 'update/losses.json',
                'update/post-update-sampled-policy.json', 'checkpoint/checkpoint.json')}})
    report = read(folder / 'report.json', {})
    return {'planned_windows': 4, 'planned_training_episodes': 24, 'windows': windows,
            'effective_training_folder': str(folder), 'effective_progress': reference(folder / 'training-progress.json'),
            'recovery_reuses_completed_windows_not_additional_samples': folder == recovery_progress.parent,
            'complete_windows': sum(w['complete'] for w in windows),
            'actual_terminal_actor_steps': report.get('actor_steps') if report.get('ended_at') is not None else None,
            'actual_terminal_critic_steps': report.get('critic_steps') if report.get('ended_at') is not None else None,
            'source_unchanged': report.get('source_unchanged'),
            'scope': 'Saved terminal-MC reward/advantage associations, not per-action causal credit. All six original slots remain. Persisted mid-update step counters do not prove final parameter state. Post-update sampled-token change is not full KL or work improvement.'}


def evaluation_progress(folder):
    rows = read(folder / 'progress.json', [])
    for row in rows:
        if row.get('assessment_ref') and pinned(row['assessment_ref']) != row.get('assessment'):
            raise ValueError('Embedded assessment differs from its referenced original artifact')
    return rows


def summarize(run):
    root = Path(run).resolve()
    supervisor = read(root / 'supervisor.json')
    if supervisor is None:
        raise ValueError('No supervisor declaration exists; no frozen evaluation inventory can be inferred')
    plan = pinned(supervisor['plan'])
    catalog = pinned(plan['catalog'])
    validate_catalog(catalog)
    supervisor_closed = supervisor.get('ended_at') is not None and supervisor.get('status') in {'complete', 'closed_with_incomplete_stages', 'supervisor_error'}
    stages, costs = {}, {}
    for name in STAGES:
        line, folder = root / name, root / name / 'actual'
        state, worker = read(line / 'state.json', {}), read(folder / 'report.json', {})
        terminal = stage_terminal(state, supervisor_closed)
        elapsed = state.get('elapsed_gpu_seconds')
        if finite(elapsed) and elapsed < 0:
            raise ValueError('Negative persisted GPU cost')
        cost = elapsed if terminal and finite(elapsed) else 0 if terminal and state.get('attempted') is False else None
        costs[name] = cost
        stages[name] = {'terminal': terminal, 'state': state,
            'worker_status': worker.get('status'), 'worker_source_unchanged': worker.get('source_unchanged'),
            'worker_actor_identity': worker.get('final_actor_identity'),
            'recovery_metadata': pick(worker, ('restoration', 'no_step_proof', 'original_train', 'recovery', 'error')) if name == 'train_recovery' else None,
            'references': {'state': reference(line / 'state.json'), 'report': reference(folder / 'report.json'),
                           'progress': reference(folder / 'progress.json'), 'model_log': reference(line / 'model.log')},
            'resources': resources(line / 'resources.jsonl', state), 'resident_calls': calls(folder)}
    terminal = supervisor_closed and all(s['terminal'] for s in stages.values())
    endpoints = {label: read(root / 'checkpoints' / f'{label}.json', {}) for label in ('initial', 'final')}
    paired = pair_evaluations(catalog, evaluation_progress(root / 'eval_initial/actual'),
                             evaluation_progress(root / 'eval_final/actual'),
                             initial_actor=endpoints['initial'].get('actor_identity'), final_actor=endpoints['final'].get('actor_identity'))
    train = training_report(root, catalog)
    effective_train_stage = 'train_recovery' if train['recovery_reuses_completed_windows_not_additional_samples'] else 'train'
    internal_complete = (terminal and train['complete_windows'] == 4 and paired['primary']['known_pairs'] == 24
        and (root / 'training-complete.json').is_file()
        and all(stages[name]['worker_status'] == 'complete' and stages[name]['worker_source_unchanged'] is True
                and stages[name]['state'].get('status') == 'complete' for name in (effective_train_stage, 'eval_initial', 'eval_final')))
    for paired_row in paired['pairs']:
        paired_row['references'] = {label: {
            'assessment': reference(root / f'eval_{label}/actual' / paired_row['slot_id'] / 'assessment.json'),
            'episode_manifest': reference(root / f'eval_{label}/actual' / paired_row['slot_id'] / 'episode/manifest.json')}
            for label in ('initial', 'final')}
    from proworksim.teambench_model_v023 import compare_checkpoints
    external_paths = {label: root / f'external_{label}/actual/external/report.json' for label in ('initial', 'final')}
    external_reports = {label: read(path) for label, path in external_paths.items()}
    external_for_comparison, external_guards = {}, {}
    for label, external_report in external_reports.items():
        if external_report is None:
            external_for_comparison[label] = None
            external_guards[label] = {'identity_matches_checkpoint': None, 'unknown_guard_seeds': []}
            continue
        expected = endpoints[label].get('actor_identity')
        matched = expected is not None and external_report.get('actor_identity') == expected
        admitted, unknown = [], []
        for row in external_report.get('episodes', []):
            guard = row.get('evaluation_guard', {})
            if (matched and row.get('actor_identity') == expected and guard.get('learning_unchanged') is True
                    and guard.get('rng_restored_exactly') is True):
                admitted.append(row)
            else:
                unknown.append(row['seed'])
        external_for_comparison[label] = {**external_report, 'episodes': admitted}
        external_guards[label] = {'identity_matches_checkpoint': matched, 'unknown_guard_seeds': unknown}
    external = compare_checkpoints(external_for_comparison['initial'], external_for_comparison['final'])
    external['endpoint_guards'] = external_guards
    external['observed_endpoints'] = external_reports
    external['references'] = {label: reference(path) for label, path in external_paths.items()}
    external['planned_episodes'] = 6
    external['outside_internal_72'] = True
    all_complete = internal_complete and (not plan.get('external_enabled') or external['known_pairs'] == 3)
    initial_adapter = endpoints['initial'].get('actor_identity', {}).get('adapter_sha256')
    final_adapter = endpoints['final'].get('actor_identity', {}).get('adapter_sha256')
    same_adapter = initial_adapter == final_adapter if initial_adapter and final_adapter else None
    zero_actor_steps = train['complete_windows'] == 4 and train['actual_terminal_actor_steps'] == 0
    no_parameter_change = same_adapter is True or zero_actor_steps
    parameter_attribution = {'initial_adapter_sha256': initial_adapter, 'final_adapter_sha256': final_adapter,
        'same_adapter_identity': same_adapter, 'actual_terminal_actor_steps': train['actual_terminal_actor_steps'],
        'four_windows_closed': train['complete_windows'] == 4,
        'no_parameter_change_evidence': no_parameter_change,
        'zero_steps_but_different_adapter_identity': zero_actor_steps and same_adapter is False,
        'interpretation': ('The actor completed zero steps or the initial/final adapter hashes are identical. The planned observed paired difference is retained, but any difference cannot be claimed as parameter-learning benefit.'
                           if no_parameter_change else 'Actual checkpoint identities and step counts are retained; an optimizer step alone does not establish improved work.') }
    known_cost = math.fsum(value for value in costs.values() if value is not None)
    all_cost = math.fsum(costs.values()) if terminal and all(v is not None for v in costs.values()) else None
    peaks = [s['resources'].get('sampled_peaks', {}).get('artifact_bytes') for s in stages.values()]
    result = {'version': VERSION, 'generated_at_epoch': time.time(), 'report_kind': 'final_complete' if all_complete else 'closed_incomplete' if terminal else 'snapshot',
        'final': bool(all_complete), 'execution_terminal': terminal, 'internal_protocol_complete': internal_complete,
        'run_root': str(root), 'planned_episodes': {'internal': 72, 'training': 24, 'initial_evaluation': 24, 'final_evaluation': 24, 'external_separate': 6},
        'source_and_artifacts': {'supervisor': reference(root / 'supervisor.json'), 'frozen_source': supervisor.get('source'),
            'plan': supervisor['plan'], 'catalog': plan['catalog'], 'source_pin': plan.get('source_pin'),
            'reporter': reference(Path(__file__)), 'training_complete': reference(root / 'training-complete.json'),
            'checkpoint_markers': {label: reference(root / 'checkpoints' / f'{label}.json') for label in ('initial', 'final')},
            'checkpoint_contents': endpoints},
        'stages': stages, 'paired_evaluation': paired, 'training': train, 'external': external,
        'parameter_learning_attribution': parameter_attribution,
        'accounting': {'persisted_terminal_gpu_seconds_by_stage': costs, 'known_terminated_gpu_seconds': known_cost,
            'final_gpu_seconds': all_cost,
            'internal_gpu_seconds': math.fsum(costs[s] for s in INTERNAL_STAGES) if all(costs[s] is not None for s in INTERNAL_STAGES) else None,
            'external_gpu_seconds': math.fsum(costs[s] for s in EXTERNAL_STAGES) if all(costs[s] is not None for s in EXTERNAL_STAGES) else None,
            'resource_caps': plan.get('resource_caps'), 'internal_cap_gpu_seconds': plan.get('internal_gpu_seconds'),
            'external_cap_gpu_seconds': plan.get('external_gpu_seconds'),
            'shared_artifact_tree_sampled_peak_bytes': max(x for x in peaks if finite(x)) if any(finite(x) for x in peaks) else None,
            'scope': 'The original five stages plus optional one train_recovery elapsed_gpu_seconds are summed once, including original failed training and recomputation. Includes failed stages and loading; overlap costs one GPU per stage. Live stages are excluded from known lower bound. Resource samples retain observed co-resident PIDs; no causal competition claim. Whole-tree artifact peaks are not additive.'},
        'scope': 'Read-only existing assessments and logs; no model, tensor load, world replay, rescoring or input mutation. Snapshot values are provisional. Known failures remain false; unassessed or invalid evidence remains null.'}
    # A prematurely stopped training protocol cannot masquerade as the proposed
    # theta0-to-planned-final learning estimate, even if endpoints were fabricated.
    if terminal and not internal_complete:
        result['planned_learning_effect_estimate'] = None
        result['planned_learning_effect_estimate_reason'] = 'Planned four-window initial/final protocol is incomplete; retained pairs are descriptive only.'
    else:
        result['planned_learning_effect_estimate'] = paired['primary']['mean_difference'] if internal_complete else None
        result['planned_learning_effect_estimate_reason'] = None if internal_complete else 'Execution is a live snapshot, not a final learning result.'
    return result


def markdown(report):
    pair, cost, training = report['paired_evaluation'], report['accounting'], report['training']
    def show(value):
        return '未知/未完成' if value is None else str(value)
    lines = ['# v0.23 有限配对工作学习报告', '',
        f"状态：`{report['report_kind']}`。内部计划 72 例，外部另计 6 例；本报告只读取原始归档，不重新评分。", '',
        f"已完成训练窗口 {training['complete_windows']}/4；可信完整配对 {pair['primary']['known_pairs']}/24，来自 12 个情境的各两次种子重复。",
        f"预定协议完整职责变化：{show(report['planned_learning_effect_estimate'])}；全部 24 对分母的不确定范围：{pair['primary']['full_denominator_bounds']}。", '',
        '| 工作结构 | 已知配对/计划 | 完整职责均值差 | 全分母范围 |', '|---|---:|---:|---|']
    for task, group in pair['structures'].items():
        lines.append(f"| {task} | {group['known_pairs']}/{group['planned_pairs']} | {show(group['mean_difference'])} | {group['full_denominator_bounds']} |")
    lines += ['', '三类结构等权；重复、初末端点和同源新材料均不能当作额外独立来源。已知失败保留为零，未知不填零。一个训练种子不支持稳定性或显著性结论。', '',
              '初末配对固定的是情境、Torch 采样种子与业务初态，并不保证 wire 消息或输入 token 逐项相同。StaffRuntime 的 run_id 使用 UUID，经 request_key 派生的命令标识及 response_sha256 可能进入后续真实工具输入。这项未控制的 Γ 随机性，加上每情境仅两次重复和单训练种子，限制把观测差异确定性地全部归因于参数更新；不改变本报告预先固定的配对及主描述量定义。本轮没有改动世界标识机制。', '',
              '| 训练窗 | 状态 | 最后保存的 actor/critic 步数 | 正优势所关联的已达成回报项 |', '|---|---|---|---|']
    for window in training['windows']:
        update, signals = window['update'], window['work_signals'] or {}
        lines.append(f"| {window['window_index']+1} | {window['status']} | {show(update.get('actor_optimizer_steps'))}/{show(update.get('critic_optimizer_steps'))} | {json.dumps(signals.get('positive_signal_slots_by_achieved_reward_term'), ensure_ascii=False)} |")
    lines += ['', '未闭合更新窗的保存步数是进度，不能替代终态证明。JSON 保留逐槽回报来源、成员动作、正/负/零优势、固定上下文概率变化及原始 SHA 引用。终端回报与动作阶段的关联不等于逐动作因果信用。', '',
              f"终态 actor/critic 累计步数：{show(training['actual_terminal_actor_steps'])}/{show(training['actual_terminal_critic_steps'])}。",
              f"原五阶段及条件恢复已结算 GPU 秒下界：{cost['known_terminated_gpu_seconds']:.3f}；完整总量：{show(cost['final_gpu_seconds'])}。资源竞争 PID 按原监督采样保留，不推断它造成失败。", '',
              f"外部指定 D2 变体：已知 {report['external']['known_pairs']}/3 对；完整责任均值差 {show(report['external']['mean_full_responsibility_difference'])}，独立于内部 72 例。原修订 grader 与真实复核责任分别保存在外部归档。", '',
              '内容、固定交付、复核缺席和错误/无据判断只使用已存 assessment 能直接支持的字段。未公开纯内容或错误原因拆分的字段明确为 null，不据 partial reward 推断完整工作提升。', '',
              f"实验目录：`{report['run_root']}`。冻结源码、计划、catalog、checkpoint 和每项产物 SHA 见同名 JSON。", '']
    attribution = report['parameter_learning_attribution']
    if attribution['no_parameter_change_evidence']:
        if attribution['zero_steps_but_different_adapter_identity']:
            lines += ['记录存在不一致：actor 累计步数为 0，但初末 adapter SHA 不同。保留两项原始事实，不能将观测差异解释为参数学习收益。', '']
        else:
            lines += ['参数未改变：四窗闭合后的 actor 累计步数为 0，或初末 adapter SHA 完全相同。上述配对差仍是预定的观测描述量；任何差异均不能归为参数学习收益。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--require-terminal', action='store_true')
    args = parser.parse_args()
    outputs = [args.output_json.resolve(), args.output_md.resolve()]
    if len(set(outputs)) != 2 or any(path.is_relative_to(args.run.resolve()) for path in outputs):
        raise ValueError('Distinct reporting outputs must remain outside original experiment artifacts')
    report = summarize(args.run)
    if args.require_terminal and not report['execution_terminal']:
        raise ValueError('Cannot issue a terminal report while a declared stage may still run')
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    outputs[1].write_text(markdown(report))
    print(json.dumps({'report_kind': report['report_kind'], 'known_pairs': report['paired_evaluation']['primary']['known_pairs'],
                      'final_gpu_seconds': report['accounting']['final_gpu_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
