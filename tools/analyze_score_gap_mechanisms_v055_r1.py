"""Read-only descriptive mechanism audit; no inference, tests, scoring or state writes."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/score-gap-evidence-r1'
ART = ROOT / 'artifacts/software-benchmark-v055/score-gap-evidence-r1'
READ = Counter()


def read(path):
    path = Path(path)
    data = path.read_bytes()
    READ['files'] += 1
    READ['bytes'] += len(data)
    return json.loads(data)


def ref(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def distribution(values):
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {'n': 0}
    ordered = sorted(values)
    return {'n': len(values), 'sum': sum(values), 'median': statistics.median(values),
        'mean': statistics.mean(values), 'p25': ordered[(len(ordered)-1)//4],
        'p75': ordered[3*(len(ordered)-1)//4], 'min': min(values), 'max': max(values)}


def main():
    OUT.mkdir(exist_ok=False)
    ART.mkdir(parents=True, exist_ok=False)
    rows, errors, samples, sources = [], [], {}, []
    for family, queue in [('Qwen', ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json'),
                          ('DeepSeek', ROOT/'runs/software-benchmark-v055/queue-r1/state.json')]:
        state = read(queue)
        sources.append(ref(queue))
        for row in state['rows']:
            if row['generation']['status'] != 'closed':
                continue
            slot = row['slot']
            group = family + ':' + slot.get('condition_id', slot['arm'])
            try:
                result = read(row['generation']['result']['path'])
                cr = result.get('controller_result') or row['generation'].get('controller_result')
                controller = read(cr['path'])
                ledger = controller['ledger']
                managed = controller.get('managed_ledger', ledger).get('model', {})
                calls = ledger.get('calls', [])
                cap = 32768 if slot['arm'] == 'REF' else 2048
                terminal = controller.get('terminal_boundary')
                if isinstance(terminal, dict):
                    terminal = terminal.get('reason')
                value = {'slot_id': slot['slot_id'], 'instance_id': slot['instance_id'], 'group': group,
                    'controller': cr, 'controller_version': controller.get('version'), 'primary_generation_status': 'closed',
                    'terminal_reason': terminal or 'SDK_returned_without_explicit_limit_boundary',
                    'attempts': ledger.get('attempts', managed.get('attempts')),
                    'decisions': ledger.get('decisions', managed.get('decisions')),
                    'tokens': ledger.get('known_actual_tokens', managed.get('charged_tokens')),
                    'complete_tokens': ledger.get('complete_actual_tokens'),
                    'tool_calls_native': controller.get('tool_calls'), 'actions_project': controller.get('actions'),
                    'opportunities_project': controller.get('opportunities'),
                    'managed_public_test_calls': result.get('public_test_calls'),
                    'agent_calls': 0, 'condenser_calls': 0, 'agent_prompt_tokens': 0, 'agent_completion_tokens': 0,
                    'condenser_prompt_tokens': 0, 'condenser_completion_tokens': 0, 'reasoning_tokens': 0,
                    'agent_outputs_at_cap': 0, 'agent_outputs_over_cap': 0, 'condenser_outputs_at_cap': 0,
                    'condenser_empty_content': 0, 'condenser_length_finish': 0, 'condenser_response_count': 0,
                    'last_prompt_tokens': None, 'maximum_output_tokens': cap}
                if not calls and managed:
                    calls = [{'usage_id': 'agent', 'usage': record.get('charge', {}).get('reported_usage', {})}
                        for record in managed['records'].values() if record.get('charge', {}).get('reported_usage')]
                for call in calls:
                    kind = call.get('usage_id', 'agent')
                    if kind not in {'agent', 'condenser'}:
                        continue
                    usage = call.get('usage', {})
                    if not usage:
                        continue
                    value[kind + '_calls'] += 1
                    value[kind + '_prompt_tokens'] += usage.get('prompt_tokens', 0)
                    value[kind + '_completion_tokens'] += usage.get('completion_tokens', 0)
                    value['reasoning_tokens'] += usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)
                    value[kind + '_outputs_at_cap'] += usage.get('completion_tokens') == cap
                    if kind == 'agent':
                        value['agent_outputs_over_cap'] += usage.get('completion_tokens', 0) > cap
                    value['last_prompt_tokens'] = usage.get('prompt_tokens')
                    if kind == 'condenser' and family == 'DeepSeek' and call.get('response'):
                        response = read(call['response']['path'])
                        choice = response['choices'][0]
                        content = choice.get('message', {}).get('content')
                        empty = content is None or not content.strip()
                        value['condenser_response_count'] += 1
                        value['condenser_empty_content'] += empty
                        value['condenser_length_finish'] += choice.get('finish_reason') == 'length'
                        if empty and group + ':first_empty_condenser' not in samples:
                            samples[group + ':first_empty_condenser'] = {'selection': 'first in frozen queue order',
                                'slot_id': slot['slot_id'], 'response': call['response'], 'usage': usage,
                                'finish_reason': choice.get('finish_reason'), 'content_empty': True,
                                'message_or_reasoning_text_exported': False}
                if slot['arm'] == 'PROJECT':
                    boundary_path = Path(cr['path']).parent/'managed-boundary.json'
                    boundary = read(boundary_path)
                    stops = boundary.get('role_stops', {})
                    value['terminal_reason'] = '|'.join(sorted(set(stops.values()))) or boundary.get('closure_reason')
                    details = boundary.get('terminal_details', {})
                    value['terminal_limits'] = sorted({item for member in details.values() for item in member.get('limits', [])})
                    policy = boundary.get('action_error_policy', {})
                    for name in ('recoverable_unknown_names', 'recoverable_argument_errors', 'other_format_errors', 'process_violation_count'):
                        value[name] = policy.get(name, 0)
                    value['argument_constraint_counts'] = dict(Counter(str(item.get('parser_failure', {}).get('constraint')) for item in policy.get('argument_rejections', [])))
                    value['outcome_status_counts'] = dict(Counter(item.get('status', 'unknown') for item in boundary.get('outcomes', [])))
                    value['business_error_code_counts'] = dict(Counter(str(item.get('response', {}).get('error', {}).get('code'))
                        for item in boundary.get('outcomes', []) if isinstance(item.get('response', {}).get('error'), dict)))
                    value['administrative_censoring'] = boundary.get('administrative_censoring')
                    value['soft_cutoff'] = boundary.get('deadline_receipt', {}).get('actual_soft_cutoff_triggered')
                    value['remaining_tokens_managed'] = managed.get('available_tokens')
                    sample_key = group + ':first_project_boundary'
                    if sample_key not in samples:
                        samples[sample_key] = {'selection': 'first normal closed slot in frozen queue order',
                            'slot_id': slot['slot_id'], 'path': str(boundary_path), 'role_stops': stops,
                            'terminal_details': details, 'opportunities': boundary.get('opportunities'),
                            'actions': boundary.get('actions'), 'public_test_calls': result.get('public_test_calls')}
                if isinstance(value['tokens'], (int, float)):
                    value['unspent_of_500000'] = 500000 - value['tokens']
                rows.append(value)
            except Exception as error:
                errors.append({'slot_id': slot['slot_id'], 'group': group, 'type': type(error).__name__, 'error': str(error)})
    groups = {}
    for group in sorted({row['group'] for row in rows}):
        selected = [row for row in rows if row['group'] == group]
        numeric = ('attempts', 'decisions', 'tokens', 'unspent_of_500000', 'agent_calls', 'condenser_calls',
            'tool_calls_native', 'actions_project', 'opportunities_project', 'managed_public_test_calls',
            'recoverable_unknown_names', 'recoverable_argument_errors', 'other_format_errors',
            'agent_prompt_tokens', 'agent_completion_tokens', 'condenser_prompt_tokens', 'condenser_completion_tokens',
            'reasoning_tokens', 'agent_outputs_at_cap', 'agent_outputs_over_cap', 'condenser_outputs_at_cap',
            'condenser_empty_content', 'condenser_response_count', 'condenser_length_finish')
        groups[group] = {'normal_closed_included': len(selected),
            'terminal_reason_counts': dict(Counter(row['terminal_reason'] for row in selected)),
            'controller_versions': dict(Counter(row['controller_version'] for row in selected)),
            'metrics': {key: distribution([row.get(key) for row in selected]) for key in numeric},
            'episode_counts': {key: sum(bool(row.get(key)) for row in selected) for key in
                ('condenser_calls', 'condenser_empty_content', 'agent_outputs_at_cap', 'recoverable_unknown_names',
                 'recoverable_argument_errors', 'other_format_errors', 'managed_public_test_calls', 'soft_cutoff')},
            'project_terminal_limit_counts': dict(Counter(item for row in selected for item in row.get('terminal_limits', []))),
            'project_outcome_status_counts': dict(sum((Counter(row.get('outcome_status_counts', {})) for row in selected), Counter())),
            'project_argument_constraint_counts': dict(sum((Counter(row.get('argument_constraint_counts', {})) for row in selected), Counter())),
            'project_business_error_code_counts': dict(sum((Counter(row.get('business_error_code_counts', {})) for row in selected), Counter()))}
    audit_path = ROOT/'artifacts/software-benchmark-v055/exception-reconciliation-r1/deepseek-generation-audit.json'
    audit = read(audit_path)
    json_shape = defaultdict(Counter)
    for row in audit['rows']:
        if row['category'] != 'provider_tool_arguments_json_parse_failed':
            continue
        shape = row.get('last_retained_response_shape', {})
        count = json_shape[row['condition_id']]
        count['JSON_parse_unknowns'] += 1
        count.update({'finish_' + reason: 1 for reason in shape.get('finish_reasons', [])})
        usage = shape.get('usage', {})
        count['reasoning_tokens_in_last_response'] += usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)
        count['completion_tokens_in_last_response'] += usage.get('completion_tokens', 0)
    write(OUT/'normal-closed-slot-metadata.json', rows)
    summary = {'version': 'v055-score-gap-evidence-r1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'source': ref(__file__), 'primary_queues': sources, 'normal_closed_rows': len(rows), 'errors': errors,
        'normal_closed_slot_metadata': ref(OUT/'normal-closed-slot-metadata.json'), 'groups': groups, 'samples': samples,
        'deepseek_generation_unknown_audit': ref(audit_path),
        'deepseek_unknown_condition_category_counts': audit['condition_category_counts'],
        'deepseek_JSON_failure_shape_counts': {key: dict(value) for key, value in json_shape.items()},
        'read_volume': dict(READ), 'model_calls': 0, 'scoring_calls': 0, 'test_executions': 0,
        'interpretation': ['Descriptive primary normal-closed subset; not a per-condition 500-task score estimate',
            'Unknown generation slots use existing audit; six later pre-entry recovery slots are a separate layer',
            'No causal attribution from condition means, cap equality is a bounded-output proxy, no success selected cases',
            'Native managed_public_test_calls=0 does not imply no tests through Terminal',
            'Raw model messages, reasoning text, source trees and large experiences are not exported']}
    write(OUT/'summary.json', summary)
    write(ART/'summary.json', summary)
    print(json.dumps({'normal_closed_rows': len(rows), 'errors': errors, 'read_volume': dict(READ), 'summary': str(OUT/'summary.json')}))


if __name__ == '__main__':
    main()
