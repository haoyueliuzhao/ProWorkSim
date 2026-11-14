"""Pure role-local message presentation; no world handle, queries or solver.

Original memory and model events remain untouched. Selected real tool messages
stay byte-for-byte equal, so actual consumer-input evidence remains checkable.
"""
import copy
import json
from pathlib import Path

from .experience import ExperienceRecorder, capture_port
from .model_policy import ModelPolicy
from .online_collection import _config
from .staff_runtime import StaffRuntime
from .storage import digest, json_bytes
from .work_interface import WorkInterface

VERSION = 'deterministic-work-view-v0.22'
ARMS = ('original_history', 'compact_work')


def _json(content):
    try:
        return json.loads(content) if isinstance(content, str) else None
    except (ValueError, TypeError):
        return None


def compact_observation(message):
    """Remove duplicate descriptive fields, retaining all current public rules."""
    result = copy.deepcopy(message)
    body = _json(result.get('content'))
    if not isinstance(body, dict) or not isinstance(body.get('observation'), dict):
        raise ValueError('Current registered observation must be actual structured public input')
    obs = body['observation']
    for project in obs.get('projects', {}).values():
        # The visible work carries its actual goal and all contract requirements.
        project.pop('goal', None)
    for work in obs.get('work_items', {}).values():
        visible = [text for text in work.get('visible_requirements', []) if text != work.get('goal')]
        if visible:
            work['visible_requirements'] = visible
        else:
            work.pop('visible_requirements', None)
        req = work.get('requirements', {})
        scope = req.get('online_scope', {})
        if scope.get('public_requirement') == work.get('goal'):
            scope.pop('public_requirement')
        # Same exact public review contract appears twice in v022; keep the
        # named work requirements entry in full, including its structural example.
        if scope.get('public_review_contract') == {k: v for k, v in req.get('review_contract', {}).items() if k != 'audit_alias'}:
            scope.pop('public_review_contract')
    result['content'] = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return result


def _association(messages, rejected):
    result = {}
    for index, message in enumerate(messages):
        if message.get('role') != 'assistant' or index in rejected:
            continue
        for call in message.get('tool_calls') or []:
            identifier = call.get('id')
            function = call.get('function') or {}
            if identifier:
                if identifier in result:
                    raise ValueError('Tool call identity repeated in original role history')
                result[identifier] = {'index': index, 'name': function.get('name'), 'arguments': _json(function.get('arguments'))}
    return result


def compact_messages(memory, inherited_selection):
    """Select by operation/reference recency, never by business content/grade."""
    messages = memory['messages']
    current = inherited_selection['current_observation_index']
    if current is None:
        raise ValueError('Compact view requires registered current public observation')
    rejected = {x['index'] for x in memory.get('rejected_assistant_messages', [])}
    associations = _association(messages, rejected)
    material, feedback, unknown = {}, [], []
    action_history = []
    for index, message in enumerate(messages):
        if message.get('role') != 'tool':
            continue
        owner = associations.get(message.get('tool_call_id'))
        response = _json(message.get('content'))
        control = bool(owner and owner['name'] in {'staff_wait', 'staff_done'} and isinstance(response, dict)
                       and response.get('status') in {'worker_wait', 'worker_done'} and response.get('world_action_executed') is False)
        if owner is None or not isinstance(response, dict) or (type(response.get('ok')) is not bool and not control):
            raise ValueError('Compact view cannot reconstruct an unbound tool return')
        result = response.get('result')
        result = result if isinstance(result, dict) else {}
        ref = result.get('reference')
        ref = ref if isinstance(ref, dict) else {}
        name = owner['name']
        feedback.append(index)
        key = None
        if response.get('ok') and name in {'read_alias', 'read_version', 'read_object', 'sql_build', 'sql_query'} and ref.get('version_id'):
            key = (name in {'sql_build', 'sql_query'}, ref.get('object_id', ref.get('artifact_id')), ref['version_id'])
        elif response.get('ok') and name == 'inspect_submission' and result.get('submission_id'):
            key = ('submission', result['submission_id'])
        elif response.get('ok') and name == 'read_messages':
            key = ('messages',)
        if control:
            key = ('worker_control',)
        if key:
            material[key] = index
        action_history.append({'original_message_index': index, 'tool': name,
                               'argument_scope': {k: copy.deepcopy(v) for k, v in (owner['arguments'] or {}).items() if k in {'alias', 'reference', 'object_id', 'version_id', 'work_id', 'work_ids', 'code_alias', 'output_alias', 'input_aliases', 'submission_id', 'route_id', 'issue_id', 'response_id', 'decision'}},
                               'arguments_sha256': digest(json_bytes(owner['arguments'])), 'ok': response.get('ok'), 'control_status': response.get('status') if control else None,
                               'reference': copy.deepcopy(ref) or None,
                               'submission_id': result.get('submission_id'),
                               'response_sha256': digest(json_bytes(message))})
    selected = {0, current, *material.values(), *feedback[-2:]}
    registered = set(inherited_selection['registered_observation_indices'])
    rejected = {x['index'] for x in memory.get('rejected_assistant_messages', [])}
    # Keep the latest actual public format-feedback message verbatim. The full
    # rejected assistant text remains archived but is not reintroduced as advice.
    format_indices = []
    for index, message in enumerate(messages):
        if message.get('role') == 'user' and index not in registered:
            payload = _json(message.get('content'))
            if isinstance(payload, dict) and 'public_format_feedback' in payload:
                format_indices.append(index)
            elif index != 0:
                unknown.append(index)
    selected.update(format_indices[-1:])
    latest_rejected = None
    if format_indices and format_indices[-1] > 0 and messages[format_indices[-1] - 1].get('role') == 'assistant':
        latest_rejected = format_indices[-1] - 1
        selected.add(latest_rejected)
    selected.update(unknown)  # Never silently summarize unknown-origin input.
    for index in list(selected):
        if messages[index].get('role') == 'tool':
            selected.add(associations[messages[index]['tool_call_id']]['index'])
    projected, decisions = [], []
    for index in sorted(selected):
        message = copy.deepcopy(messages[index])
        operation = 'unchanged'
        if index == current:
            message = compact_observation(message)
            body = _json(message['content'])
            body['own_action_history'] = action_history
            body['presentation_note'] = 'Deterministic view of your own actual observations and tool calls only. A retained read is not understanding or adoption. Omitted materials remain accessible through the original authorized tools. No result, issue, submission or decision is generated by this view.'
            message['content'] = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            operation = 'deduplicated_current_observation_and_own_action_index'
        elif message.get('role') == 'assistant':
            if index == latest_rejected:
                message = {'role': 'assistant', 'content': json.dumps({'rejected_assistant_response': message}, ensure_ascii=False)}
                operation = 'actual_latest_rejected_assistant_as_data'
            elif index in rejected:
                raise ValueError('Rejected assistant cannot own an executed selected tool result')
            elif message.get('tool_calls'):
                message['content'] = None
                operation = 'actual_tool_call_without_freeform_preamble'
        projected.append(message)
        decisions.append({'original_index': index, 'original_sha256': digest(json_bytes(messages[index])),
                          'wire_sha256': digest(json_bytes(message)), 'projection': operation})
    audit = {'version': VERSION, 'arm': 'compact_work', 'original_message_count': len(messages),
             'original_messages_sha256': digest(json_bytes(messages)), 'selected_messages_sha256': digest(json_bytes(projected)),
             'selected_indices': sorted(selected), 'removed_indices': sorted(set(range(len(messages))) - selected),
             'current_observation_index': current, 'messages': decisions,
             'preserved_tool_result_indices': sorted(i for i in selected if messages[i].get('role') == 'tool'),
             'scope': 'Role-local deterministic presentation only. Original archive unchanged; no world access, new read receipts, inferred facts, hidden truth, cross-role memory or automatic action.'}
    return projected, audit


class OriginalHistoryModelPolicy(ModelPolicy):
    """The actual v021 organization: latest observation, otherwise full dialogue."""
    def __init__(self, config=None, **kwargs):
        super().__init__(config, **kwargs)
        if self.config['context_policy'] != 'latest_observation' or self.config['action_protocol'] != 'native_tools':
            raise ValueError('W1 preserves the v021 native/latest-observation protocol')


class CompactWorkModelPolicy(OriginalHistoryModelPolicy):
    def _select_messages(self, memory):
        _, inherited = super()._select_messages(memory)  # Validate original provenance first.
        return compact_messages(memory, inherited)


def runtime(owner, prepared, folder, arm):
    if arm not in ARMS:
        raise ValueError('Unknown predeclared work-view arm')
    folder = Path(folder)
    policies, ports, captures, interfaces = {}, {}, {}, {}
    policy_type = OriginalHistoryModelPolicy if arm == 'original_history' else CompactWorkModelPolicy
    for role in prepared.scenario['roles']:
        label = role['role_id']
        interface = WorkInterface(prepared.world.session(role['actor'], role['project']), label,
                                  audit_dir=folder/'public-projections'/label, variant='v14', presentation='compact_v14')
        interfaces[label] = interface
        ports[label] = capture_port(interface, captures.setdefault(label, []))
        config = _config(owner, label, role['config']['task'], prepared.case['role_decision_limits'])
        policies[label] = policy_type(config, transport=owner.transport, audit_dir=folder/'model-calls'/label)
        role.update(policy='model', config=copy.deepcopy(policies[label].config))
    return StaffRuntime(ports, policies, recorder=ExperienceRecorder()), captures, interfaces
