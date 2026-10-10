"""Close saved v045 CPU evidence and add only eight missing initial shapes.

The original twelve runtimes stay closed. Their 36 programmed responses and
actual encodings are read only. Each supplemental two-member unit gets a fresh
world and one opportunity for its previously unmeasured initial member.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]
VERSION = 'software-organization-cpu-evidence-repair-v0.45'
ENTRY_FILES = ('event_time.py', 'event_store.py', 'rules.py', 'migration.py')
STAGES = ('initial_read', 'public_test', 'consume_exact_home')


def checked(ref):
    path = Path(ref['path'])
    if digest(path.read_bytes()) != ref['sha256']:
        raise ValueError('Source changed: ' + str(path))
    return path


def unique(rows, kind, call_id, stage=None):
    found = [row for row in rows if row['kind'] == kind
             and (row['payload'].get('call_id') == call_id
                  or row['payload'].get('model_call_id') == call_id)
             and (stage is None or row['payload'].get('stage') == stage)]
    if len(found) != 1:
        raise ValueError(f'Expected exactly one {kind}/{stage}/{call_id}: {len(found)}')
    return found[0]


def stage_review(folder, row, response, snapshot, events, index):
    refs = {Path(ref['path']).name: ref for ref in row['artifacts']}
    for ref in [*row['artifacts'], row['measurement_ref']]:
        checked(ref)
    raw = folder / 'raw-transport' / f'request-{index + 1:05d}'
    selected = read_json(checked(refs['selected-request.json']))
    encoding = read_json(checked(refs['selected-encoding.json']))
    ids = read_json(checked(refs['selected-input-ids.json']))
    transport = read_json(raw / 'response.json')
    body = transport['body']
    budget = snapshot['team_budget']['records'][row['call_id']]
    preparation = budget['reservation']['preparation']
    turn = read_json(raw / 'runner-turn.json')
    started = unique(events, 'model_call', row['call_id'], 'started')
    finished = unique(events, 'model_call', row['call_id'], 'finished')
    output = unique(events, 'model_response', row['call_id'])
    action = unique(events, 'tool_call', row['call_id'])
    link = unique(events, 'model_action_link', row['call_id'])
    feedback = unique(events, 'model_tool_result', row['call_id'])
    expected = row['programmed_action']
    actual = action['payload']
    choice = body['choices'][0]['message']['tool_calls'][0]
    usage = response['usage']
    checks = {
        'saved_artifacts_hash_bound': True,
        'member_and_call_bound': turn['member_id'] == row['member']
            and turn['association']['call_id'] == row['call_id']
            and all(x['worker_id'] == row['member'] for x in (started, finished, output, action, link, feedback)),
        'selected_request_equal_transport': selected == read_json(raw / 'selected-request.json'),
        'saved_actual_encoding_bound': encoding['native_projection']['request_sha256'] == refs['selected-request.json']['sha256']
            and encoding['input_ids_sha256'] == refs['selected-input-ids.json']['sha256']
            and encoding['rendered_prompt_sha256'] == refs['selected-native-prompt.txt']['sha256'],
        'selected_ids_equal_actual_program_trace': ids == body['token_trace']['input_ids']
            and len(ids) == row['prompt_tokens'] == encoding['prompt_tokens'] == usage['prompt_tokens'],
        'actual_hard_capacity_fit': row['selected_hard_capacity_passed'] is True
            and len(ids) + row['reserved_output_tokens'] <= row['context_limit']
            and row['headroom_tokens'] == row['context_limit'] - len(ids) - row['reserved_output_tokens'],
        'original_preservation_checks': all(v is True for v in row['preservation_checks'].values())
            and all(v is True for v in row['protected_preservation_checks'].values()),
        'program_response_bound': digest(json_bytes(body)) == response['response_body_sha256']
            and body['id'] == response['response_id']
            and body == output['payload']['response'] and body['usage'] == usage,
        'native_action_exact': choice['function']['name'] == expected['name']
            and json.loads(choice['function']['arguments']) == expected['arguments']
            and actual['action'] == expected['name'] and actual['arguments'] == expected['arguments']
            and finished['payload']['proposed_action'] == {'action': expected['name'], 'arguments': expected['arguments']},
        'world_action_and_feedback_bound': actual['response']['ok'] is True
            and actual['response'] == link['payload']['world_response'] == feedback['payload']['world_response']
            and json.loads(feedback['payload']['message']['content']) == actual['response']
            and action['sequence'] < link['sequence'] < feedback['sequence'],
        'one_settled_program_response': budget['member'] == row['member'] and budget['status'] == 'settled'
            and budget['attempt_started'] is True and budget['charge']['response_id'] == response['response_id']
            and budget['charge']['reported_usage'] == usage
            and budget['charge']['charged_tokens'] == usage['total_tokens'],
        'original_reservation_bound': preparation['selected_request_sha256'] == refs['selected-request.json']['sha256']
            and preparation['input_ids_sha256'] == refs['selected-input-ids.json']['sha256']
            and preparation['prompt_tokens'] == len(ids) and preparation['fits'] is True,
        'program_output_exactly_accounted': usage['completion_tokens'] == len(body['token_trace']['output_ids'])
            and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'],
        'cpu_fixture_only': row['model_generated'] is False and row['origin'] == 'cpu_programmed_fixture'
            and body['cpu_program_provenance'] == {'model_generated': False, 'model_calls': 0, 'weights_loaded': False},
    }
    return {'stage': row['stage'], 'member': row['member'], 'call_id': row['call_id'],
        'passed': all(checks.values()), 'checks': checks, 'actual_world_response': actual['response'],
        'selected_request': refs['selected-request.json'], 'actual_encoding': refs['selected-encoding.json'],
        'measurement': row['measurement_ref'], 'raw_response': reference(raw / 'response.json'),
        'runner_turn': reference(raw / 'runner-turn.json'),
        'event_sequences': {name: event['sequence'] for name, event in
            [('started', started), ('finished', finished), ('response', output), ('action', action), ('link', link), ('feedback', feedback)]},
        'programmed_usage': usage}


def original_review(original_ref, unit, root_index, output):
    started = time.monotonic()
    folder = checked(original_ref).parent
    route = read_json(folder / 'route.json')
    events = [json.loads(line) for line in (folder / 'runtime/experience.jsonl').read_text().splitlines()]
    actions = read_json(folder / 'program-actions.json')
    measurements, responses, snapshot = route['measurements'], route['programmed_responses'], route['runtime_snapshot']
    reviews = [stage_review(folder, row, response, snapshot, events, i)
               for i, (row, response) in enumerate(zip(measurements, responses))]
    home = reviews[1]['actual_world_response']
    selected = read_json(checked(reviews[2]['selected_request']))
    home_messages = []
    for index, message in enumerate(selected['messages']):
        if message.get('role') != 'tool':
            continue
        try:
            if json.loads(message.get('content', '')) == home:
                home_messages.append(index)
        except (TypeError, ValueError):
            pass
    labels = ['member_001'] if unit['condition'] == 'S1' else ['member_001', 'member_002']
    state = read_json(folder / 'prepared/world/control/state.json')
    test_events = [e for e in state['software_events'] if e['kind'] == 'test']
    checks = {
        'original_declared_postcheck_error_only': route['passed'] is False
            and route['failure'] == {'type': 'AttributeError', 'message': "'str' object has no attribute 'read_text'"},
        'route_identity_exact': route['route_id'] == unit['root_label'] + '-' + unit['condition']
            and route['case_id'] == unit['case_id'] and route['condition'] == unit['condition']
            and route['first_member'] == unit['first_member'],
        'three_original_requests_and_responses': len(measurements) == len(responses) == len(reviews) == 3,
        'three_expected_stages_and_actor': [r['stage'] for r in measurements] == list(STAGES)
            and all(r['member'] == unit['first_member'] for r in measurements),
        'three_native_actions_bound': all(r['passed'] for r in reviews),
        'three_actions_are_original_program': [r['programmed_action'] for r in measurements] == [
            {'name': 'read_file', 'arguments': {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30}},
            {'name': 'run_tests', 'arguments': {}},
            {'name': 'read_file', 'arguments': {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30}}],
        'first_two_original_action_checks_retained': len(actions) == 2
            and all(all(v is True for v in action['checks'].values()) for action in actions)
            and all(action['outcome']['response'] == reviews[i]['actual_world_response'] for i, action in enumerate(actions)),
        'exact_original_test_home_consumed': len(home_messages) == 1 and home['ok'] is True
            and home['result']['version'] == 'paged-public-test-feedback-v0.42'
            and home['result']['page']['index'] == 0,
        'population_unchanged': route['initial_labels'] == snapshot['labels'] == labels,
        'three_completed_opportunities': snapshot['actions'] == snapshot['opportunities'] == 3,
        'three_calls_charged_once': snapshot['team_budget']['decisions'] == snapshot['team_budget']['attempts'] == 3
            and snapshot['team_budget']['held_tokens'] == 0 and snapshot['team_budget']['integrity_failure'] is None
            and snapshot['team_budget']['charged_tokens'] == sum(r['usage']['total_tokens'] for r in responses),
        'one_public_test': len(test_events) == 1 and test_events[0]['public_execution']['execution']['executed'] is True,
        'no_models': route['new_model_calls'] == 0 and route['model_weights_loaded'] is False,
    }
    review = {'version': VERSION, 'route_id': route['route_id'], 'passed': all(checks.values()), 'checks': checks,
        'original_failure': route['failure'], 'old_requests_not_retokenized': True,
        'original_route': original_ref, 'original_actions': reference(folder / 'program-actions.json'),
        'original_experience': reference(folder / 'runtime/experience.jsonl'),
        'original_world_state': reference(folder / 'prepared/world/control/state.json'),
        'stages': reviews, 'exact_home_selected_message_indices': home_messages,
        'original_cost': {'prepared_requests': 3, 'programmed_responses': 3,
            'programmed_prompt_tokens': sum(r['usage']['prompt_tokens'] for r in responses),
            'programmed_output_tokens': sum(r['usage']['completion_tokens'] for r in responses),
            'programmed_charged_tokens': snapshot['team_budget']['charged_tokens'],
            'run_tests': len(test_events), 'public_test_driver_executions': len(test_events),
            'public_test_sandbox_seconds': sum(e['public_execution']['execution']['elapsed_seconds'] for e in test_events),
            'environment_preparation': route['environment_preparation_cost']},
        'new_tokenizer_calls': 0, 'new_programmed_responses': 0, 'new_model_calls': 0,
        'elapsed_seconds': time.monotonic() - started,
        'scope': 'Read-only closure of three original consecutive opportunities. Third action recovered from its original world action, feedback, native response and settled team record; no old runtime is resumed.'}
    write(output, review)
    return review


def supplemental_shape(folder, unit, root_index, member, measurement):
    from scripts.software_feedback_qualification_v044 import ProgrammedOutput, RecordingContext
    from proworksim.software_organization_runtime_v038 import _CollectionOwner, close_runtime
    from proworksim.software_organization_runtime_v045 import build_runtime
    from proworksim.software_organization_v045 import build_software_collaboration_case, case_spec

    started = time.monotonic()
    folder.mkdir(exist_ok=False)
    route_id = unit['root_label'] + '-' + unit['condition']
    identity = {'policy_version': 'cpu-private-program-v045', 'adapter_sha256': 'no-model-weights'}
    owner = SimpleNamespace(window_id='cpu-v045-initial-supplement:' + route_id,
        recipe=copy.deepcopy(measurement.recipe), prepare_request=measurement.render,
        tokenizer=measurement.tokenizer, freeze_identity=lambda: copy.deepcopy(identity))
    program = ProgrammedOutput(owner, measurement)
    owner.transport = program
    context = RecordingContext(owner, folder / 'raw-transport', measurement, folder / 'measurements')
    prepared = build_software_collaboration_case(case_spec(unit['case_id'], condition=unit['condition'],
        first_member=unit['first_member']), folder / 'prepared')
    runtime, _, _ = build_runtime(_CollectionOwner(owner, context), prepared, folder / 'runtime', require_exact_resident=True)
    before = runtime.snapshot()
    before_test_budget = prepared.world.test_budget.snapshot()
    program.action = {'name': 'read_file', 'arguments': {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30}}
    context.stage = 'independent_other_initial_member'
    failure, outcome, checks = None, None, {}
    try:
        runtime.cursor = runtime.labels.index(member)
        outcome = runtime.step()
        runtime.after_completed_opportunity(outcome)
        runtime.sync_members()
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    finally:
        snapshot = runtime.snapshot()
        test_budget = prepared.world.test_budget.snapshot()
        close_runtime(runtime)
    if outcome is not None:
        checks = {
            'fresh_runtime_zero_prior_opportunities': before['opportunities'] == before['actions'] == 0
                and before['team_budget']['decisions'] == before['team_budget']['attempts'] == 0,
            'original_first_member_and_two_real_initial_members': prepared.case['first_member'] == unit['first_member']
                and before['labels'] == snapshot['labels'] == ['member_001', 'member_002'],
            'only_previously_unmeasured_member': member != unit['first_member'] and outcome['worker_id'] == member,
            'one_prepared_request': len(context.rows) == 1,
            'one_programmed_response': len(program.responses) == 1,
            'expected_action': outcome.get('decision', {}).get('action') == program.action['name']
                and outcome.get('decision', {}).get('arguments') == program.action['arguments'],
            'action_success': outcome.get('status') == 'running' and outcome.get('response', {}).get('ok') is True,
            'no_test_call': before_test_budget == test_budget and test_budget['used'] == 0,
            'one_completed_opportunity': snapshot['opportunities'] == snapshot['actions'] == 1,
        }
    if len(context.rows) == len(program.responses) == 1:
        events = [json.loads(line) for line in (folder / 'runtime/experience.jsonl').read_text().splitlines()]
        review = stage_review(folder, context.rows[0], program.responses[0], snapshot, events, 0)
        checks['new_actual_encoding_action_charge_and_preservation'] = review['passed']
        write(folder / 'stage-review.json', review)
    checks['no_exception'] = failure is None
    row = {'version': VERSION, 'route_id': route_id, 'case_id': unit['case_id'], 'condition': unit['condition'],
        'member': member, 'first_member': unit['first_member'], 'passed': bool(checks) and all(checks.values()),
        'failure': failure, 'checks': checks, 'prepared_requests': len(context.rows),
        'programmed_responses': len(program.responses), 'responses': program.responses, 'measurements': context.rows,
        'initial_actor_ids': before['labels'], 'fresh_independent_initial_state': True, 'old_runtime_resumed': False,
        'outcome': outcome, 'runtime_snapshot': snapshot,
        'environment_preparation_cost': prepared.world._software()['environment_preparation_cost'],
        'test_budget': test_budget, 'new_model_calls': 0, 'model_weights_loaded': False,
        'elapsed_seconds': time.monotonic() - started,
        'scope': 'One independent fresh initial shape for the previously unmeasured partner. The case retains its registered first_member; only the CPU diagnostic cursor is set to this partner. This is not a fourth consecutive action in the original route.'}
    write(folder / 'shape.json', row)
    return row


def repair(destination, original, plan):
    from scripts.software_organization_v045 import assignments
    from scripts.software_context_replay_v044 import load_cpu_measurement

    started = time.monotonic()
    destination, original = Path(destination).resolve(), Path(original).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    original_ref = reference(original / 'native-routes.json')
    old = read_json(original / 'native-routes.json')
    units = [(r, u) for r in range(4) for u in assignments()[f'block-r{r}-s0']]
    by_id = {r['route_id']: r for r in old['routes']}
    required = [u['root_label'] + '-' + u['condition'] for _, u in units]
    if len(by_id) != 12 or old['required_route_ids'] != required or set(by_id) != set(required):
        raise ValueError('Original material inventory mismatch')
    source_before = {str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in (SOURCE / 'src').rglob('*.py')}
    write(destination / 'source-before.json', {'files': source_before, 'repair_source': reference(Path(__file__)),
        'original_qualification': reference(SOURCE / 'runs/v045-controls/qualification-01/qualification.json')})
    reviews, rows, failures = {}, [], []
    # Do not load even the tokenizer until all original evidence is closed.
    for root_index, unit in units:
        route_id = unit['root_label'] + '-' + unit['condition']
        folder = destination / route_id
        folder.mkdir(exist_ok=False)
        review = original_review(by_id[route_id]['receipt'], unit, root_index, folder / 'readonly-review.json')
        reviews[route_id] = review
        if not review['passed']:
            failures.append({'route_id': route_id, 'phase': 'original_readonly_closure', 'checks': review['checks']})
    measurement = load_cpu_measurement(plan) if not failures else None
    for root_index, unit in units:
        route_id = unit['root_label'] + '-' + unit['condition']
        folder, old_route = destination / route_id, read_json(checked(by_id[route_id]['receipt']))
        supplemental = None
        if unit['condition'] != 'S1' and measurement is not None:
            member = next(m for m in old_route['initial_labels'] if m != unit['first_member'])
            supplemental = supplemental_shape(folder / 'initial-partner', unit, root_index, member, measurement)
            if not supplemental['passed']:
                failures.append({'route_id': route_id, 'phase': 'independent_initial_partner',
                    'checks': supplemental['checks'], 'failure': supplemental['failure']})
        labels = [unit['first_member']]
        if supplemental and supplemental['passed']:
            labels.append(supplemental['member'])
        complete = set(labels) == set(old_route['initial_labels'])
        measurements = old_route['measurements'] + (supplemental['measurements'] if supplemental else [])
        row = {'route_id': route_id, 'case_id': unit['case_id'], 'condition': unit['condition'],
            'first_member': unit['first_member'], 'passed': reviews[route_id]['passed'] and complete,
            'original_route': by_id[route_id]['receipt'], 'readonly_review': reference(folder / 'readonly-review.json'),
            'supplemental_initial_shape': reference(folder / 'initial-partner/shape.json') if supplemental else None,
            'initial_actor_ids': old_route['initial_labels'], 'measured_initial_actor_ids': sorted(labels),
            'initial_shapes_complete': complete, 'original_consecutive_requests': 3,
            'supplemental_independent_initial_requests': supplemental['prepared_requests'] if supplemental else 0,
            'minimum_selected_headroom': min(r['headroom_tokens'] for r in measurements),
            'protected_margin_deficits': sum(r['protected_headroom_after_margin_tokens'] < 0 for r in measurements)}
        write(folder / 'unit.json', row)
        row['receipt'] = reference(folder / 'unit.json')
        rows.append(row)
    checked(original_ref)
    for old_row in old['routes']:
        checked(old_row['receipt'])
    source_after = {str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in (SOURCE / 'src').rglob('*.py')}
    if source_before != source_after:
        failures.append({'phase': 'source_integrity', 'reason': 'production_source_changed_during_repair'})
    supplements = [read_json(checked(r['supplemental_initial_shape'])) for r in rows if r['supplemental_initial_shape']]
    originals = [r['original_cost'] for r in reviews.values()]
    result = {'version': VERSION, 'kind': 'twelve_new_material_native_cpu_routes_repaired',
        'passed': len(rows) == 12 and len(supplements) == 8 and not failures and all(r['passed'] for r in rows),
        'required_route_ids': required, 'routes': rows, 'failures': failures, 'original_failed_receipt': original_ref,
        'original_prepared_requests': old['prepared_requests'], 'original_programmed_responses': old['programmed_responses'],
        'supplemental_prepared_requests': sum(s['prepared_requests'] for s in supplements),
        'supplemental_programmed_responses': sum(s['programmed_responses'] for s in supplements),
        'old_requests_retokenized': 0, 'old_runtimes_resumed': 0, 'old_112_requests_replayed': 0,
        'continuous_four_step_routes_claimed': False, 'new_model_calls': 0, 'model_weights_loaded': False,
        'new_backward_calls': 0, 'actual_gpu_work': 0,
        'original_native_measurement_identity': old['native_measurement_identity'],
        'supplemental_native_measurement_identity': measurement.identity if measurement else None,
        'original_tokenizer_statistics': old['tokenizer_statistics'],
        'supplemental_tokenizer_statistics': measurement.statistics if measurement else {},
        'source_receipt': reference(destination / 'source-before.json'), 'production_source_unchanged': source_before == source_after,
        'cost': {'original_cpu_programmed_tokens': sum(r['programmed_charged_tokens'] for r in originals),
            'supplemental_cpu_programmed_tokens': sum(s['runtime_snapshot']['team_budget']['charged_tokens'] for s in supplements),
            'original_run_tests': sum(r['run_tests'] for r in originals), 'supplemental_run_tests': 0,
            'original_environment_public_drivers': sum(r['environment_preparation']['actual_public_driver_executions'] for r in originals),
            'supplemental_environment_public_drivers': sum(s['environment_preparation_cost']['actual_public_driver_executions'] for s in supplements),
            'supplemental_environment_cache_reuses': sum(s['environment_preparation_cost']['actual_public_driver_executions'] == 0 for s in supplements),
            'supplemental_environment_sandbox_seconds': sum(s['environment_preparation_cost']['sandbox_elapsed_seconds'] for s in supplements),
            'original_native_elapsed_seconds': old['elapsed_seconds'], 'repair_elapsed_seconds': time.monotonic() - started},
        'scope': 'Twelve material units close three original consecutive programmed opportunities each, plus eight separately initialized partner shapes. This is 36 retained original requests plus eight independent one-request supplements, not twelve continuous four-step routes. Failed original receipts remain unchanged. No historical requests are rendered or tokenized again; no model weights, sampling, GPU, private acceptance or parameter update.'}
    write(destination / 'native-routes.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    result = repair(args.output, args.original, args.plan)
    print(json.dumps({key: result[key] for key in ('passed', 'original_prepared_requests',
        'supplemental_prepared_requests', 'failures', 'cost')}, indent=2))
    if not result['passed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
