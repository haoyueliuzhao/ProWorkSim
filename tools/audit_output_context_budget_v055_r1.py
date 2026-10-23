"""Budget decomposition from sealed metadata plus one narrow SDK-limit witness."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
EVIDENCE = ROOT / 'artifacts/software-benchmark-v055/score-gap-evidence-r1'
OUT = ROOT / 'artifacts/software-benchmark-v055/budget-constraint-audit-r1'


def ref(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def read(path):
    return json.loads(Path(path).read_bytes())


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def main():
    summary_path = EVIDENCE / 'summary.json'
    summary = read(summary_path)
    metadata = read(summary['normal_closed_slot_metadata']['path'])
    format_path = EVIDENCE / 'project-format-shapes.json'
    formatting = read(format_path)
    groups = {}
    for group, body in summary['groups'].items():
        rows = [row for row in metadata if row['group'] == group]
        metrics = body['metrics']
        def total(key):
            return metrics[key].get('sum', 0) or 0
        agent_calls, condenser_calls = total('agent_calls'), total('condenser_calls')
        agent_tokens = total('agent_prompt_tokens') + total('agent_completion_tokens')
        condenser_tokens = total('condenser_prompt_tokens') + total('condenser_completion_tokens')
        measured_tokens = agent_tokens + condenser_tokens
        if measured_tokens != total('tokens') or len(rows) != body['normal_closed_included']:
            raise ValueError('Existing grouped metadata no longer reconciles its original normal-closed rows')
        is_ref = group.endswith(':REF') or ':REF-' in group
        entry = {
            'planned_task_denominator': 500,
            'primary_normal_closed_task_denominator': len(rows),
            'scope_excludes_original_generation_unknowns_and_later_preentry_recovery': True,
            'limits': {'episode_input_plus_completion_tokens': 500000,
                'all_model_attempts_including_condenser': 128, 'agent_decisions': 128,
                'context_total_tokens': 131072 if is_ref else 18432,
                'maximum_input_tokens': 98304 if is_ref else 16384,
                'maximum_single_completion_tokens': 32768 if is_ref else 2048,
                'reasoning_tokens_are_inside_completion_limit': True},
            'actual_tokens_from_measured_call_usage': measured_tokens,
            'agent': {'measured_calls': agent_calls, 'prompt_tokens': total('agent_prompt_tokens'),
                'completion_tokens': total('agent_completion_tokens'), 'actual_tokens': agent_tokens,
                'mean_prompt_tokens_per_measured_call': fraction(total('agent_prompt_tokens'), agent_calls),
                'calls_equal_single_output_cap': total('agent_outputs_at_cap'),
                'fraction_calls_equal_single_output_cap': fraction(total('agent_outputs_at_cap'), agent_calls),
                'tasks_with_any_call_equal_single_output_cap': body['episode_counts']['agent_outputs_at_cap'],
                'fraction_normal_closed_tasks_with_any_call_equal_single_output_cap': fraction(
                    body['episode_counts']['agent_outputs_at_cap'], len(rows)),
                'calls_above_single_output_cap': total('agent_outputs_over_cap')},
            'condenser': {'measured_calls': condenser_calls,
                'tasks_with_calls': body['episode_counts']['condenser_calls'],
                'calls_per_normal_closed_task_median': metrics['condenser_calls']['median'],
                'prompt_tokens': total('condenser_prompt_tokens'),
                'completion_tokens': total('condenser_completion_tokens'), 'actual_tokens': condenser_tokens,
                'share_of_all_measured_tokens': fraction(condenser_tokens, measured_tokens),
                'share_of_all_measured_model_calls': fraction(condenser_calls, agent_calls + condenser_calls),
                'calls_equal_output_cap': total('condenser_outputs_at_cap'),
                'tasks_with_any_call_equal_output_cap': sum(row['condenser_outputs_at_cap'] > 0 for row in rows),
                'response_shape_audited': group.startswith('DeepSeek:'),
                'empty_content_calls': total('condenser_empty_content') if group.startswith('DeepSeek:') else None,
                'tasks_with_empty_content': body['episode_counts']['condenser_empty_content'] if group.startswith('DeepSeek:') else None,
                'finish_reason_length_calls': total('condenser_length_finish') if group.startswith('DeepSeek:') else None,
                'tasks_with_finish_reason_length': sum(row['condenser_length_finish'] > 0 for row in rows) if group.startswith('DeepSeek:') else None},
            'attempt_count': metrics['attempts'], 'decision_count': metrics['decisions'],
            'direct_context_boundary_observed_task_count': sum(
                'context' in str(row['terminal_reason']) or 'context_capacity' in row.get('terminal_limits', []) for row in rows),
            'direct_context_boundary_scope': 'Direct final boundary only; context-driven condensation can occur without this terminal reason',
        }
        if group in formatting['groups']:
            recorded = formatting['groups'][group]
            entry['project_recoverable_other_format_rejections'] = {
                **recorded,
                'fraction_normal_closed_tasks_affected': fraction(recorded['episodes'], len(rows)),
                'fraction_rejected_call_completion_tokens_reported_as_reasoning': fraction(
                    recorded['reasoning_tokens'], recorded['completion_tokens']),
                'not_generation_integrity_unknowns': True,
            }
        groups[group] = entry
    witness_row = next(row for row in metadata if row['slot_id'] == 'v055-MATCH-thinking-pylint-dev__pylint-7080')
    controller_path = Path(witness_row['controller']['path'])
    controller = read(controller_path)
    ledger = controller['ledger']
    stderr_path = controller_path.with_name('controller.stderr')
    stderr = stderr_path.read_bytes()
    tail = stderr[-5500:].decode('utf-8', errors='replace')
    state_path = controller_path.parent / 'native-conversation/9b01404949764604be07251f6788502a/base_state.json'
    state = read(state_path)
    if 'iterations limit (128)' not in tail or state.get('execution_status') != 'error':
        raise ValueError('The narrow SDK iteration-limit witness changed')
    witness = {'slot_id': witness_row['slot_id'],
        'selection': 'Only existing normal-closed metadata row with recorded attempts >=128; not selected by score',
        'controller': witness_row['controller'], 'stderr': ref(stderr_path), 'sdk_state': ref(state_path),
        'controller_status': controller['status'], 'controller_terminal_boundary': controller.get('terminal_boundary'),
        'actual_model_calls': controller['actual_model_calls'], 'attempts': ledger['attempts'],
        'decisions': ledger['decisions'], 'purpose_call_counts': dict(Counter(call['usage_id'] for call in ledger['calls'])),
        'known_actual_tokens': ledger['known_actual_tokens'], 'complete_actual_tokens': ledger['complete_actual_tokens'],
        'uncertain_reserved_tokens': ledger['uncertain_reserved_tokens'],
        'sdk_execution_status': state['execution_status'], 'sdk_max_iterations': state['max_iterations'],
        'explicit_sdk_limit_log': '[10/22/26 15:48:23] Agent reached maximum iterations limit (128).',
        'last_repeated_condenser_context_observations': {'observed_token_range_in_last_5500_bytes': [16541, 16566],
            'max_tokens': 16384, 'events': 5},
        'last_three_request_references': [call['request'] for call in ledger['calls'][-3:]],
        'last_three_requests_identical_SHA': len({call['request']['sha256'] for call in ledger['calls'][-3:]}) == 1,
        'interpretation': 'Explicit SDK iteration limit after repeated still-over-context condensation. No adapter all_model_attempt_limit rejection is recorded; preserve the original null controller boundary and add this independent explanation.',
        'original_queue_or_controller_modified': False,
    }
    value = {'version': 'v055-output-context-budget-evidence-r1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'source': ref(__file__), 'existing_sources': [ref(summary_path), ref(format_path),
            ref(EVIDENCE/'qwen-cost-and-schema.json'), ref(summary['normal_closed_slot_metadata']['path'])],
        'original_primary_normal_closed_rows': 4324, 'groups': groups,
        'historical_generation_unknown_JSON_failure_shapes_separate_population': summary['deepseek_JSON_failure_shape_counts'],
        'condenser_empty_output_mechanical_witness': summary['samples']['DeepSeek:MATCH-thinking:first_empty_condenser'],
        'single_sdk_iteration_limit_witness': {**witness, 'role': 'ancillary MATCH-only diagnosis; not evidence about REF'},
        'latest_user_focus_reference_conditions': {
            key: {'scope': 'original primary normal-closed only; later pre-entry recovery separate',
                'normal_closed_task_denominator': value['primary_normal_closed_task_denominator'],
                'planned_task_denominator': 500,
                'actual_measured_calls': value['agent']['measured_calls'],
                'calls_equal_32768_output_cap': value['agent']['calls_equal_single_output_cap'],
                'tasks_with_cap_equality': value['agent']['tasks_with_any_call_equal_single_output_cap'],
                'explicit_finish_reason_length_count': None,
                'finish_reason_scope': 'Not retained in the existing aggregate; no new broad REF scan',
                'condenser_calls': value['condenser']['measured_calls'],
                'attempt_maximum_observed': value['attempt_count']['max'],
                'episode_actual_token_distribution': summary['groups'][key]['metrics']['tokens'],
                'normal_boundary_reason_counts': summary['groups'][key]['terminal_reason_counts']}
            for key, value in groups.items() if ':REF' in key},
        'interpretation_limits': [
            'Episode500000, context16384/98304 input and completion2048/32768 are distinct constraints.',
            'Output equals cap is an exposure proxy, not proof of truncation or task failure; use explicit length/parser evidence when available.',
            'Condenser actual-token shares are small relative to total in Qwen/MATCH-nonthinking; do not describe them as the majority of token spending.',
            'Model attempts consumed by condensation are measured; the number of counterfactual productive Agent actions or extra resolved tasks is not identifiable.',
            'Qwen condenser content/finish_reason was not audited by prior shape extraction; null must not be reported as zero empty summaries.',
            'Controller return without an explicit limit boundary does not establish SDK success or voluntary Agent finish.',
            'The single SDK-limit witness does not reclassify other no-boundary episodes, and original records remain unchanged.',
            'Normal-closed rows exclude original unknowns and subsequent pre-entry recovery; do not combine the separate JSON-failure last-response population into these call denominators.',
            'No output/context budget ablation was performed; causal score recovery from increased limits remains unknown.'
        ],
        'additional_large_trajectory_scan': False, 'single_witness_read_scope': 'One167969B controller, one103123B stderr and one3061B SDK base_state; no events/messages/rootfs',
        'model_calls': 0, 'test_executions': 0, 'scoring_calls': 0, 'GPU_queries': 0}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/'output-context-evidence.json').open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
    with (OUT/'pylint7080-sdk-limit-stderr-tail.txt').open('x') as stream:
        stream.write(tail)
    print(json.dumps({'path': str(OUT/'output-context-evidence.json'),
        'normal_closed_rows': 4324, 'sdk_iteration_limit_witness': witness['slot_id'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
