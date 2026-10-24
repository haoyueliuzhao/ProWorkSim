"""Read saved REF tool/SDK traces; classify stalls without executing model or tools."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / 'runs/software-benchmark-v056/score-encoding-repair-r1/analysis-r2'
OUT = ROOT / 'artifacts/software-benchmark-v056/failure-analysis-r1'
SDK = ROOT / 'runs/v016-sdk/resident-venv/lib/python3.12/site-packages/openhands/sdk'
VERSION = 'v056-stuck-tool-evidence-r1'


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def text_content(observation):
    return '\n'.join(item.get('text', '') for item in observation.get('content', [])
                     if item.get('type') == 'text')


def action_key(event):
    return {key: event.get(key) for key in ('source', 'thought', 'action', 'tool_name')}


def observation_key(event):
    return {key: event.get(key) for key in ('source', 'observation', 'tool_name')}


def summarize_response(path):
    body = json.loads(Path(path).read_bytes())
    choice = body['choices'][0]
    message = choice['message']
    reasoning = message.get('reasoning') or message.get('reasoning_content') or ''
    return {'source': ref(path), 'response_id': body['id'], 'finish_reason': choice['finish_reason'],
            'content_characters': len(message.get('content') or ''),
            'tool_calls': len(message.get('tool_calls') or []),
            'raw_reasoning_characters': len(reasoning),
            'reasoning_sha256': hashlib.sha256(reasoning.encode()).hexdigest(),
            'raw_reasoning_content_present': message.get('reasoning_content') is not None,
            'completion_tokens': body['usage']['completion_tokens'],
            'reasoning_tokens': (body['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens')}


def mapping_control(output):
    """Pure conversion of one actual saved response through the pinned SDK types."""
    from litellm.types.utils import ModelResponse
    from openhands.sdk.agent.response_dispatch import classify_response
    from openhands.sdk.llm import Message
    path = ROOT / ('runs/software-benchmark-v056/episodes/'
                   '4cf65a707e4e463d54ecc5849af7fee95a421705888ff837b56bad539863a8d1/'
                   'ref-ledger/response-0046.json')
    body = json.loads(path.read_bytes())
    raw = ModelResponse(**body)
    original = Message.from_llm_chat_message(raw.choices[0].message)
    changed = copy.deepcopy(body)
    changed['choices'][0]['message']['reasoning_content'] = changed['choices'][0]['message']['reasoning']
    normalized = Message.from_llm_chat_message(ModelResponse(**changed).choices[0].message)
    def describe(message):
        return {'reasoning_content_characters': len(message.reasoning_content or ''),
                'content_parts': len(message.content), 'tool_calls': len(message.tool_calls or []),
                'classification': str(classify_response(message))}
    value = {'version': VERSION, 'script': ref(__file__), 'saved_response': ref(path),
        'raw_reasoning_characters': len(body['choices'][0]['message']['reasoning']),
        'litellm_extra_reasoning_characters': len(getattr(raw.choices[0].message, 'reasoning', '') or ''),
        'original_sdk_conversion': describe(original), 'field_normalized_conversion': describe(normalized),
        'content_unchanged': original.content == normalized.content,
        'tools_unchanged': original.tool_calls == normalized.tool_calls,
        'raw_response_changed': False, 'model_calls': 0, 'tool_calls': 0, 'scoring_calls': 0,
        'interpretation': 'The current adapter omits normalization from vLLM reasoning to SDK reasoning_content. '
            'This proves information omission, not a measured accuracy effect. Both EMPTY and REASONING_ONLY '
            'receive the same corrective nudge; the monologue detector counts message events regardless '
            'of reasoning content. Action equality compares thought separately and does not compare reasoning_content.'}
    assert value['raw_reasoning_characters'] == 8440
    assert len(original.reasoning_content or '') == 0 and len(normalized.reasoning_content or '') == 8440
    output.mkdir(parents=True, exist_ok=True)
    (output / 'reasoning-mapping-control.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(value, ensure_ascii=False))


def analyze(output):
    classified = list(csv.DictReader((ANALYSIS / 'slot-results.csv').open()))
    closed = [row for row in classified if row['generation_status'] == 'closed']
    assert len(closed) == 186
    rpc_rows, stalled = [], []
    global_types, global_errors, rejection_types = Counter(), Counter(), Counter()
    rejection_examples = {}
    for row in closed:
        episode = Path(row['generation_result']).parent
        path = episode / 'native-rpc-transcript.json'
        transcript = json.loads(path.read_bytes())
        calls = [item for item in transcript if 'request' in item]
        kinds, errors = Counter(), Counter()
        nonzero = nonzero_no_tool_error = timeout = rpc_error = 0
        for item in calls:
            request, response = item['request'], item['response']
            tool = request['tool']
            kinds[tool] += 1
            observation = response.get('observation', {})
            if observation.get('is_error') is True:
                errors[tool] += 1
                feedback = (text_content(observation) + '\n'
                            + str(observation.get('metadata', {}).get('suffix', '')))
                if 'Cannot execute multiple commands at once.' in feedback:
                    rejection = 'terminal_multiple_commands_not_chained'
                elif 'previous command is still running' in feedback:
                    rejection = 'terminal_previous_command_running'
                elif 'No previous running command to interact with.' in feedback:
                    rejection = 'terminal_no_previous_running_command'
                elif tool == 'file_editor':
                    rejection = 'file_editor_argument_rejection'
                else:
                    rejection = 'other_explicit_tool_error'
                rejection_types[rejection] += 1
                rejection_examples.setdefault(rejection, {
                    'slot_id': row['slot_id'], 'transcript': ref(path),
                    'rpc_request_id': request['id'], 'tool': tool,
                    'feedback_excerpt': feedback.strip()[:400]})
            if response.get('type') != 'observation':
                rpc_error += 1
            if tool == 'terminal':
                code = observation.get('exit_code')
                nonzero += type(code) is int and code != 0
                nonzero_no_tool_error += (type(code) is int and code != 0
                                         and observation.get('is_error') is not True)
                timeout += observation.get('timeout') is True
        global_types.update(kinds)
        global_errors.update(errors)
        rpc_rows.append({'slot_id': row['slot_id'], 'condition_id': row['condition_id'],
            'resolved': row['resolved'], 'stop_class': row['stop_class'], 'rpc_calls': len(calls),
            'terminal_calls': kinds['terminal'], 'file_editor_calls': kinds['file_editor'],
            'task_tracker_calls': kinds['task_tracker'], 'observation_is_error_count': sum(errors.values()),
            'terminal_nonzero_exit_observations': nonzero,
            'terminal_nonzero_exit_without_tool_error': nonzero_no_tool_error,
            'terminal_timeout_observations': timeout,
            'rpc_non_observation_count': rpc_error, 'transcript': ref(path)})
        if row['stop_class'] != 'sdk_stuck':
            continue
        stderr = (episode / 'controller.stderr').read_text()
        event_paths = sorted((episode / 'native-conversation').glob('*/events/*.json'))
        events = [json.loads(path.read_bytes()) for path in event_paths]
        recent = events[-20:]
        actions = [event for event in recent if event['kind'] == 'ActionEvent']
        observations = [event for event in recent if event['kind'] == 'ObservationEvent']
        repeated = 0
        if actions and observations:
            for action, observation in zip(reversed(actions), reversed(observations)):
                if action_key(action) != action_key(actions[-1]) or observation_key(observation) != observation_key(observations[-1]):
                    break
                repeated += 1
        reason = 'unspecified'
        if 'Alternating Action, Observation loop' in stderr:
            reason = 'alternating_action_observation'
        elif 'Action, Observation loop' in stderr:
            reason = 'repeated_action_observation'
        elif 'Action, Error loop' in stderr:
            reason = 'repeated_action_error'
        agent_messages = []
        for event in reversed(recent):
            if event['kind'] == 'MessageEvent':
                if event.get('source') == 'agent':
                    agent_messages.append(event)
                elif event.get('source') == 'user':
                    break
            elif event['kind'] != 'CondensationSummaryEvent':
                break
        if reason == 'unspecified' and len(agent_messages) >= 3:
            reason = 'consecutive_agent_messages_without_action'
        assert reason != 'unspecified'
        ledger = json.loads((episode / 'ref-ledger/ledger.json').read_bytes())
        last = actions[-1] if actions else {}
        action = last.get('action', {})
        tool = last.get('tool_name')
        last_rpc = calls[-1] if calls else {}
        last_rpc_observation = last_rpc.get('response', {}).get('observation', {})
        observation = observations[-1].get('observation', {}) if observations else {}
        observation_text = text_content(observation)
        if reason == 'consecutive_agent_messages_without_action':
            subtype = 'reasoning_only_responses_no_action'
        elif tool == 'file_editor' and action.get('command') == 'view':
            subtype = 'repeated_file_view'
        elif tool == 'think':
            subtype = 'repeated_think_tool'
        elif tool == 'terminal' and action.get('command') == 'C-c':
            subtype = 'repeated_interrupt_wait'
        elif tool == 'terminal' and type(last_rpc_observation.get('exit_code')) is int and last_rpc_observation['exit_code'] != 0:
            subtype = 'repeated_terminal_command_nonzero_exit'
        else:
            subtype = 'repeated_terminal_command'
        terminal_messages = list(reversed(agent_messages))[-3:]
        response_ids = {event.get('llm_response_id') for event in terminal_messages}
        matched = [call['response']['path'] for call in ledger['calls']
                   if call['native_attempt_id'] in response_ids]
        terminal_responses = [summarize_response(path) for path in matched]
        if subtype == 'reasoning_only_responses_no_action':
            assert len(terminal_responses) == 3
            assert all(item['content_characters'] == 0 and item['tool_calls'] == 0
                       and item['raw_reasoning_characters'] > 0 for item in terminal_responses)
        else:
            assert repeated >= 4
        sample = {'tool': tool, 'command': action.get('command'), 'path': action.get('path'),
                  'view_range': action.get('view_range'),
                  'action_sha256': hashlib.sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()}
        if sample.get('command') and len(sample['command']) > 320:
            sample['command'] = sample['command'][:320] + '… [see original trace]'
        errors_in_feedback = re.findall(r'(?m)^\w*(?:Error|Exception):[^\n]*', observation_text)
        stalled.append({'slot_id': row['slot_id'], 'instance_id': row['instance_id'],
            'condition_id': row['condition_id'], 'resolved': row['resolved'] == 'True',
            'known_actual_tokens': ledger['known_actual_tokens'], 'token_limit': int(row['token_limit']),
            'remaining_tokens': int(row['token_limit']) - ledger['known_actual_tokens'],
            'attempts': ledger['attempts'], 'sdk_stuck_reason': reason, 'observed_subtype': subtype,
            'tail_identical_action_observation_pairs': repeated,
            'terminal_consecutive_agent_messages': len(agent_messages),
            'last_action_summary': sample, 'last_observation_is_error': observation.get('is_error'),
            'last_rpc_terminal_exit_code': last_rpc_observation.get('exit_code') if tool == 'terminal' else None,
            'last_feedback_head': observation_text[:250], 'last_feedback_tail': observation_text[-350:],
            'last_feedback_exception_lines': errors_in_feedback[-3:],
            'terminal_reasoning_only_responses': terminal_responses,
            'evidence': {'controller_result': ref(episode / 'controller-result.json'),
                         'controller_stderr': ref(episode / 'controller.stderr'),
                         'transcript': ref(path), 'tail_events': [ref(item) for item in event_paths[-8:]]}})
    assert len(stalled) == 26 and sum(item['resolved'] for item in stalled) == 2
    by_condition = {}
    for condition in ('REF_B0500K', 'REF_B2000K', 'REF_B5000K', 'REF_B10000K'):
        subset = [item for item in stalled if item['condition_id'] == condition]
        by_condition[condition] = {'stuck': len(subset), 'resolved': sum(item['resolved'] for item in subset),
            'subtypes': dict(Counter(item['observed_subtype'] for item in subset)),
            'remaining_tokens_min': min(item['remaining_tokens'] for item in subset),
            'remaining_tokens_max': max(item['remaining_tokens'] for item in subset)}
    high = [item for item in stalled if item['condition_id'] in ('REF_B5000K', 'REF_B10000K')]
    mapping_path = output / 'reasoning-mapping-control.json'
    mapping = json.loads(mapping_path.read_bytes())
    assert mapping['script'] == ref(__file__)
    value = {'version': VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'sources': {'classification': ref(ANALYSIS / 'slot-results.csv'),
                    'state': ref(ANALYSIS / 'source-state.json'), 'script': ref(__file__),
                    'stuck_detector': ref(SDK / 'conversation/stuck_detector.py'),
                    'thresholds': ref(SDK / 'conversation/types.py'),
                    'response_dispatch': ref(SDK / 'agent/response_dispatch.py'),
                    'message_mapping': ref(SDK / 'llm/message.py'),
                    'exact_adapter': ref(ROOT / 'src/proworksim/software_benchmark_exact_transport_v054.py')},
        'stuck_total': len(stalled), 'stuck_resolved': sum(item['resolved'] for item in stalled),
        'stuck_known_failures': sum(not item['resolved'] for item in stalled),
        'by_condition': by_condition,
        'reason_counts': dict(Counter(item['sdk_stuck_reason'] for item in stalled)),
        'subtype_counts': dict(Counter(item['observed_subtype'] for item in stalled)),
        'high_budget': {'episodes': len(high), 'resolved': sum(item['resolved'] for item in high),
                       'subtype_counts': dict(Counter(item['observed_subtype'] for item in high))},
        'rpc_metrics': {'closed_episode_count': 186, 'calls_by_tool': dict(global_types),
            'observation_is_error_by_tool': dict(global_errors),
            'episodes_with_is_error_observation': sum(item['observation_is_error_count'] > 0 for item in rpc_rows),
            'rpc_non_observation_responses': sum(item['rpc_non_observation_count'] for item in rpc_rows),
            'terminal_nonzero_exit_observations': sum(item['terminal_nonzero_exit_observations'] for item in rpc_rows),
            'terminal_nonzero_exit_without_tool_error': sum(item['terminal_nonzero_exit_without_tool_error'] for item in rpc_rows),
            'terminal_timeout_observations': sum(item['terminal_timeout_observations'] for item in rpc_rows),
            'explicit_rejection_types': dict(rejection_types),
            'rejection_examples': rejection_examples},
        'reasoning_mapping_control': ref(mapping_path), 'stuck_episodes': stalled,
        'interpretation': [
            'Stuck is the SDK observed stop state, not automatically a host/tool fault or incorrect candidate.',
            '23 repeated-action episodes reproduce at least four identical action/observation pairs at the end; no action-error-loop or alternating-loop stop was observed.',
            'Three stalls end with reasoning-only responses and no action/content. Some responses hit the per-call 32768 output limit while other reasoning-only responses finish normally.',
            'Repeated terminal nonzero exit is a command/program outcome, not itself an interface failure; successful reads and think responses can also form loops.',
            'Remote RPC metrics exclude SDK-local think/finish and do not count tests from shell-command regexes.',
            'A nonzero exit observation can also be a rejected command (-1); counts excluding is_error are provided separately. Neither number is a public-test failure count.',
            'The reasoning field omission is confirmed by CPU conversion, but the accuracy effect is not measured. Mapping it does not itself create a missing action or remove SDK monologue detection.',
            'These are observed mechanisms and associations, not counterfactual estimates of recovered successes.'],
        'model_calls': 0, 'scoring_calls': 0, 'public_test_executions': 0}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'stuck-tools.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    with (output / 'tool-rpc-counts.csv').open('w', newline='') as stream:
        flat = [{**item, 'transcript': json.dumps(item['transcript'])} for item in rpc_rows]
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(flat)
    print(json.dumps({key: value[key] for key in ('stuck_total', 'reason_counts', 'subtype_counts',
                                                'by_condition', 'rpc_metrics')}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--mapping-control', action='store_true')
    args = parser.parse_args()
    if args.mapping_control:
        mapping_control(args.output)
    else:
        analyze(args.output)


if __name__ == '__main__':
    main()
