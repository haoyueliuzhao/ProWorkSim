"""Independent qualification-only correction and original-ten continuation.

The original614 files and both failed attempts remain unchanged. One PS1 input
can be source-derived from its already-recorded SDK events, with no original
provider request/hash claim. OH's completed measurement is never re-encoded.
"""
from __future__ import annotations

import argparse
import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import software_bridge_inputs_v052 as original
from scripts.software_holdout_inputs_v051 import ExactTokenizer, CaptureTransport, InitialCaptured, evaluate_request
from proworksim.software_bridge_sources_v052 import RepositorySources, checked, ref, write_new
from proworksim.storage import digest, json_bytes

VERSION = 'v052-initial-input-resume-v1'
FIRST_OH = 'v052-cal2-boltons-1-OH_ref'
FIRST_PS1 = 'v052-cal2-boltons-1-PS1'


def read(path):
    return json.loads(Path(path).read_bytes())


def tokenizer_for(release):
    specification = release['tokenizer']
    model = Path(specification['model_path']).resolve()
    expected = {model / 'tokenizer.json', model / 'tokenizer_config.json', model / 'chat_template.jinja'}
    if {checked(reference) for reference in specification['files']} != expected:
        raise ValueError('The exact original tokenizer/config/template binding must remain unchanged')
    checked(release['model_manifest'])
    checked(release['model_config'])
    from transformers import AutoTokenizer
    return ExactTokenizer(AutoTokenizer.from_pretrained(model, local_files_only=True))


def counts(tokenizer):
    return {'tokenizer_encoding_calls': tokenizer.encodings, 'tokenizer_encoding_exact_cache_hits': tokenizer.encoding_hits,
            'native_template_renders': tokenizer.renders, 'native_template_exact_cache_hits': tokenizer.render_hits}


def capture_counters(worker, budget, actions):
    return {'harness_decisions': worker.meter['decisions'], 'team_decisions': budget['decisions'],
        'LLM_entries': worker._completions, 'adapter_decisions': None,
        'adapter_decisions_status': 'not_applicable_PS1', 'attempts': budget['attempts'],
        'reservation_tokens': budget['held_tokens'], 'charged_tokens': budget['charged_tokens'],
        'responses': int(worker._last_body is not None), 'tool_actions': actions,
        'model_generations': worker.meter['http_attempts']}


def capture_ps1(provider, row, owner, destination):
    destination = Path(destination)
    prepared = original.build_software_collaboration_case(original.case_spec(row['task_id'], provider=provider),
        destination / 'prepared', provider=provider)
    owner.transport = CaptureTransport(owner, destination / 'transport')
    runtime, _, _ = original.build_runtime(owner, prepared, destination / 'sdk')
    before = prepared.world.store.load()
    try:
        try:
            runtime.step()
        except InitialCaptured:
            pass
        else:
            raise ValueError('SDK did not stop at the real first prepare boundary')
        captured = owner.transport.captured
        # Export the actual request immediately, before any post-capture assertion.
        if captured is not None:
            write_new(destination / 'original-request.json', captured['request'])
            write_new(destination / 'original-capture-envelope.json', captured)
        if captured is None or captured['runner_turn']['member_id'] != 'member_001' or runtime.labels != ['member_001']:
            raise ValueError('Only the original member_001 initial request is allowed')
        worker, budget = runtime.policies['member_001'], runtime.team_budget.snapshot()
        counters = capture_counters(worker, budget, runtime.actions)
        unchanged = before == prepared.world.store.load()
        write_new(destination / 'capture.json', {'version': VERSION, 'capture_counters': counters,
            'runner_turn': captured['runner_turn'], 'team_budget': budget, 'world_unchanged': unchanged,
            'original_provider_request_persisted': True, 'original_request_sha256': digest(json_bytes(captured['request'])),
            'source_derived_rematerialization': False, 'raw_owner_metadata': owner.metadata_reference,
            'weights_loaded': False, 'guard_claimed': False})
        original.validate_capture_counters('PS1', counters, unchanged=unchanged)
        if counters['LLM_entries'] != 1 or counters['charged_tokens'] != 0:
            raise ValueError('One real LLM entry and zero charges are required')
        return captured['request'], counters
    finally:
        original.close_runtime(runtime)


def recovered_request(*, prior_root, release):
    """Pure projection of original records through the bound SDK functions.

    No Agent/Conversation/Tool construction, SDK invocation, UUID, model or
    tokenizer is used here. Dynamic tool types need not be deserialized: their
    actual schema/description inputs are bound separately from event messages.
    """
    from openhands.sdk.llm import Message, TextContent
    from openhands.sdk.event.base import LLMConvertibleEvent
    from openhands.sdk.event.llm_convertible.system import SystemPromptEvent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from proworksim.harness_sdk import select_context, HARNESS_VERSION
    from proworksim.model_policy import CONTROL_TOOLS, normalize_config
    from proworksim.online_collection import _config
    from proworksim.software_calibration_collector_v051 import WAIT_DESCRIPTION, DONE_DESCRIPTION
    from proworksim.software_runtime_v033 import SDK_CONTEXT_SELECTION

    root = Path(prior_root).resolve() / FIRST_PS1
    experience = root / 'sdk/experience.jsonl'
    records = [json.loads(line) for line in experience.read_text().splitlines() if line.strip()]
    sdk_events = [row['payload']['event'] for row in records if row['kind'] == 'harness_sdk_event']
    if [event['kind'] for event in sdk_events] != ['SystemPromptEvent', 'MessageEvent']:
        raise ValueError('Only the fully saved first two actual SDK events are reconstructible')
    system, user = sdk_events
    if (system['dynamic_context'] is not None or user['source'] != 'user' or user['extended_content']
            or user['llm_message']['role'] != 'user' or any(block['type'] != 'text' for block in user['llm_message']['content'])
            or any(row['kind'] in {'model_call', 'tool_call', 'harness_tool_call', 'harness_model_refresh'} for row in records)):
        raise ValueError('Unknown mutable context/history cannot be guessed')
    bases = list((root / 'sdk/sdk-conversations/member_001/conversations').glob('*/base_state.json'))
    if len(bases) != 1:
        raise ValueError('Exactly one original SDK conversation must be bound')
    base = read(bases[0])
    if base.get('agent_state') != {} or base['agent'].get('condenser') is not None:
        raise ValueError('Unknown agent history or condensation is not reconstructible')
    # SystemPromptEvent.to_llm_message reads only these two recorded fields;
    # its dynamic ToolDefinition classes are irrelevant to message conversion.
    system_view = SimpleNamespace(system_prompt=TextContent.model_validate(system['system_prompt']), dynamic_context=None)
    user_view = SimpleNamespace(llm_message=Message.model_validate(user['llm_message']), extended_content=[])
    system_view.to_llm_message = lambda: SystemPromptEvent.to_llm_message(system_view)
    user_view.to_llm_message = lambda: MessageEvent.to_llm_message(user_view)
    messages = LLMConvertibleEvent.events_to_messages([system_view, user_view])
    flattened = []
    for message in messages:
        if message.role == 'user' and len(message.content) > 1:
            flattened.extend(Message(role='user', content=[block]) for block in message.content)
        else:
            flattened.append(message)
    wire = [message.to_chat_dict(cache_enabled=False, vision_enabled=False, function_calling_enabled=True,
        force_string_serializer=True, send_reasoning_content=True) for message in flattened]
    if [message['role'] for message in wire] != ['system', 'user']:
        raise ValueError('The stored actual first request must have one system and user message')
    user_text = wire[1]['content']
    payload = json.loads(user_text)
    before, after = [row['payload'] for row in records if row['kind'] == 'organization_work_opportunity_v049']
    if before['phase'] != 'before' or after['phase'] != 'after' or before['opportunity_id'] != after['opportunity_id']:
        raise ValueError('Original before/after runner opportunity binding is required')
    budget = after['team_budget']
    if (budget['decisions'] != 1 or budget['attempts'] != 0 or budget['held_tokens'] != 0
            or budget['charged_tokens'] != 0 or len(budget['records']) != 1):
        raise ValueError('Original capture must be the first unreserved decision')
    metadata = read(checked(release['raw_owner_metadata']))
    owner = original.MetadataOwner(metadata, metadata_reference=release['raw_owner_metadata'],
        model_manifest=release['model_manifest'], slot_id=FIRST_PS1, tokenizer=None)
    config = _config(owner, 'member_001', payload['role_task'], {'member_001': before['team_budget']['limits']['max_decisions']})
    config.update(context_policy='full_history', format_error_policy='format_feedback_budgeted_v033')
    config = normalize_config(config)
    if (base['agent']['llm']['temperature'] != config['temperature']
            or base['agent']['llm']['max_input_tokens'] != config['max_context_tokens']
            or base['agent']['llm']['max_output_tokens'] != config['max_output_tokens']):
        raise ValueError('Actual SDK configuration disagrees with the frozen source-derived config')
    tools_records = [row['payload'] for row in records if row['kind'] == 'harness_public_tools']
    if len(tools_records) != 1 or len(tools_records[0]) != 27:
        raise ValueError('All27 actual harness schemas must be saved')
    definitions = copy.deepcopy(tools_records[0]) + copy.deepcopy(list(CONTROL_TOOLS))
    descriptions = {'staff_wait': WAIT_DESCRIPTION, 'staff_done': DONE_DESCRIPTION}
    for definition in definitions:
        if definition['name'] in descriptions:
            definition['description'] = descriptions[definition['name']]
    if (len(system['tools']) != 29 or [tool['title'] for tool in system['tools']] != [tool['name'] for tool in definitions]
            or [tool['description'] for tool in system['tools']] != [tool['description'] for tool in definitions]):
        raise ValueError('Actual resolved SDK tool names/descriptions do not match all original schemas')
    selected, selection = select_context(wire, [user_text], SDK_CONTEXT_SELECTION)
    if selected != wire:
        raise ValueError('No hidden context reduction may be inferred for the original first request')
    request = {'model': config['model'], 'messages': selected,
        'tools': [{'type': 'function', 'function': item} for item in definitions],
        'max_tokens': config['max_output_tokens'], 'temperature': config['temperature'], 'tool_choice': 'auto', 'stream': False}
    if config['thinking'] is not None:
        request['thinking'] = {'type': 'enabled' if config['thinking'] else 'disabled'}
    if config['reasoning_effort'] is not None:
        request['reasoning_effort'] = config['reasoning_effort']
    call_id = next(iter(budget['records']))
    opportunity = before['opportunity_id']
    run_id, ordinal = opportunity.removeprefix('staff-opportunity-').rsplit('-', 1)
    if ordinal != '1' or call_id != 'model-' + digest(json_bytes([run_id, 'member_001', 1]))[:24]:
        raise ValueError('The saved call ID must match the original deterministic association')
    association = {'call_id': call_id, 'decision_id': call_id, 'worker_id': 'member_001', 'opportunity_id': opportunity,
        'decision_index': 1, 'requested_model': config['model'], 'backend_id': config['backend_id'],
        'action_protocol': config['action_protocol'], 'model_revision': config['model_revision'],
        'weight_identity': copy.deepcopy(config['weight_identity']), 'harness_version': HARNESS_VERSION, 'identity_epoch': 0}
    sources = {str(path): ref(path) for path in (experience, bases[0], checked(release['raw_owner_metadata']))}
    for item in (Message, LLMConvertibleEvent, SystemPromptEvent, MessageEvent, select_context, _config, normalize_config):
        path = Path(inspect.getfile(item)).resolve()
        sources[str(path)] = ref(path)
    chain = {'version': 'v052-PS1-source-derived-request-chain-v1', 'sources': sources,
        'original_provider_request_persisted': False, 'original_request_sha256': None,
        'source_derived_rematerialization': True, 'independent_original_hash_match_claimed': False,
        'original_sdk_event_ids': [event['id'] for event in sdk_events], 'source_derived_config': config,
        'runner_turn': {'member_id': 'member_001', 'association': association}, 'before': before, 'after': after,
        'context_selection': selection, 'mutable_inputs_guessed': [], 'new_UUIDs_generated': 0,
        'new_SDK_requests': 0, 'new_model_calls': 0, 'tokenizer_calls_in_rematerialization': 0,
        'conversion': ['Original SystemPromptEvent/TextContent and original user MessageEvent',
            'Bound SDK events_to_messages and Message.to_chat_dict, with exact original flags',
            'Frozen first-round select_context; both actual messages retained',
            'Actual27 tool schemas + frozen2 control schemas + actual S1 descriptions',
            'Frozen _config/normalize_config and original raw metadata / original role_task / recorded128 limit',
            'Exact frozen _complete request dictionary construction, without invoking completion or a conversation'],
        'scope': 'Deterministic source-derived input from the actual first SDK records, not a previously persisted provider request or independently matched original provider SHA.'}
    return request, chain


def measured_record(*, provider, row, owner, folder, request, projection, native, natives, counters, derived=False):
    write_new(folder / 'selected-request.json', projection['selected'])
    write_new(folder / 'projection.json', projection['projection'])
    write_new(folder / 'selected-native-input.json', native)
    write_new(folder / 'native-inputs.json', natives)
    case = provider.build_case(row['task_id'])
    p = projection['projection']
    return {'slot_id': row['slot_id'], 'task_id': row['task_id'], 'condition': row['condition'], 'member_id': 'member_001',
        'source_row_sha256': row['source_row_sha256'], 'initial_files_sha256': case['initial_binding']['initial_files_sha256'],
        'problem_sha256': digest(case['root_goal'].encode()), 'raw_actor_identity_metadata_only': owner.freeze_identity(),
        'window_id': owner.window_id, 'capture_counters': counters,
        'original_provider_request_persisted': not derived,
        'original_request_sha256': None if derived else digest(json_bytes(request)), 'source_derived_rematerialization': derived,
        'original_request': ref(folder / ('source-derived-request.json' if derived else 'original-request.json')),
        'selected_request': ref(folder / 'selected-request.json'), 'projection': ref(folder / 'projection.json'),
        'native_input': ref(folder / 'selected-native-input.json'), 'all_native_inputs': ref(folder / 'native-inputs.json'),
        'capture': ref(folder / 'capture.json'),
        **{key: p[key] for key in ('original_prompt_tokens', 'selected_prompt_tokens', 'protected_prompt_tokens',
                                  'reserved_output_tokens', 'context_limit', 'fits')}}


def no_tests(**kwargs):
    raise AssertionError('Initial qualification cannot execute business tests')


def recover(*, prior_root, prior_release, output):
    release, source, rows = original.gate(prior_release)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    request, chain = recovered_request(prior_root=prior_root, release=release)
    write_new(output / 'dependency-chain.json', chain)
    write_new(output / 'source-derived-request.json', request)
    tokenizer = tokenizer_for(release)
    row = next(row for row in rows if row['slot_id'] == FIRST_PS1)
    owner = original.MetadataOwner(read(checked(release['raw_owner_metadata'])), metadata_reference=release['raw_owner_metadata'],
        model_manifest=release['model_manifest'], slot_id=FIRST_PS1, tokenizer=tokenizer)
    measured, _ = evaluate_request(request, owner, 'member_001', {})
    native = next(item for item in measured['native'] if item['request_sha256'] == digest(json_bytes(measured['selected'])))
    provider = RepositorySources(source['source_root'], runtime_manifest=checked(release['test_runtime']),
        expected_manifest_sha256=source['adapter_manifest']['sha256'], runner=no_tests)
    counters = {'harness_decisions': 1, 'team_decisions': 1, 'LLM_entries': 1, 'responses': 0,
        'attempts': 0, 'reservation_tokens': 0, 'charged_tokens': 0, 'tool_actions': 0, 'model_generations': 0}
    write_new(output / 'capture.json', {'version': VERSION, 'dependency_chain': ref(output / 'dependency-chain.json'),
        'capture_counters': counters, 'original_provider_request_persisted': False,
        'original_request_sha256': None, 'source_derived_rematerialization': True,
        'new_SDK_requests': 0, 'first_PS1_tokenizer_measurement': True})
    record = measured_record(provider=provider, row=row, owner=owner, folder=output, request=request,
        projection=measured, native=native, natives=measured['native'], counters=counters, derived=True)
    summary = {'version': 'v052-initial-PS1-rematerialization-v1', 'completed': True, 'passed': record['fits'],
        'fixture_only': False, 'prior_release': ref(prior_release), 'prior_root': str(Path(prior_root).resolve()),
        'design': release['design'], 'source_qualification': release['source_qualification'],
        'row': record, 'dependency_chain': ref(output / 'dependency-chain.json'), **counts(tokenizer),
        'new_SDK_requests': 0, 'new_model_calls': 0, 'new_tests': 0, 'old_OH_reencoded': False,
        'original_provider_request_persisted': False, 'original_request_sha256': None,
        'source_derived_rematerialization': True, 'original_records_modified': False}
    write_new(output / 'summary.json', summary)
    return summary


def remaining_inventory(rows, prior_oh, recovered_ps1):
    if (len(rows) != 12 or len({row['slot_id'] for row in rows}) != 12 or rows[0]['slot_id'] != FIRST_OH or rows[1]['slot_id'] != FIRST_PS1
            or prior_oh['slot_id'] != FIRST_OH or recovered_ps1['slot_id'] != FIRST_PS1
            or recovered_ps1.get('source_derived_rematerialization') is not True
            or recovered_ps1.get('original_provider_request_persisted') is not False
            or recovered_ps1.get('original_request_sha256') is not None):
        raise ValueError('Reuse precisely the first OH and source-derived first PS1; do not reselect or duplicate')
    return [copy.deepcopy(row) for row in rows[2:]]


def resume(*, release_path, output):
    release = read(release_path)
    if (release.get('version') != 'v052-initial-input-resume-execution-release-v1'
            or release.get('released') is not True or release.get('maximum_new_SDK_requests') != 10):
        raise ValueError('Root must release only the ten original unstarted input shapes')
    prior_release_path = checked(release['prior_input_release'])
    prior_release, source, rows = original.gate(prior_release_path)
    prior_progress = read(checked(release['prior_OH_progress']))
    recovered = read(checked(release['rematerialized_PS1']))
    checked(release['prior_partial_exit'])
    for reference in release['implementation_sources'].values():
        checked(reference)
    if ref(__file__) not in release['implementation_sources'].values():
        raise ValueError('Freeze this independent qualification correction before continuation')
    for reference in release['control_refs']:
        if read(checked(reference)).get('passed') is not True:
            raise ValueError('The two affected/new pure controls must close before continuation')
    if (len(prior_progress['rows']) != 1 or recovered['prior_release'] != release['prior_input_release']
            or recovered['design'] != prior_release['design'] or recovered['source_qualification'] != prior_release['source_qualification']):
        raise ValueError('Recovery and original first OH must bind the same unchanged release and design')
    prior_oh = copy.deepcopy(prior_progress['rows'][0])
    for key in ('original_request', 'selected_request', 'projection', 'native_input', 'all_native_inputs', 'capture'):
        checked(prior_oh[key])
        checked(recovered['row'][key])
    remaining = remaining_inventory(rows, prior_oh, recovered['row'])
    if [row['slot_id'] for row in remaining] != release['remaining_slot_ids']:
        raise ValueError('Only the exact original ten unstarted slots may be captured')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior_oh.update(original_provider_request_persisted=True,
        original_request_sha256=prior_oh['original_request']['sha256'], source_derived_rematerialization=False,
        measurement_reused_from=release['prior_OH_progress'])
    report = {'version': 'v052-initial-input-qualification-resume-v1', 'purpose': original.PURPOSE,
        'fixture_only': False, 'completed': False, 'passed': False, 'design': prior_release['design'],
        'source_qualification': prior_release['source_qualification'], 'test_runtime': prior_release['test_runtime'],
        'reference_runtime': prior_release['reference_runtime'], 'input_release': ref(release_path),
        'original_input_release': release['prior_input_release'], 'prior_partial_exit': release['prior_partial_exit'],
        'prior_OH_progress': release['prior_OH_progress'], 'rematerialized_PS1': release['rematerialized_PS1'],
        'rows': [prior_oh, copy.deepcopy(recovered['row'])], 'actual_initial_SDK_requests': 2,
        'new_actual_initial_SDK_requests': 0, 'logical_initial_shapes': 12,
        'source_derived_initial_shapes': 1, 'new_model_calls': 0, 'repository_test_executions': 0,
        'source_derived_shape_slot_id': recovered['row']['slot_id'],
        'original_provider_request_persisted': False, 'original_request_sha256': None,
        'source_derived_rematerialization': True,
        'request_provenance_field_scope': 'Only the explicitly identified source-derived PS1 shape; all other rows retain their own original request refs',
        'weights_loaded': False, 'GPU_workers': 0, 'original_provider_request_persisted_for_all_shapes': False,
        'source_derived_rematerialization_present': True, 'independent_original_request_hash_match_claimed_for_derived_shape': False,
        'old_OH_reencoded': False, 'old_PS1_recaptured': False, 'original_records_modified': False}
    write_new(output / 'declaration.json', report)
    tokenizer = tokenizer_for(prior_release)
    provider = RepositorySources(source['source_root'], runtime_manifest=checked(prior_release['test_runtime']),
        expected_manifest_sha256=source['adapter_manifest']['sha256'], runner=no_tests)
    metadata = read(checked(prior_release['raw_owner_metadata']))
    cache = {}
    for row in remaining:
        folder = output / row['slot_id']
        owner = original.MetadataOwner(metadata, metadata_reference=prior_release['raw_owner_metadata'],
            model_manifest=prior_release['model_manifest'], slot_id=row['slot_id'], tokenizer=tokenizer)
        if row['condition'] == 'PS1':
            request, counters = capture_ps1(provider, row, owner, folder)
            measured, _ = evaluate_request(request, owner, 'member_001', cache)
            native = next(item for item in measured['native'] if item['request_sha256'] == digest(json_bytes(measured['selected'])))
        else:
            request, native, counters = original.capture_oh(provider, row, owner, folder, prior_release['reference_runtime'])
            measured = {'selected': request, 'projection': original.native_capacity(native, owner.contract), 'native': [native]}
        original.validate_native_input(native, owner.contract)
        record = measured_record(provider=provider, row=row, owner=owner, folder=folder, request=request,
            projection=measured, native=native, natives=measured['native'], counters=counters)
        report['rows'].append(record)
        report['new_actual_initial_SDK_requests'] += 1
        report['actual_initial_SDK_requests'] += 1
        write_new(output / (row['slot_id'] + '-progress.json'), report)
    # Prior OH took the sole unbranched prepare_native_input path once. Its
    # aggregate counter object was not saved after the later PS1 assertion;
    # expose this source-derived count separately, never as a saved snapshot.
    prior_oh_counts = {'tokenizer_encoding_calls': 1, 'tokenizer_encoding_exact_cache_hits': 0,
        'native_template_renders': 1, 'native_template_exact_cache_hits': 0}
    new_counts = counts(tokenizer)
    recovery_counts = {key: recovered[key] for key in new_counts}
    cumulative_counts = {key: new_counts[key] + recovery_counts[key] + prior_oh_counts[key] for key in new_counts}
    paired = {case: [row for row in report['rows'] if row['task_id'] == case] for case in original.TASK_IDS}
    same_sources = all(len(items) == 2 and len({(row['source_row_sha256'], row['initial_files_sha256'], row['problem_sha256'])
        for row in items}) == 1 for items in paired.values())
    report.update(completed=True, passed=len(report['rows']) == 12 and same_sources and all(row['fits'] for row in report['rows']),
        same_task_source_and_assets_bound=same_sources, **cumulative_counts,
        measurement_counts_by_phase={'prior_OH': {'counts': prior_oh_counts,
            'basis': 'Source-bound single unbranched prepare_native_input call and saved native input; aggregate counter not originally persisted'},
            'first_PS1_measurement': {'counts': recovery_counts, 'source': release['rematerialized_PS1']},
            'new_original_ten': {'counts': new_counts}},
        PS1_harness_decisions=sum(row['capture_counters']['harness_decisions'] for row in report['rows'] if row['condition'] == 'PS1'),
        PS1_team_decisions=sum(row['capture_counters']['team_decisions'] for row in report['rows'] if row['condition'] == 'PS1'),
        model_generations=0, qualification_bookkeeping_transferred_to_formal_episode=False)
    write_new(output / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['recover', 'resume'])
    parser.add_argument('--prior-root')
    parser.add_argument('--prior-release')
    parser.add_argument('--release')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.action == 'recover':
        if not args.prior_root or not args.prior_release:
            parser.error('Recovery requires both original evidence root and original release')
        result = recover(prior_root=args.prior_root, prior_release=args.prior_release, output=args.output)
    else:
        if not args.release:
            parser.error('Continuation requires its independent release')
        result = resume(release_path=args.release, output=args.output)
    print(json.dumps({key: result.get(key) for key in ('version', 'passed', 'new_SDK_requests', 'actual_initial_SDK_requests',
        'tokenizer_encoding_calls', 'native_template_renders', 'new_model_calls')}))


if __name__ == '__main__':
    main()
