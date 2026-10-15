#!/usr/bin/env python3
"""Extract existing terminal reports; no model, tokenizer, world, or acceptance calls."""
import hashlib
import json
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, default=Path('/data1/zhuxinrui/projects/ProWorkSim'),
                    help='Repository root containing docs/experiments/*-final.json')
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent,
                    help='Output directory for comparison-data.json and data-findings.md')
args = parser.parse_args()
ROOT = args.source_root.resolve()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
VERSIONS = {'v045': 'v045-completion', 'v047': 'v047', 'v048': 'v048'}
SOURCES = {}
DATA = {}
for version, name in VERSIONS.items():
    path = ROOT / f'docs/experiments/software-organization-{name}-final.json'
    raw = path.read_bytes()
    SOURCES[version] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'bytes': len(raw)}
    DATA[version] = json.loads(raw)


def get(obj, pointer):
    if pointer is None:
        return None
    for part in pointer.strip('/').split('/'):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def ref(version, pointer):
    return {'source_id': version, 'json_pointer': pointer}


def extract(obj, version, pointer, mapping):
    row = {key: get(obj, path) for key, path in mapping.items()}
    row['provenance'] = {
        'source_id': version, 'json_pointer': pointer,
        'field_pointers': {key: f'{pointer}/{path}' if path else None
                           for key, path in mapping.items()},
    }
    return row


def scalar_total(values):
    return sum(values) if values and all(v is not None for v in values) else None


def delta(a, b):
    return a - b if a is not None and b is not None else None


def mean(values):
    total = scalar_total(values)
    return total / len(values) if total is not None else None


def ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def outcome(values):
    known = [v for v in values if v is not None]
    return {'fixed_denominator': len(values), 'known': len(known),
            'unknown': len(values) - len(known), 'known_sum': sum(known),
            'mean': mean(values),
            'identification_interval': [sum(known) / len(values),
                                        (sum(known) + len(values) - len(known)) / len(values)]}


def aggregate(rows):
    result = {'fixed_denominator': len(rows), 'slot_ids': [r['slot_id'] for r in rows],
              'R': outcome([r['R'] for r in rows]), 'Q': outcome([r['Q'] for r in rows]),
              'statuses': dict(Counter(r['outcome_status'] for r in rows)),
              'complete_cost_records': sum(r['complete_actual_tokens'] is not None for r in rows)}
    for key in ('complete_actual_tokens', 'actual_calls', 'member_tests', 'new_births'):
        values = [r[key] for r in rows]
        result[key] = scalar_total(values)
        result[f'mean_{key}'] = mean(values)
    submitted = [r for r in rows if r['submitted'] is True]
    result['first_submit_cost'] = {
        'submitted_slots': len(submitted), 'not_all_slot_denominator': True,
        'known_cost_records': sum(r['first_fixed_submit_tokens'] is not None for r in submitted),
        'total': scalar_total([r['first_fixed_submit_tokens'] for r in submitted]),
        'mean': mean([r['first_fixed_submit_tokens'] for r in submitted]),
        'no_submission_cost': None,
    }
    result['derivation'] = 'Sum/mean of listed normalized rows, including failures; mean is null if any value is unknown. First-submit summaries use only actual submitters and are explicitly separate.'
    return result


ROWS = {}
v45 = DATA['v045']
work_index = {r['slot_id']: (i, r) for i, r in enumerate(v45['slot_work_summaries'])}
ROWS['v045'] = []
for i, raw in enumerate(v45['rows']):
    r = extract(raw, 'v045', f'/rows/{i}', {
        'slot_id': 'slot_id', 'root_id': 'root_label', 'condition': 'condition',
        'sampling_seed': 'sampling_seed', 'first_member': 'first_member',
        'R': 'R', 'Q': None, 'submitted': 'submitted', 'outcome_status': 'status',
        'complete_actual_tokens': 'usage/total_tokens', 'actual_calls': 'usage/output_bearing_calls',
        'decisions': 'usage/decisions', 'attempts': 'usage/attempts', 'member_tests': 'run_tests',
        'first_fixed_submit_tokens': None,
    })
    wi, w = work_index[r['slot_id']]
    wp = f'/slot_work_summaries/{wi}'
    r['Q_status'] = 'unknown_not_reported_in_canonical_row; not inferred from R'
    r['first_submit_cost_status'] = 'unknown_not_reported_in_canonical_row'
    r['initial_members'] = len(w['population']['initial_members'])
    r['cumulative_members'] = len(w['population']['registered_members'])
    r['new_births'] = len(w['population']['actual_births'])
    r['partner_use'] = {key: w.get(key) for key in (
        'cross_member_applicability', 'has_evidenced_cross_member_chain',
        'has_use_linked_to_final_fixed_delivery', 'pending_semantic_relation_count')}
    r['partner_use']['scope'] = 'Original frozen tracker; S1 false is not-applicable, not a collaboration failure; independent file application is recorded separately.'
    r['provenance']['work'] = ref('v045', wp)
    r['provenance']['field_pointers'].update({
        'initial_members': wp + '/population/initial_members',
        'cumulative_members': wp + '/population/registered_members',
        'new_births': wp + '/population/actual_births',
        'partner_use': wp,
    })
    r['provenance']['population_derivation'] = 'Length of original member/birth lists; cumulative includes initial members.'
    ROWS['v045'].append(r)

COMMON = {key: key for key in ('slot_id', 'root_id', 'condition', 'sampling_seed',
    'team_token_budget', 'submitted', 'complete_actual_tokens', 'first_fixed_submit_tokens',
    'R_joint', 'R_token', 'Q_joint', 'Q_token', 'administrative_censoring')}
COMMON.update({'R': 'R_joint', 'Q': 'Q_joint', 'outcome_status': 'outcome_class'})
ROWS['v047'] = []
for i, raw in enumerate(DATA['v047']['slots']):
    r = extract(raw, 'v047', f'/slots/{i}', {**COMMON,
        'pilot_stage': 'pilot_stage', 'new_births': 'actual_spawn_events',
        'cumulative_members': 'cumulative_born_members', 'actual_call_members': 'actual_call_members',
        'peak_live_members': 'peak_live_members', 'actual_calls': 'cost_detail/actual_model_calls',
        'member_tests': 'cost_detail/tests/accepted_run_tests_calls',
        'decisions': 'cost_detail/usage/decisions', 'attempts': 'cost_detail/usage/attempts',
        'after_first_submit_tokens': 'after_first_submit_tokens',
        'rejection_counts': 'cost_detail/stop_classifications',
        'exact_candidate_application_count': 'exact_candidate_applications',
        'semantic_candidates_pending': 'semantic_candidates_pending',
    })
    r['initial_members'] = len(raw['cost_detail']['member_lifecycle']['initial_members'])
    r['provenance']['field_pointers']['initial_members'] = f'/slots/{i}/cost_detail/member_lifecycle/initial_members'
    ROWS['v047'].append(r)

ROWS['v048'] = []
for i, raw in enumerate(DATA['v048']['slots']):
    r = extract(raw, 'v048', f'/slots/{i}', {**COMMON,
        'representation': 'representation', 'actual_calls': 'actual_calls',
        'member_tests': 'member_tests', 'decisions': 'usage/decisions', 'attempts': 'usage/attempts',
        'hard_context_rejections': 'hard_context_rejections',
        'after_first_submit_tokens': 'after_first_submit_tokens',
        'cumulative_members': 'population_measurements/cumulative_born_members',
        'actual_call_members': 'population_measurements/actual_call_participant_count',
        'peak_live_members': 'population_measurements/lifecycle_counts/peak_live',
        'cross_member_applicability': 'cross_member_applicability',
        'frozen_symbol_measurement': 'frozen_symbol_measurement',
    })
    initial = raw['population_measurements']['lifecycle_counts']['initial_members']
    r['initial_members'] = len(initial)
    r['new_births'] = delta(r['cumulative_members'], len(initial))
    r['provenance']['field_pointers']['initial_members'] = f'/slots/{i}/population_measurements/lifecycle_counts/initial_members'
    r['provenance']['new_births_derivation'] = 'cumulative_members minus length(initial_members); distinguishes initial assignment from extra births.'
    r['partner_file_applications'] = [
        {**{key: value for key, value in a.items() if key != 'sources'},
         'provenance': ref('v048', f'/slots/{i}/exact_candidate_applications/{j}')}
        for j, a in enumerate(raw['exact_candidate_applications'])]
    ROWS['v048'].append(r)

AGG = {}
AGG['v045'] = [dict(condition=c, **aggregate([r for r in ROWS['v045'] if r['condition'] == c]))
               for c in ('S1', 'F2', 'O3')]
AGG['v047'] = [dict(condition=x['condition'], team_token_budget=x['team_token_budget'],
    pilot_stage=x['pilot_stage'], source_report_configuration=ref('v047', f'/configuration_table/{i}'),
    **aggregate([r for r in ROWS['v047'] if r['condition'] == x['condition'] and
                 r['team_token_budget'] == x['team_token_budget']]))
    for i, x in enumerate(DATA['v047']['configuration_table'])]
AGG['v048'] = [dict(condition=x['condition'], representation=x['representation'],
    source_report_configuration=ref('v048', f'/configurations/{i}'),
    **aggregate([r for r in ROWS['v048'] if r['condition'] == x['condition'] and
                 r['representation'] == x['representation']]))
    for i, x in enumerate(DATA['v048']['configurations'])]
for version, groups in AGG.items():
    for group in groups:
        peer = next(g for g in groups if g['condition'] == 'S1' and
                    g.get('team_token_budget') == group.get('team_token_budget') and
                    g.get('representation') == group.get('representation'))
        group['mean_complete_cost_ratio_to_same_setting_S1'] = ratio(
            group['mean_complete_actual_tokens'], peer['mean_complete_actual_tokens'])
        group['mean_R_difference_from_same_setting_S1'] = delta(group['R']['mean'], peer['R']['mean'])

matrix = []
for condition in ('S1', 'D2', 'D4', 'I2', 'I4', 'P2', 'P4'):
    row = {'condition': condition}
    for budget in (250000, 500000):
        match = next((g for g in AGG['v047'] if g['condition'] == condition and
                      g['team_token_budget'] == budget), None)
        row[str(budget)] = {'status': 'scheduled', 'aggregate': match} if match else {
            'status': 'not_scheduled', 'fixed_denominator': 0, 'R': None, 'Q': None,
            'complete_actual_tokens': None, 'mean_complete_actual_tokens': None,
            'reason': 'No such condition/budget in the archived fixed configuration table; not zero success.'}
    matrix.append(row)

budget_pairs = []
for pair in DATA['v047']['budget_pair_table']:
    c = pair['condition']
    pairs = []
    for low in [r for r in ROWS['v047'] if r['condition'] == c and r['team_token_budget'] == 250000]:
        high = next(r for r in ROWS['v047'] if r['condition'] == c and
                    r['team_token_budget'] == 500000 and r['root_id'] == low['root_id'])
        pairs.append({'root_id': low['root_id'], 'sampling_seed': low['sampling_seed'],
                      'low_slot_id': low['slot_id'], 'high_slot_id': high['slot_id'],
                      'deltas': {k: delta(high[k], low[k]) for k in (
                          'R', 'Q', 'complete_actual_tokens', 'first_fixed_submit_tokens',
                          'new_births', 'actual_call_members')}})
    budget_pairs.append({'condition': c, 'fixed_root_pair_denominator': len(pairs), 'pairs': pairs,
                         'mean_deltas': {k: mean([p['deltas'][k] for p in pairs]) for k in pairs[0]['deltas']},
                         'derivation': 'Independent high-budget slot minus paired low-budget slot; same root and seed, not continuation.'})

def selected_evidence(version, pointer, rows, fields):
    return [{**{key: r.get(key) for key in fields},
             'provenance': ref(version, f'{pointer}/{i}')}
            for i, r in enumerate(rows)]

file45 = selected_evidence('v045', '/file_level_application_details',
    v45['file_level_application_details'], ('slot_id', 'original_R',
    'effective_nonidentical_partner_file_application', 'producer', 'recipient',
    'recipient_post_import_test_count', 'recipient_post_import_patch_fixed_count',
    'recipient_post_import_submit_count', 'final_fixed_delivery_precedes_import',
    'file_application_linked_to_new_recipient_fixed_delivery', 'interpretation'))
file47 = selected_evidence('v047', '/file_application_review/candidates',
    DATA['v047']['file_application_review']['candidates'], ('slot_id', 'application_kind',
    'world_sequence', 'recipient', 'source_member', 'cross_member', 'status',
    'exact_whole_candidate_adoption', 'changed_paths', 'exact_source_file_paths_applied_nonidentically',
    'recipient_exact_after_tree_test_sequences', 'applied_files_retained_in_later_final_submission',
    'final_submission_after_application', 'scope'))
context48 = selected_evidence('v048', '/context_rejection_process_evidence',
    DATA['v048']['context_rejection_process_evidence'], ('slot_id', 'root_id', 'gamma',
    'call_id', 'member', 'stage_id', 'prompt_tokens', 'output_reservation',
    'context_limit', 'overflow_tokens'))

OUTPUT = {
    'version': 'organization-strategy-read-only-comparison-v1',
    'created_at_utc': datetime.now(timezone.utc).isoformat(), 'sources': SOURCES,
    'script': {'path': str(Path(__file__).resolve()),
               'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    'scope': {'reads_only': list(SOURCES), 'new_model_calls': 0, 'new_tokenizer_calls': 0,
              'new_tests_or_acceptance': 0, 'new_gpu_diagnostics': 0, 'source_mutations': 0,
              'full_fixed_denominators': True,
              'warnings': ['These versions are different protocols and task panels; do not pool as a causal member-count experiment.',
                           'All costs are complete episode token costs including failures, unless explicitly labelled first-submit.',
                           'Q is not present in the v045 canonical row table; null remains unknown.',
                           'Not applicable partner use and not scheduled budget cells are not zero outcomes.',
                           'Cross-member source-file evidence is distinct from the original symbol tracker and from causal benefit.']},
    'execution_record': {'extractor_attempt': 1, 'extractor_initial_failures': [],
        'pre_extraction_environment_failures': [
            {'attempt': n, 'action': 'read-only JSON schema inspection',
             'error': 'bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted',
             'script_started': False, 'files_written': False} for n in (1, 2)],
        'resolution': 'Same authorized read-only commands used escalated execution after sandbox startup failure; no model environment or reports changed.'},
    'v045': {'rows': ROWS['v045'], 'aggregates': AGG['v045'],
        'paired_blocks': v45['paired_blocks'], 'pair_source': ref('v045', '/paired_blocks'),
        'mean_contrasts': v45['full_inventory_mean_contrasts'],
        'mean_contrasts_source': ref('v045', '/full_inventory_mean_contrasts'),
        'independent_file_applications': file45,
        'file_application_summary': v45['file_level_application_summary'],
        'file_application_summary_source': ref('v045', '/file_level_application_summary'),
        'rejections': selected_evidence('v045', '/resource_rejections', v45['resource_rejections'],
                      ('slot_id', 'classification', 'call_id', 'member_id'))},
    'v047': {'rows': ROWS['v047'], 'aggregates': AGG['v047'], 'architecture_budget_matrix': matrix,
        'budget_pairs': budget_pairs,
        'source_budget_pair_table': DATA['v047']['budget_pair_table'],
        'source_budget_pair_table_ref': ref('v047', '/budget_pair_table'),
        'rejection_counts': DATA['v047']['final_cost_delivery_summary']['stop_classifications'],
        'rejection_counts_source': ref('v047', '/final_cost_delivery_summary/stop_classifications'),
        'independent_file_applications': file47,
        'frozen_tracker_use': DATA['v047']['feedback_aggregate']['frozen_tracker_use'],
        'frozen_tracker_use_source': ref('v047', '/feedback_aggregate/frozen_tracker_use')},
    'v048': {'rows': ROWS['v048'], 'aggregates': AGG['v048'],
        'representation_pairs': DATA['v048']['representation_pairs'],
        'representation_pairs_source': ref('v048', '/representation_pairs'),
        'mean_representation_deltas': DATA['v048']['mean_Gamma1_minus_Gamma0_by_architecture'],
        'mean_representation_deltas_source': ref('v048', '/mean_Gamma1_minus_Gamma0_by_architecture'),
        'economics': DATA['v048']['economics'], 'economics_source': ref('v048', '/economics'),
        'rejection_counts': DATA['v048']['known_rejection_counts'],
        'rejection_counts_source': ref('v048', '/known_rejection_counts'),
        'context_rejections': context48},
}

# Necessary extraction consistency only: no new experiment checks or acceptance.
assert {v: len(rows) for v, rows in ROWS.items()} == {'v045': 24, 'v047': 44, 'v048': 8}
assert all(len({r['slot_id'] for r in rows}) == len(rows) for rows in ROWS.values())
OUTPUT['extraction_consistency'] = {'unique_rows': {v: len(rows) for v, rows in ROWS.items()},
    'complete_actual_token_sums': {v: scalar_total([r['complete_actual_tokens'] for r in rows])
                                  for v, rows in ROWS.items()}}
(OUT / 'comparison-data.json').write_text(json.dumps(OUTPUT, ensure_ascii=False, indent=2) + '\n')

lines = ['# 组织策略比较数据摘录', '',
    '只读取 canonical 三份终态 JSON，未运行分析器、分词器、模型、GPU诊断、测试或验收。每个来源有 SHA256；逐槽 field_pointers 与已归档证据指针保留。', '',
    '固定分母包含失败；完整回合 token 与首次固定提交 token 分开。v045 归档逐槽没有 Q，保留 null；S1 伙伴使用不适用，不当作协作失败。', '',
    '| 版本/配置 | 成功/固定分母 | Q均值 | 完整token | 平均完整token | 同设定S1费用倍数 |',
    '|---|---:|---:|---:|---:|---:|']
for v, groups in AGG.items():
    for g in groups:
        label = '/'.join(str(x) for x in (v, g['condition'], g.get('team_token_budget'), g.get('representation')) if x is not None)
        q = 'unknown' if g['Q']['mean'] is None else f"{g['Q']['mean']:.6f}"
        lines.append(f"| {label} | {g['R']['known_sum']}/{g['fixed_denominator']} | {q} | {g['complete_actual_tokens']:,} | {g['mean_complete_actual_tokens']:,.2f} | {g['mean_complete_cost_ratio_to_same_setting_S1']:.4f} |")
lines += ['', 'v047 的 500k D2/I2/P2 未设置，矩阵为 not_scheduled/null，不是 0/4。D2/D4 所有槽实际仍单人，全部新生为0。四对预算配置以同root、同seed独立初态配对，不能解释为原轨迹续跑。', '',
    '| v047预算配置 | 平均ΔR | 平均ΔQ | 平均完整token差(500k−250k) |',
    '|---|---:|---:|---:|']
for pair in budget_pairs:
    d = pair['mean_deltas']
    lines.append(f"| {pair['condition']} | {d['R']:.4f} | {d['Q']:.4f} | {d['complete_actual_tokens']:,.2f} |")
lines += ['', f"v047 归档执行前拒绝：{OUTPUT['v047']['rejection_counts']}。", '',
    'v045 单独文件证据有1次伙伴非同值应用，但固定成功交付早于应用，接收者没有后续复验或新增固定交付；原符号口径不回写。', '',
    'v047 归档6次候选采用中5次非同值、1次采用前已同值；A/LA/I2有具体应用到成功交付链，不能据此单独识别因果收益。', '',
    'v048 两个 Γ0/P4 各3次真实context拒绝；两条 Γ1/P4 均R1，并存在伙伴非同值文件树采用→本人成员同树测试→最终固定交付。完整费用仍含失败与提交后工作，首提交费用不替代全回合费用。', '',
    '建议图1：v047 七架构×两预算的小矩阵，单元格同时写成功/4与平均完整token，500k N2配置用灰色“未设置”。图2：v047配置的成功率—平均完整token散点，按预算分面，用实际人数说明D2/D4。图3：v048四个配对的R与完整费用并列；可用堆叠条分别显示首提交前/后费用，无提交用整体成本且首提交标NA。图4：v045三制度费用条+相同4/8成功标注，不跨版本连接为因果趋势。', '',
    '源文件SHA见 comparison-data.json/sources；报告脚本执行一次。此前两次只读字段浏览被bwrap环境初始化阻断，未启动Python、未写文件；同一读取改走授权执行后完成。', '']
(OUT / 'data-findings.md').write_text('\n'.join(lines))
print(json.dumps(OUTPUT['extraction_consistency'], ensure_ascii=False))
print('Wrote comparison-data.json and data-findings.md')
