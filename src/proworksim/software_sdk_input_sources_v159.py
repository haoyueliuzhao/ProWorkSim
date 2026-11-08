"""v157 source tags for real compressed communications and existing SDK events.

This changes no prompt text, role, tool, condenser, routing, or budget. Unknown
inputs remain unknown. Event order and explicit JSON paths establish origin;
matching arbitrary text against a history is intentionally not supported.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .software_input_provenance_v156 import (
    AnnotatedText, SourceFragment, TextSegment, annotate_tree,
    build_request, capture_response, persist_request,
)


def raw(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(raw(value)).hexdigest()


def source(category, event_id, member, *, pointer='', value=None, transformation='raw',
           source_id=None, version_sha256=None, parent_source_ids=()):
    identity = source_id or f'{event_id}:{pointer}'
    artifact = sha(value) if category == 'Artifact' else None
    return SourceFragment(category, identity, event_id, member,
                          transformation=transformation, artifact_sha256=artifact,
                          version_sha256=version_sha256, parent_source_ids=tuple(parent_source_ids))


def published_version_bindings(owner):
    """Read actual publication receipts, not arbitrary literal metadata hashes."""
    result = {}
    observer = getattr(owner, 'observation', None)
    for row in getattr(getattr(observer, 'log', None), '_rows', {}).values():
        if row.get('kind') != 'artifact_published':
            continue
        data = row['data']
        identity = data.get('content_identity') or {}
        ref = data.get('source_reference')
        files, metadata = identity.get('files_sha256'), identity.get('entry_metadata_sha256')
        if (not isinstance(ref, dict) or not isinstance(files, str) or len(files) != 64
                or not isinstance(metadata, str) or len(metadata) != 64):
            continue
        payload = {'source_reference': ref, 'files_sha256': files, 'entry_metadata_sha256': metadata}
        result[sha(ref)] = {**payload, 'version_identity_sha256': sha(payload),
                           'publication_event_id': row.get('event_id', row.get('id')),
                           'definition': 'SHA256 of canonical source reference plus actual files/metadata digests'}
    bridge = getattr(owner, 'communication_v157', None)
    if bridge is not None:
        result['_communication_v157'] = {bridge.records[sequence]['ref']['source_id']: {
            'version_hash': bridge.records[sequence]['ref']['version_hash'],
            'representation': rendered['representation'],
            'text': rendered.get('L1'), 'segments': copy.deepcopy(rendered.get('L1_source_segments', []))}
            for (sequence, recipient), rendered in bridge.rendered.items()}
    return result


def annotate_json_text(text, default_source, classify):
    """Walk JSON syntax and retain literal offsets, escapes and whitespace."""
    decoder = json.JSONDecoder()
    root = json.loads(text)
    spans = []

    def spaces(position):
        while position < len(text) and text[position].isspace():
            position += 1
        return position

    def walk(position, path):
        position = spaces(position)
        value, end = decoder.raw_decode(text, position)
        if isinstance(value, dict):
            cursor = spaces(position + 1)
            while cursor < end - 1:
                key, cursor = decoder.raw_decode(text, cursor)
                cursor = spaces(cursor)
                if text[cursor] != ':':
                    raise ValueError('Invalid JSON field boundary')
                cursor = walk(cursor + 1, (*path, key))
                cursor = spaces(cursor)
                if cursor < end - 1:
                    if text[cursor] != ',':
                        raise ValueError('Invalid JSON object separator')
                    cursor = spaces(cursor + 1)
        elif isinstance(value, list):
            cursor, index = spaces(position + 1), 0
            while cursor < end - 1:
                cursor = spaces(walk(cursor, (*path, index)))
                index += 1
                if cursor < end - 1:
                    if text[cursor] != ',':
                        raise ValueError('Invalid JSON list separator')
                    cursor = spaces(cursor + 1)
        else:
            # Quotes/delimiters belong to the observation rendering, not the
            # peer author's message body. Escape sequences retain wire offsets.
            start, stop = (position + 1, end - 1) if isinstance(value, str) else (position, end)
            if stop > start:
                origin = classify(path, value, root)
                if isinstance(origin, AnnotatedText):
                    if not isinstance(value, str) or ''.join(s.text for s in origin.segments) != value:
                        raise ValueError('Structured communication annotation changed its actual scalar')
                    encoded = None
                    for ascii_mode in (False, True):
                        candidate = [json.dumps(s.text, ensure_ascii=ascii_mode)[1:-1] for s in origin.segments]
                        if ''.join(candidate) == text[start:stop]:
                            encoded = candidate
                            break
                    if encoded is None:
                        raise ValueError('Communication string escaping differs from exact source segments')
                    cursor = start
                    for piece, segment in zip(encoded, origin.segments, strict=True):
                        if piece:
                            spans.append((cursor, cursor+len(piece), segment.source))
                        cursor += len(piece)
                else:
                    spans.append((start, stop, origin))
        return end

    final = spaces(walk(0, ()))
    if final != len(text):
        raise ValueError('Trailing content is not part of this registered JSON source')
    pieces, cursor = [], 0
    for start, end, origin in spans:
        if start > cursor:
            pieces.append(TextSegment(text[cursor:start], default_source))
        pieces.append(TextSegment(text[start:end], origin or default_source))
        cursor = end
    if cursor < len(text):
        pieces.append(TextSegment(text[cursor:], default_source))
    return AnnotatedText(tuple(pieces))


def observation_text(text, *, event_id, member, episode_id='unbound-local-control', artifact_bindings=None):
    default = source('Tool-feedback', event_id, member, transformation='structured')
    artifact_bindings = artifact_bindings or {}

    def classify(path, value, root):
        pointer = '/'.join(map(str, path))
        if path and (path[0] == 'role_task' or path[:2] in {
                ('observation', 'root_goal'), ('observation', 'contract')}):
            manifest = root.get('observation', {}).get('source_contract_sha256')
            origin = 'task-manifest:' + manifest if isinstance(manifest, str) else event_id
            return source('Task', origin, 'public-task', pointer=pointer, value=value)
        if len(path) >= 4 and path[0] == 'observation' and path[1] in {'messages', 'handoffs'}:
            message = root['observation'][path[1]][path[2]]
            publication = message.get('communication')
            if isinstance(publication, dict) and publication.get('source_id') and publication.get('version_hash'):
                parent = publication['source_id']
                if path[3] in {'body', 'message', 'reason'}:
                    representation = publication.get('representation', 'raw')
                    origin = f"{episode_id}:world-message:{message['sequence']}"
                    if representation != 'raw':
                        binding = artifact_bindings.get('_communication_v157', {}).get(parent)
                        if (not binding or binding['version_hash'] != publication['version_hash']
                                or binding['representation'] != representation or binding['text'] != value):
                            raise ValueError('Compressed communication lacks its exact source-span binding')
                        template = source('Base/Template', 'communication-format:v157', 'harness',
                            source_id='communication-format:v157', transformation='template')
                        return AnnotatedText(tuple(TextSegment(segment['text'],
                            source('Peer-message', origin, message['actor_id'],
                                source_id=parent+':fact:'+segment['fact_id'], transformation='compressed',
                                parent_source_ids=(parent,)) if segment['fact_id'] else template)
                            for segment in binding['segments']))
                    return source('Peer-message', origin, message['actor_id'], source_id=parent,
                        transformation='excerpt' if message.get(str(path[3])+'_truncated') else 'raw')
                if path[3] == 'communication':
                    return source('Artifact', event_id, member, pointer=pointer, value=publication,
                        source_id='communication-index:'+parent+':'+pointer, transformation='index',
                        parent_source_ids=(parent,))
        if len(path) >= 4 and path[:2] == ('observation', 'messages') and path[3] == 'body':
            message = root['observation']['messages'][path[2]]
            author = message.get('actor_id', message.get('actor'))
            sequence = message.get('sequence')
            if (author and author != member and message.get('recipient') == member
                    and sequence is not None):
                return source('Peer-message', f'{episode_id}:world-message:{sequence}', author,
                              pointer='body', transformation='excerpt' if message.get('body_truncated') else 'raw')
        if len(path) >= 2 and path[0] == 'observation' and path[1] in {
                'patches', 'handoffs', 'deliveries', 'source_reference', 'all_fixed_patches'}:
            item = root['observation'][path[1]]
            if isinstance(item, list) and len(path) > 2 and isinstance(path[2], int):
                item = item[path[2]]
            ref = item.get('source_reference') if isinstance(item, dict) else None
            binding = artifact_bindings.get(sha(ref)) if isinstance(ref, dict) else None
            return source('Artifact', event_id, member, pointer=pointer, value=value,
                          transformation='index', source_id='metadata:'+event_id+':'+pointer,
                          version_sha256=binding['version_identity_sha256'] if binding else None,
                          parent_source_ids=(binding['publication_event_id'],) if binding and binding['publication_event_id'] else ())
        return default

    return annotate_json_text(text, default, classify)


def registered_format_feedback(message, origin, member, episode_id, records):
    """Bind a runner's registered rejection by identity and exact SDK event.

    A JSON field name alone confers no source authority. The existing feedback
    ledger has already checked the original response ID/hash and decision. Here
    the actual SDK event must be that registered original user-channel message;
    only the unchanged original or its registered compact projection is valid.
    """
    if message.get('role') != 'user' or not isinstance(message.get('content'), str):
        return None
    events = origin.get('events') or []
    if len(events) != 1 or events[0].get('kind') != 'MessageEvent':
        return None
    event = events[0]
    llm = event.get('llm_message', {})
    blocks = llm.get('content') or []
    if (event.get('source') != 'user' or llm.get('role') != 'user'
            or len(blocks) != 1 or blocks[0].get('type') != 'text'):
        return None
    original = blocks[0].get('text')
    try:
        value = json.loads(original)
        if set(value) != {'public_format_feedback'}:
            return None
        call = value['public_format_feedback']['model_call_id']
    except (TypeError, ValueError, KeyError):
        return None
    record = (records or {}).get(member+':'+call)
    if (not isinstance(record, dict) or record.get('runner_source') != 'model_format_feedback'
            or record.get('member_id') != member or record.get('call_id') != call
            or record.get('association', {}).get('worker_id') != member
            or not record.get('source_event_id')
            or original != record.get('original_message', {}).get('content')
            or hashlib.sha256(original.encode()).hexdigest() != record.get('original_content_sha256')
            or message['content'] not in {
                record.get('original_message', {}).get('content'),
                record.get('visible_message', {}).get('content')}):
        return None
    return source('Tool-feedback', record['source_event_id'], member,
        source_id=f'{episode_id}:runner-format-feedback:{record["feedback_id"]}',
        transformation='raw' if message['content'] == original else 'structured',
        parent_source_ids=('sdk:'+event['id'],))


def annotate_message(message, origin, *, member, episode_id='unbound-local-control',
                     artifact_bindings=None, feedback_records=None):
    """Use explicit SDK event type/tool identity, never infer from similar text."""
    event_ids = origin.get('event_ids', [])
    event_types = origin.get('event_types', [])
    if not event_ids or not event_types:
        return copy.deepcopy(message)
    event_id = 'sdk:' + '+'.join(event_ids)
    role = message.get('role')
    if role == 'system' and any('System' in kind for kind in event_types):
        return annotate_tree(message, source('Base/Template', event_id, member, transformation='template'))
    if any('CondensationSummary' in kind for kind in event_types):
        return annotate_tree(message, source('Summary', event_id, member, transformation='summary'))
    if role == 'assistant':
        return annotate_tree(message, source('Self-history', event_id, member))
    if role == 'tool':
        events = origin.get('events') or []
        tool = origin.get('tool_name') or message.get('name')
        call = message.get('tool_call_id') or origin.get('tool_call_id')
        tool_parents = (f'sdk-tool-call:{episode_id}:{member}:{call}',) if call else ()
        if tool is None and events and isinstance(events[0], dict):
            tool = events[0].get('tool_name')
        if tool == 'read_file' and isinstance(message.get('content'), str):
            try:
                envelope = json.loads(message['content'])
            except ValueError:
                envelope = {}
            item = envelope.get('result', {}) if isinstance(envelope, dict) else {}
            required = {'path', 'source_reference', 'text_sha256', 'start_character', 'end_character', 'text'}
            if envelope.get('ok') is True and isinstance(item, dict) and required <= set(item):
                material = {k: item[k] for k in ('path', 'text_sha256', 'start_character', 'end_character')}
                parent = f'{episode_id}:file-material:{sha(material)}'
                default = source('Tool-feedback', event_id, member, parent_source_ids=tool_parents)
                def classify_file(path, value, root):
                    if path == ('result', 'text'):
                        # Member identifies the authorized retrieval producer;
                        # this does not guess who authored the file's contents.
                        return source('Retrieved', event_id, member, pointer='file-text',
                            transformation='excerpt', parent_source_ids=(parent, *tool_parents))
                    if len(path) > 1 and path[0] == 'result' and path[1] in required - {'text'}:
                        return source('Artifact', event_id, member, pointer='/'.join(map(str, path)),
                            value={'retrieved_file_descriptor': material, 'source_reference': item['source_reference']},
                            source_id='metadata:'+event_id+':'+str(path), parent_source_ids=tool_parents)
                    return default
                value = annotate_tree(message, default)
                value['content'] = annotate_json_text(message['content'], default, classify_file)
                return value
        if tool == 'read_work_event' and isinstance(message.get('content'), str):
            try:
                envelope = json.loads(message['content'])
            except ValueError:
                envelope = {}
            item = envelope.get('result', {}) if isinstance(envelope, dict) else {}
            if (envelope.get('ok') is True and isinstance(item, dict)
                    and item.get('kind') == 'communication_pull' and item.get('recipient') == member):
                parent = item['source_id']
                default = source('Tool-feedback', event_id, member, parent_source_ids=tool_parents)
                def classify_layer(path, value, root):
                    if path == ('result', 'text'):
                        return source('Retrieved', f"{episode_id}:world-message:{item['sequence']}",
                            item['actor_id'], source_id=event_id+':'+item['level']+':'+parent,
                            transformation='excerpt' if item['level'] == 'L2' else 'excerpt',
                            parent_source_ids=(parent, *tool_parents))
                    return default
                value = annotate_tree(message, default)
                value['content'] = annotate_json_text(message['content'], default, classify_layer)
                return value
        if tool == 'read_work_event' and isinstance(message.get('content'), str):
            try:
                envelope = json.loads(message['content'])
            except ValueError:
                envelope = {}
            item = envelope.get('result', {}) if isinstance(envelope, dict) else {}
            if (envelope.get('ok') is True and isinstance(item, dict)
                    and item.get('kind') in {'work_message', 'handoff'} and item.get('recipient') == member
                    and item.get('actor_id') and item.get('sequence') is not None):
                field = 'body' if item.get('kind') == 'work_message' else 'message'
                parent = f"{episode_id}:world-message:{item['sequence']}:{field}"
                default = source('Tool-feedback', event_id, member, parent_source_ids=tool_parents)
                def classify(path, value, root):
                    if path == ('result', field):
                        return source('Retrieved', f"{episode_id}:world-message:{item['sequence']}",
                            item['actor_id'], source_id=event_id+':retrieved-message-body',
                            transformation='full', parent_source_ids=(parent, *tool_parents))
                    return default
                value = annotate_tree(message, default)
                value['content'] = annotate_json_text(message['content'], default, classify)
                return value
        if tool in {'read_file', 'read_test_result', 'read_work_event', 'work_history_read'}:
            category = 'Retrieved'
        elif tool in {'fix_patch', 'integrate_patch', 'diff_workspace', 'handoff_patch'}:
            category = 'Artifact'
        else:
            category = 'Tool-feedback'
        binding = None
        if category == 'Artifact':
            try:
                item = json.loads(message.get('content', '{}')).get('result', {})
                ref = item.get('source_reference')
                binding = (artifact_bindings or {}).get(sha(ref)) if isinstance(ref, dict) else None
            except (ValueError, TypeError, AttributeError):
                pass
        return annotate_tree(message, source(category, event_id, member, value=message,
            source_id=('metadata:' if category == 'Artifact' else '')+event_id,
            version_sha256=binding['version_identity_sha256'] if binding else None,
            parent_source_ids=((binding['publication_event_id'],) if binding and binding['publication_event_id'] else ())
                              + tool_parents))
    if role == 'user' and 'MessageEvent' in event_types:
        feedback_source = registered_format_feedback(message, origin, member, episode_id, feedback_records)
        if feedback_source is not None:
            return annotate_tree(message, feedback_source)
        events = origin.get('events') or []
        from .software_benchmark_finish_review_v117 import SENDER
        if events and all(isinstance(e, dict) and e.get('sender') == SENDER for e in events):
            return annotate_tree(message, source('Base/Template', event_id, member, transformation='template'))
        value = copy.deepcopy(message)
        content = message.get('content')
        if isinstance(content, str):
            try:
                decoded = json.loads(content)
            except ValueError:
                decoded = None
            known_observation = isinstance(decoded, dict) and 'observation' in decoded and 'role_task' in decoded
            if (isinstance(decoded, dict) and 'observation' in decoded
                    and '_v117_same_input_static_fields' in decoded
                    and origin.get('verified_observation_projection') is True):
                original = origin.get('wire_message', {}).get('content')
                try:
                    original_value = json.loads(original)
                except (ValueError, TypeError):
                    original_value = None
                known_observation = (isinstance(original_value, dict)
                                     and 'role_task' in original_value and 'observation' in original_value)
            if known_observation:
                value = annotate_tree(value, source('Base/Template', event_id, member, transformation='template'))
                value['content'] = observation_text(content, event_id=event_id, member=member,
                    episode_id=episode_id, artifact_bindings=artifact_bindings)
                return value
        # Known SDK user event origin remains visible; an unregistered free-form
        # prompt is not automatically labelled Task, Self-history or feedback.
    return copy.deepcopy(message)


def annotate_agent_wire(wire, origins, *, member, projection=None,
                        episode_id='unbound-local-control', artifact_bindings=None, feedback_records=None):
    output = copy.deepcopy(wire)
    base = source('Base/Template', 'frozen-member-tool-schema:'+sha(wire.get('tools', [])),
                  member, transformation='template')
    output['tools'] = annotate_tree(wire.get('tools', []), base)
    projection = projection or {}
    indices = projection.get('format_feedback_projection', {}).get('selected_indices')
    if indices is None:
        indices = list(range(len(wire.get('messages', []))))
    if len(indices) != len(wire.get('messages', [])) or any(i < 0 or i >= len(origins) for i in indices):
        return output, base, {'source_mapping': 'unavailable_index_projection'}
    messages = []
    for message, index in zip(wire['messages'], indices):
        origin = copy.deepcopy(origins[index])
        origin['verified_observation_projection'] = (
            projection.get('observation_history_projection', {}).get('validation', {}).get('passed') is True)
        original = origin.get('wire_message', {})
        if original.get('role') != message.get('role'):
            messages.append(copy.deepcopy(message))
            continue
        if message.get('role') == 'tool' and original.get('tool_call_id') != message.get('tool_call_id'):
            messages.append(copy.deepcopy(message))
            continue
        messages.append(annotate_message(message, origin, member=member,
            episode_id=episode_id, artifact_bindings=artifact_bindings, feedback_records=feedback_records))
    output['messages'] = messages
    return output, base, {'source_mapping': 'explicit_sdk_event_indices', 'selected_indices': indices}


class SDKRequestCapture:
    """Native runtime callback. Canonical request bytes are never changed."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pending, self.completed = {}, []

    def request(self, member, payload, worker, owner):
        wire = payload['wire']
        request_id = payload['request_id']
        if request_id in self.pending or any(r['response']['request_id'] == request_id for r in self.completed):
            raise ValueError('A captured logical request cannot silently be re-entered')
        purpose = payload.get('usage_id')
        identity = {'request_id': request_id, 'attempt_id': request_id,
            'episode_id': owner.window_id, 'member_id': member,
            'decision_id': request_id, 'model_alias': wire['model'],
            'request_time': datetime.now(timezone.utc).isoformat(),
            'usage_id': purpose, 'capture_boundary': 'controller_logical_request',
            'physical_HTTP_capture_required_separately': True}
        projection = {}
        feedback_records = copy.deepcopy(getattr(
            getattr(getattr(worker, 'transport', None), 'feedback_ledger', None), 'records', {}))
        if worker is not None:
            prepared = getattr(worker.transport, '_prepared', None)
            if prepared:
                projection = prepared.get('projection', {})
            elif purpose == 'agent':
                # The unchanged context transport writes this exact projection
                # before dispatch and clears _prepared. Read only that counter's
                # evidence, not another historical matching prompt.
                folder = Path(worker.transport.directory)/f'request-{worker.transport.counter:05d}'
                evidence_path = folder/'projection.json'
                if evidence_path.is_file():
                    from .storage import digest, json_bytes
                    projection = json.loads(evidence_path.read_bytes())
                    if projection.get('wire_request_sha256') != digest(json_bytes(wire)):
                        raise ValueError('Current context projection belongs to another actual request')
        if worker is not None and purpose == 'agent':
            artifacts = published_version_bindings(owner)
            annotated, template, evidence = annotate_agent_wire(wire,
                getattr(worker, '_v156_input_origins', []), member=member, projection=projection,
                episode_id=owner.window_id, artifact_bindings=artifacts, feedback_records=feedback_records)
        elif worker is not None and purpose == 'condenser':
            from .software_condenser_input_sources_v159 import annotate_condenser_wire
            artifacts = published_version_bindings(owner)
            annotated, template, evidence = annotate_condenser_wire(wire, worker, member,
                episode_id=owner.window_id, artifact_bindings=artifacts, feedback_records=feedback_records)
        else:
            annotated, template = copy.deepcopy(wire), None
            evidence = {'source_mapping': 'unattributed_auxiliary_request',
                        'reason': 'pending explicit condenser template span binding'}
        built = build_request(annotated, identity, template_source=template)
        if built.payload_bytes != raw(wire):
            raise ValueError('Provenance changed the actual member request')
        capture = persist_request(self.directory, built)
        (Path(capture['payload']['path']).parent/'source-mapping-evidence.json').write_bytes(raw(evidence))
        self.pending[request_id] = {'request': built, 'capture': capture,
                                    'annotated_payload': annotated, 'template_source': template,
                                    'projection_evidence': copy.deepcopy(projection), **evidence}
        if purpose in {'agent', 'condenser'} and worker is not None:
            (Path(capture['payload']['path']).parent/'published-version-bindings.json').write_bytes(raw(artifacts))

    def http_annotations(self, wire, context):
        """Use the same source tree for each physical retry of this logical call."""
        row = self.pending.get(context['logical_id'])
        if row is None or row['request'].payload_bytes != raw(wire):
            raise ValueError('Physical HTTP lacks the exact current SDK source binding')
        identity = row['request'].manifest['identity']
        if identity['member_id'] != context['member_id'] or identity['episode_id'] != context['slot_id']:
            raise ValueError('A source map cannot cross member or episode boundaries')
        return {'payload': copy.deepcopy(row['annotated_payload']),
                'template_source': row['template_source']}

    def response(self, member, payload, body, worker, owner):
        row = self.pending.pop(payload['request_id'])
        cancelled = any(x.get('request_id') == payload['request_id']
                        for x in getattr(owner, 'pre_dispatch_boundaries', []))
        result = capture_response(row['request'], body,
            outcome='success' if body is not None else
                    ('cancelled_before_dispatch' if cancelled else 'transport_unknown'),
            http_status=200 if body is not None else None,
            response_time=datetime.now(timezone.utc).isoformat())
        folder = Path(row['capture']['payload']['path']).parent
        if body is not None:
            (folder/'response-original.json').write_bytes(raw(body))
        (folder/'response.json').write_bytes(raw(result))
        (folder/'projection-evidence.json').write_bytes(raw(row['projection_evidence']))
        self.completed.append({**row, 'response': result})
        observer = getattr(owner, 'observation', None)
        if observer is not None and hasattr(observer, 'observe_source_presentations'):
            observer.observe_source_presentations(member, row['request'], result)
