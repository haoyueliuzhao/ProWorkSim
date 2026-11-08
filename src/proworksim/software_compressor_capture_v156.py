"""Exact, CPU-only compressor request/response capture without a second budget.

The renderer alone reserves/settles the shared team pool. This wrapper observes
one physical delegate call. A published-message content hash is an artifact
content identity, never a repository tree/patch version hash. No network client
or third autonomous member is introduced.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .software_communication_pilot_v156 import (
    COMPRESSOR_SETTINGS, FIELDS, PROMPT_SHA256, PROMPT_VERSIONS, ROLE_FIELDS,
    SYSTEM_PROMPTS, SourceRejected, canonical, fact_text,
)
from .software_input_provenance_v156 import (
    SourceFragment, annotate_tree,
    build_request, capture_response, persist_request,
)
from .software_sdk_input_sources_v156 import annotate_json_text

VERSION = 'v156-audited-compressor-capture-r1'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, data):
    encoded = canonical(data)
    with path.open('xb') as stream:
        stream.write(encoded)
    return {'path': str(path), 'sha256': _sha(encoded), 'bytes': len(encoded)}


class AuditedCompressorTransport:
    """Callable(raw_payload_bytes, identity=...) with explicit CPU transport only.

    `receipts` contains one immutable capture reference per actual attempt,
    including a failed delegate attempt. It is not a second usage ledger.
    """
    evidence_domain = 'cpu_synthetic'

    def __init__(self, directory, store, delegate, episode_id):
        if getattr(delegate, 'evidence_domain', None) != 'cpu_synthetic':
            raise PermissionError('Real P1 compressor transport is not enabled')
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError('A concrete episode identity is required')
        self.directory, self.store, self.delegate = Path(directory), store, delegate
        self.episode_id, self.receipts, self.errors = episode_id, [], []
        self.directory.mkdir(parents=True, exist_ok=True)

    def _annotate(self, raw_payload, identity):
        if not isinstance(raw_payload, bytes):
            raise TypeError('Capture requires the exact serialized request bytes')
        if identity.get('episode_id') != self.episode_id:
            raise SourceRejected('Compressor capture must belong to the same shared team budget')
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict) or set(payload) != set(COMPRESSOR_SETTINGS) | {'messages'}:
            raise SourceRejected('Compressor request cannot add tools or unregistered fields')
        if canonical(payload) != raw_payload:
            raise SourceRejected('Compressor payload must be the exact canonical wire serialization')
        condition = identity['condition']
        if condition not in {'C1', 'C2'}:
            raise SourceRejected('C0 cannot dispatch a compressor')
        ref = {k: identity[k] for k in ('source_id', 'version_hash')}
        source = self.store.get(ref)
        if identity['recipient'] not in source['recipients']:
            raise PermissionError('Compressor source recipient lacks publication access')
        messages = payload.get('messages')
        if (not isinstance(messages, list) or len(messages) != 2
                or messages[0] != {'role': 'system', 'content': SYSTEM_PROMPTS[condition]}
                or messages[1].get('role') != 'user'):
            raise SourceRejected('Compressor payload does not match the frozen producer shape')
        for name, expected in COMPRESSOR_SETTINGS.items():
            if payload.get(name) != expected:
                raise SourceRejected('Compressor settings differ from frozen design')
        if (identity.get('payload_sha256') != _sha(raw_payload)
                or identity.get('prompt_sha256') != PROMPT_SHA256[condition]
                or identity.get('prompt_version') != PROMPT_VERSIONS[condition]):
            raise SourceRejected('Compressor producer identity differs from actual bytes/prompt')
        data = json.loads(messages[1]['content'])
        if set(data) != {'source_id', 'version_hash', 'recipient_role', 'field_priority', 'facts'}:
            raise SourceRejected('Unexpected compressor source fields')
        if any(data[k] != ref[k] for k in ref):
            raise SourceRejected('Compressor content reference changed')
        if (data['recipient_role'] != 'generic' if condition == 'C1'
                else data['recipient_role'] not in ROLE_FIELDS):
            raise SourceRejected('Compressor role selection is not frozen')
        expected_order = FIELDS if condition == 'C1' else ROLE_FIELDS[data['recipient_role']]
        expected_facts = [{**f, 'text': fact_text(source, f)} for f in source.get('facts', [])]
        if (data['facts'] != expected_facts or data['field_priority'] != list(expected_order)
                or not source.get('facts_complete')):
            raise SourceRejected('Compressor facts are not the exact complete immutable producer spans')
        event_id = source.get('metadata', {}).get('published_event_id') or source['source_id']
        template = SourceFragment('Base/Template', 'compressor-template:'+PROMPT_SHA256[condition],
            'compressor-prompt:'+PROMPT_VERSIONS[condition], 'compression-service', 'template')
        content_ref = SourceFragment('Artifact', 'published-message-content:'+ref['version_hash'],
            event_id, source['sender'], 'index', artifact_sha256=ref['version_hash'],
            version_sha256=None, parent_source_ids=(ref['source_id'],))

        def classify(path, value, _):
            if len(path) == 3 and path[0] == 'facts' and type(path[1]) is int and path[2] == 'text':
                fact = source['facts'][path[1]]
                # The raw slice was verified above; this field occurrence has a
                # specific fact identity even when another fact has equal text.
                return SourceFragment('Peer-message', ref['source_id']+':fact:'+fact['fact_id'],
                    event_id, source['sender'], 'excerpt', artifact_sha256=ref['version_hash'],
                    version_sha256=None, parent_source_ids=(ref['source_id'],))
            if path in {('source_id',), ('version_hash',)}:
                return content_ref
            return template

        annotated = annotate_tree(payload, template)
        annotated['messages'][1]['content'] = annotate_json_text(messages[1]['content'], template, classify)
        now = datetime.now(timezone.utc).isoformat()
        request_identity = {**copy.deepcopy(identity),
            'episode_id': self.episode_id, 'member_id': 'compression-service',
            'decision_id': identity['request_id'].rsplit(':compressor:', 1)[0],
            'attempt_id': identity['request_id'], 'model_alias': payload['model'],
            'request_time': now, 'purpose': 'compressor', 'autonomous_member': False}
        built = build_request(annotated, request_identity, template_source=template)
        if built.payload_bytes != raw_payload:
            raise SourceRejected('Source annotations changed the actual compressor request')
        source_projection = {'source_ref': ref, 'sender': source['sender'], 'recipient': identity['recipient'],
            'source_id_semantics': 'immutable_published_message',
            'version_hash_semantics': 'published_communication_content_sha256_not_code_tree_hash',
            'artifact_sha256': ref['version_hash'], 'repository_version_sha256': None,
            'facts': [{k: fact[k] for k in ('fact_id', 'start_character', 'end_character', 'provenance')}
                      for fact in source['facts']],
            'raw_message_sha256': _sha(source['raw_text'].encode()),
            'capture_changes_budget': False, 'captured_transport_domain': 'cpu_synthetic'}
        return built, source_projection

    def _observe_write(self, receipt, key, path, value):
        """An observation write after dispatch must not change payment/retry."""
        try:
            receipt[key] = _write(path, value)
        except Exception as error:
            item = {'request_id': receipt['request_id'], 'stage': key,
                    'exception_type': type(error).__name__,
                    'error_sha256': _sha(str(error).encode())}
            receipt.setdefault('observer_errors', []).append(item)
            self.errors.append(copy.deepcopy(item))

    def _finish_observation(self, folder, receipt):
        self._observe_write(receipt, 'saved_receipt', folder/'receipt.json', copy.deepcopy(receipt))
        self.receipts.append(copy.deepcopy(receipt))

    def __call__(self, raw_payload_bytes, *, identity):
        built, source_projection = self._annotate(raw_payload_bytes, identity)
        capture = persist_request(self.directory, built)
        folder = Path(capture['payload']['path']).parent
        capture_ref = _write(folder/'capture.json', capture)
        source_ref = _write(folder/'source-projection.json', source_projection)
        dispatch_ref = _write(folder/'dispatch-entered.json', {
            'request_id': identity['request_id'], 'domain': 'cpu_synthetic',
            'payload_sha256': _sha(raw_payload_bytes), 'budget_owner': 'CommunicationRenderer.pool'})
        receipt = {'version': VERSION, 'request_id': identity['request_id'],
            'request_capture': capture_ref, 'payload': capture['payload'], 'provenance': capture['manifest'],
            'source_projection': source_ref, 'dispatch': dispatch_ref,
            'request_wire_bytes_exact': True, 'response_is_decoded_object_not_claimed_wire_bytes': True,
            'budget_reserved_or_settled_by_wrapper': False}
        try:
            body = self.delegate(raw_payload_bytes, identity=copy.deepcopy(identity))
        except Exception as error:
            status = getattr(error, 'http_status', None)
            if type(status) is not int:
                status = None
            original_body = getattr(error, 'response_body', None)
            if not isinstance(original_body, dict):
                original_body = {'usage': copy.deepcopy(error.usage)} if getattr(error, 'usage', None) is not None else None
            error_record = {'type': type(error).__name__, 'reason': str(error), 'http_status': status,
                            'usage': copy.deepcopy(getattr(error, 'usage', None)),
                            'retryable': getattr(error, 'retryable', None), 'response_body': original_body}
            self._observe_write(receipt, 'exception', folder/'exception-original.json', error_record)
            try:
                response = capture_response(built, original_body, outcome='http_error' if status else 'transport_unknown',
                    http_status=status, response_time=datetime.now(timezone.utc).isoformat(), error=error_record)
            except Exception:
                response = capture_response(built, None, outcome='transport_unknown', http_status=status,
                    error={'reason': 'malformed_exception_usage', 'raw_exception_preserved': 'exception' in receipt})
            self._observe_write(receipt, 'response', folder/'response.json', response)
            receipt['outcome'] = response['outcome']
            self._finish_observation(folder, receipt)
            raise
        self._observe_write(receipt, 'original_response', folder/'response-original.json', body)
        try:
            outcome = 'success' if isinstance(body, dict) and isinstance(body.get('usage'), dict) else 'transport_unknown'
            response = capture_response(built, body if isinstance(body, dict) else None,
                outcome=outcome, http_status=200, response_time=datetime.now(timezone.utc).isoformat())
        except Exception:
            response = capture_response(built, None, outcome='transport_unknown', http_status=200,
                error={'reason': 'malformed_response_usage', 'raw_response_preserved': 'original_response' in receipt})
        self._observe_write(receipt, 'response', folder/'response.json', response)
        receipt['outcome'] = response['outcome']
        self._finish_observation(folder, receipt)
        return body
