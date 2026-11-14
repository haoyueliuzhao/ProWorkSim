"""Role-private working memory and exact edits over an existing managed port.

Only the underlying port changes world facts. Notes/todos are explicitly private
claims. Retrieval searches this role's actually observed history, never assets,
other conversations, raw source files, evaluators or locked pools.
"""
import copy
import json

from .storage import digest, json_bytes
from .work_interface import REFERENCE, _schema_errors

VERSION = 'role-workbench-v0.16'
PRIVATE = {'work_note', 'work_todo', 'work_history_search', 'work_history_read'}
EDIT = 'work_replace_text'


def _tool(name, description, properties, required):
    return {'name': name, 'description': description, 'parameters': {'type': 'object',
            'properties': properties, 'required': required, 'additionalProperties': False}}


TOOLS = [
    _tool('work_note', 'Store your own private working note, or delete it with an empty text. It is not a world fact, read receipt, handoff or approval.',
          {'key': {'type': 'string'}, 'text': {'type': 'string'}}, ['key', 'text']),
    _tool('work_todo', 'Maintain your own task checklist. Marking a todo done does not complete any business work.',
          {'key': {'type': 'string'}, 'text': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['open', 'done']}}, ['key', 'text', 'status']),
    _tool('work_history_search', 'Search only observations and real tool returns previously seen by this worker. Results are bounded excerpts; use work_history_read for the exact original record. Recall is not a new world read.',
          {'query': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1}}, ['query', 'limit']),
    _tool('work_history_read', 'Recall one exact entry from your own observed history. This does not query the world or establish current applicability.',
          {'entry_id': {'type': 'integer', 'minimum': 0}}, ['entry_id']),
    _tool(EDIT, 'Replace one string leaf in a JSON alias you actually read, at the exact current reference and explicit locator. Other content is preserved. You choose all replacement text and source dependencies; this executes an ordinary write_object, not a SQL repair service.',
          {'alias': {'type': 'string'}, 'reference': REFERENCE,
           'locator': {'type': 'array', 'items': {'type': ['string', 'integer']}, 'minItems': 1},
           'new_text': {'type': 'string'}, 'work_id': {'type': 'string'}, 'dependencies': {'type': 'array', 'items': REFERENCE}},
          ['alias', 'reference', 'locator', 'new_text', 'dependencies']),
]


class WorldGatewayError(RuntimeError):
    pass


class HarnessPort:
    def __init__(self, port, role_id, *, project_id, public_sink, world_sink, harness_sink):
        self.port, self.role_id, self.project_id = port, role_id, project_id
        self.public_sink = public_sink
        self._definitions = {}
        self.world_sink, self.harness_sink = world_sink, harness_sink
        self.notes, self.todos, self.history, self.reads = {}, {}, [], {}
        self.latest = None
        self._requests = {}

    def tools(self):
        base = self.port.tools()
        self.public_sink("public_tools", base)
        additions = [t for t in TOOLS if t['name'] != EDIT or any(d['name'] == 'write_object' for d in base)]
        self._definitions = {t["name"]: copy.deepcopy(t) for t in base + additions}
        return copy.deepcopy(base + additions)

    def _remember(self, kind, value):
        row = {'entry_id': len(self.history), 'kind': kind, 'payload': copy.deepcopy(value),
               'payload_sha256': digest(json_bytes(value))}
        self.history.append(row)

    def observe(self):
        observed = self.port.observe()
        self.public_sink("public_observation", observed)
        self.latest = copy.deepcopy(observed)
        # Keep the original world observation, before private notes are appended.
        self._remember('public_observation', observed)
        result = copy.deepcopy(observed)
        result['personal_workbench'] = {'version': VERSION, 'owner_role': self.role_id,
            'notes': copy.deepcopy(self.notes), 'todos': copy.deepcopy(self.todos),
            'observed_history_entries': len(self.history),
            'scope': 'Role-private working claims; not formal world state, proof of reading, applicability or completion.'}
        return result

    def _world_call(self, action, arguments, request_key, association):
        try:
            response = self.port.call(action, request_key=request_key, **arguments)
        except Exception as error:
            self.world_sink({'action': action, 'arguments': copy.deepcopy(arguments), 'request_key': request_key,
                'exception': {'type': type(error).__name__, 'message': str(error)}}, association)
            raise WorldGatewayError('Managed world port raised: ' + str(error)) from error
        if not isinstance(response, dict):
            raise WorldGatewayError('Managed world port returned a non-object response')
        payload = {'action': action, 'arguments': copy.deepcopy(arguments), 'request_key': request_key,
                   'response': copy.deepcopy(response)}
        self.world_sink(payload, association)
        self._remember('tool_call', payload)
        result = response.get('result', {}) if isinstance(response, dict) else {}
        if response.get('ok') and action in {'read_alias', 'read_version'} and isinstance(result.get('reference'), dict) and 'data' in result:
            ref = result['reference']
            self.reads[(ref['object_id'], ref['version_id'])] = copy.deepcopy(result['data'])
        return response

    def call(self, action, *, request_key, association, **arguments):
        fingerprint = digest(json_bytes([action, arguments]))
        if request_key in self._requests:
            old, response = self._requests[request_key]
            if old != fingerprint:
                raise ValueError('Harness request key was reused with different arguments')
            return copy.deepcopy(response)
        if action not in PRIVATE | {EDIT}:
            return self._world_call(action, arguments, request_key, association)
        definitions = self._definitions
        before = self.snapshot()
        try:
            if action not in definitions:
                raise ValueError('Tool not in this worker profile')
            errors = _schema_errors(definitions[action]['parameters'], arguments)
            if errors:
                raise ValueError('; '.join(errors))
            if action == 'work_note':
                key, text = arguments['key'], arguments['text']
                if not key or len(key) > 80 or len(text) > 2000 or (key not in self.notes and len(self.notes) >= 8):
                    raise ValueError('Notes are bounded to 8 keys, 80-character keys and 2000 characters per note')
                if text:
                    self.notes[key] = text
                else:
                    self.notes.pop(key, None)
                response = {'ok': True, 'private_state': {'note': key, 'text': text}, 'world_effect': False}
            elif action == 'work_todo':
                key = arguments['key']
                if not key or len(key) > 80 or len(arguments['text']) > 500 or (key not in self.todos and len(self.todos) >= 8):
                    raise ValueError('Todos are bounded to 8 entries, 80-character keys and 500-character text')
                self.todos[key] = {k: arguments[k] for k in ('text', 'status')}
                response = {'ok': True, 'private_state': copy.deepcopy(self.todos[key]), 'world_effect': False}
            elif action == 'work_history_search':
                limit, query = arguments['limit'], arguments['query']
                if not 1 <= limit <= 5 or not query or len(query) > 200:
                    raise ValueError('Search needs a nonempty query <=200 characters and limit 1..5')
                matches = []
                for row in reversed(self.history):
                    text = json.dumps(row['payload'], ensure_ascii=False)
                    pos = text.casefold().find(query.casefold())
                    if pos >= 0:
                        start = max(0, pos-200)
                        matches.append({'entry_id': row['entry_id'], 'kind': row['kind'], 'payload_sha256': row['payload_sha256'],
                                        'excerpt': text[start:start+1200], 'excerpt_start_character': start,
                                        'full_character_length': len(text)})
                        if len(matches) == limit:
                            break
                response = {'ok': True, 'matches': matches, 'world_effect': False,
                            'scope': 'Only actual prior observations/returns of this role; no source query or new reading receipt'}
            elif action == 'work_history_read':
                index = arguments['entry_id']
                if not 0 <= index < len(self.history):
                    raise ValueError('No such entry in this worker history')
                response = {'ok': True, 'entry': copy.deepcopy(self.history[index]), 'world_effect': False}
            else:
                response = self._edit(arguments, request_key, association)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            response = {'ok': False, 'error': {'code': 'harness_tool_rejected', 'message': str(error)}, 'world_effect': False}
        event = {'action': action, 'arguments': copy.deepcopy(arguments), 'request_key': request_key,
                 'response': copy.deepcopy(response), 'owner_role': self.role_id,
                 'private_before_sha256': digest(json_bytes(before)), 'private_after_sha256': digest(json_bytes(self.snapshot()))}
        self.harness_sink(event, association)
        self._requests[request_key] = (fingerprint, copy.deepcopy(response))
        return response

    def _edit(self, arguments, key, association):
        current = self.port.observe()
        self.public_sink('public_observation', current)
        self.latest = copy.deepcopy(current)
        self._remember('editor_current_metadata', {'observation': current,
            'origin': 'harness_mechanical_lookup', 'included_in_model_input': False,
            'scope': 'Metadata checked for stale edit only; no document read or adoption created'})
        ref, alias = arguments['reference'], arguments['alias']
        oid, version = ref['object_id'], ref['version_id']
        if self.latest is None or (oid, version) not in self.reads:
            raise ValueError('Exact target JSON must have been actually read by this worker')
        aliases = self.latest.get('workspaces', {})
        if aliases.get(self.project_id, {}).get(alias) != oid:
            raise ValueError('Alias does not bind this observed object')
        if self.latest.get('objects', {}).get(oid, {}).get('versions', [])[-1:] != [version]:
            raise ValueError('Edit base is stale against the latest public observation; read the intended current version')
        data = copy.deepcopy(self.reads[(oid, version)])
        node = data
        for component in arguments['locator'][:-1]:
            if isinstance(node, list) and (type(component) is not int or component < 0):
                raise ValueError('List locators need nonnegative integer indices')
            node = node[component]
        last = arguments['locator'][-1]
        if isinstance(node, list) and (type(last) is not int or last < 0):
            raise ValueError('List locators need nonnegative integer indices')
        if not isinstance(node[last], str):
            raise ValueError('Only an existing string leaf can be replaced')
        node[last] = arguments['new_text']
        actual = {'alias': alias, 'data': data, 'dependencies': copy.deepcopy(arguments['dependencies'])}
        if 'work_id' in arguments:
            actual['work_id'] = arguments['work_id']
        return self._world_call('write_object', actual, key, association)

    def snapshot(self):
        return {'version': VERSION, 'owner_role': self.role_id, 'notes': copy.deepcopy(self.notes),
                'todos': copy.deepcopy(self.todos), 'history_entries': len(self.history),
                'history_sha256': digest(json_bytes(self.history)),
                'read_references': [list(ref) for ref in self.reads]}
