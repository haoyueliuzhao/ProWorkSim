"""Real published-message presentation for the three frozen REVIEW2 conditions.

No transport, workspace inspection, scheduling, model or accounting authority is
created here. The owner supplies one charged compression service. Exact sender
claims remain claims; deterministic extraction is eligibility, not truth proof.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from types import MethodType

from .software_communication_pilot_v156 import (
    CommunicationRenderer, ImmutableCommunicationStore, SourceRejected,
    COMPRESSOR_SETTINGS, FIELDS, ROLE_FIELDS, SYSTEM_PROMPTS,
    PROMPT_SHA256, PROMPT_VERSIONS, canonical, fact_text,
)
from .software_communication_runtime_v156 import AccountingConflict
from .software_benchmark_deepseek_contract_v105 import PreDispatchBudgetStopped
from .software_benchmark_deepseek_api_v157 import APIUncertainFailure
from .software_input_provenance_v156 import SourceFragment, annotate_tree
from .software_sdk_input_sources_v156 import annotate_json_text

VERSION = 'v157-real-communication-presentation-r1'
FACT_RULE_VERSION = 'v157-exact-sentence-claims-protected-facts-r1'
PREVIEW_CHARACTERS = 500
PREVIEW_COUNT = 4

_LABELS = {
    'conclusion': ('conclusion', 'decision', 'result', '结论', '决定'),
    'next_action': ('next action', 'next', 'action', 'request', 'todo', '下一步', '请求'),
    'change': ('change', 'changes', 'implementation', 'context', 'background', 'reason', '修改', '背景', '原因'),
    'test_status': ('test', 'tests', 'test status', 'validation', '测试', '验证'),
    'risk': ('risk', 'risks', 'warning', '风险', '注意'),
    'unknown': ('unknown', 'uncertainty', 'blocked', '未知', '阻塞'),
}
_LABEL_PATTERN = re.compile(r'^\s*(?:[-*]\s*)?(?P<label>' + '|'.join(
    re.escape(v) for values in _LABELS.values() for v in values) + r')\s*[:：]\s*', re.I)
_PROTECTED = re.compile(
    r'\b(?:not|never|no|must|required|fail(?:ed|ure|s)?|error|except(?:ion)?|timeout|'
    r'pass(?:ed|es)?|pytest|test(?:s|ed)?|unverified|unknown|risk|block(?:ed)?|'
    r'patch[-_ ]?\d+|version|commit|hash|sha256|sha1)\b|'
    r'[0-9]|[/\\]|`|[\[\]{}]|[\w-]+\.(?:py|js|ts|json|toml|yaml|yml|cfg|ini|rst|md)\b|'
    r'不|未|须|必须|失败|错误|测试|风险|版本|待确认', re.I)
_OPTIONAL_LABEL = re.compile(r'^\s*(?:[-*]\s*)?(?:context|background|reason|背景|原因)\s*[:：]', re.I)


def source_facts(text):
    """Complete exact source spans with conservative lexical protection.

    Explicit field labels are trusted *structure*, never trusted factual claims.
    Unlabelled sentences are eligible only for fixed coding-message grammars.
    Ambiguous prose, fenced code, empty or very long single claims use raw preview.
    Critical facts cannot be dropped; unknown/test states are always critical.
    """
    if not text.strip() or '```' in text or '\x00' in text:
        return [], False, 'unstructured_or_code_block'
    facts, complete, reasons = [], True, []
    # Do not split decimals, dotted paths, code identifiers or abbreviations at a
    # bare period. A sentence boundary needs following whitespace and uppercase.
    ends = [m.end() for m in re.finditer(r'\n+|[。！？]+|[.!?](?=\s+[A-Z])', text)]
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
    start = 0
    for end in ends:
        raw = text[start:end]
        left = start + len(raw)-len(raw.lstrip())
        right = end-(len(raw)-len(raw.rstrip()))
        start = end
        if left >= right:
            continue
        sentence = text[left:right]
        match = _LABEL_PATTERN.match(sentence)
        field = None
        if match:
            label = match['label'].lower()
            field = next(k for k, values in _LABELS.items() if label in values)
        elif re.search(r'\b(?:unknown|unsure|uncertain|unverified|blocked)\b|未知|不确定|阻塞', sentence, re.I):
            field = 'unknown'
        elif re.search(r'\b(?:test|tests|pytest|passed|failed|failure|traceback)\b|测试|验证', sentence, re.I):
            field = 'test_status'
        elif re.search(r'\b(?:risk|warning|regression|exception)\b|风险|注意|回归', sentence, re.I):
            field = 'risk'
        elif re.search(r'\b(?:please|review|inspect|check|implement|run|read|use|need|must|should|next|fix)\b|请|检查|复核|需要|修复', sentence, re.I):
            field = 'next_action'
        elif re.search(r'\b(?:changed|updated|added|removed|replaced|implemented|because|reason|found|observed)\b|已修改|已实现|已新增|原因|发现', sentence, re.I):
            field = 'change'
        elif re.search(r'\b(?:accept|accepted|reject|rejected|conclude|done|complete)\b|接受|拒绝|结论|完成', sentence, re.I):
            field = 'conclusion'
        if field is None or len(sentence) > 2048:
            complete = False
            reasons.append('ambiguous_natural_language' if field is None else 'oversized_atomic_claim')
            field = 'unknown'
        optional = (field == 'change' or bool(_OPTIONAL_LABEL.match(sentence))) and not _PROTECTED.search(sentence)
        facts.append({'fact_id': f'f{len(facts)+1:03d}', 'field': field,
            'start_character': left, 'end_character': right,
            'critical': not optional or field in {'test_status', 'unknown'},
            'provenance': 'sender_claim'})
    return facts, complete, '|'.join(sorted(set(reasons))) or 'complete_exact_claim_spans'


def source_from_event(event, *, episode_id, task_id):
    if event.get('kind') not in {'work_message', 'handoff', 'delegate', 'task_returned'}:
        raise SourceRejected('Only actually published addressed communications are eligible')
    field = next((name for name in ('body', 'message', 'reason') if isinstance(event.get(name), str)), None)
    if field is None or not event.get('recipient') or not event.get('actor_id'):
        raise SourceRejected('Published source lacks exact text or addressed participants')
    facts, complete, _ = source_facts(event[field])
    event_id = f"{episode_id}:world-message:{event['sequence']}"
    metadata = {'published_event_id': event_id}
    if event.get('source_reference'):
        metadata['artifact_version'] = copy.deepcopy(event['source_reference'])
    if event.get('fixed_reference'):
        metadata['artifact_refs'] = [copy.deepcopy(event['fixed_reference'])]
    if event.get('patch_id'):
        metadata.setdefault('artifact_refs', []).append({'patch_id': event['patch_id']})
    return {'source_id': event_id+':'+field, 'sender': event['actor_id'],
        'recipients': [event['recipient']], 'task_id': event.get('task_id') or task_id,
        'raw_text': event[field], 'facts': facts, 'facts_complete': complete,
        'metadata': metadata, 'evidence': []}, field


def compressor_annotations(payload, identity, source):
    """Exact input-source tree for the real auxiliary request, not a new bill."""
    condition = identity['condition']
    template = SourceFragment('Base/Template', 'compressor-template:'+PROMPT_SHA256[condition],
        'compressor-prompt:'+PROMPT_VERSIONS[condition], 'compression-service', 'template')
    event = source['metadata']['published_event_id']
    refsource = SourceFragment('Artifact', source['source_id']+':content-index', event,
        source['sender'], 'index', artifact_sha256=identity['version_hash'])
    def classify(path, value, root):
        if len(path) == 3 and path[0] == 'facts' and type(path[1]) is int and path[2] == 'text':
            fact = source['facts'][path[1]]
            return SourceFragment('Peer-message', source['source_id']+':fact:'+fact['fact_id'],
                event, source['sender'], 'excerpt', artifact_sha256=identity['version_hash'],
                parent_source_ids=(source['source_id'],))
        if path in {('source_id',), ('version_hash',)}:
            return refsource
        return template
    annotated = annotate_tree(payload, template)
    annotated['messages'][1]['content'] = annotate_json_text(payload['messages'][1]['content'], template, classify)
    return {'payload': annotated, 'template_source': template}


class RealCommunicationRenderer(CommunicationRenderer):
    """Uses the host owner's existing single cash/team authority exactly once."""
    def __init__(self, condition, store, owner, *, authorize, token_counter):
        # The parent constructor stays CPU-only; no real transport is disguised.
        super().__init__(condition, store, None, authorize=authorize, token_counter=token_counter)
        self.owner = owner

    def render(self, ref, recipient, recipient_role, request_id):
        source = self._source(ref, recipient, 'default')
        index = self._index(source, ref, recipient)
        if self.condition == 'C0':
            return self._raw(source, index, None, [])
        if not source['facts_complete']:
            return self._raw(source, index, 'source_semantics_not_structured_and_complete', [])
        if self.token_counter is None or not callable(getattr(self.owner, 'compress', None)):
            raise AccountingConflict('Real communication compressor/counter is not bound')
        order = FIELDS if self.condition == 'C1' else ROLE_FIELDS[recipient_role]
        data = {**ref, 'recipient_role': 'generic' if self.condition == 'C1' else recipient_role,
            'field_priority': list(order), 'facts': [{**f, 'text': fact_text(source, f)} for f in source['facts']]}
        payload = {**COMPRESSOR_SETTINGS, 'stream': False, 'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPTS[self.condition]},
            {'role': 'user', 'content': canonical(data).decode()}]}
        identity = {**ref, 'recipient': recipient, 'member_id': recipient,
            'condition': self.condition, 'episode_id': self.owner.window_id,
            'request_id': request_id, 'prompt_version': PROMPT_VERSIONS[self.condition],
            'prompt_sha256': PROMPT_SHA256[self.condition],
            'payload_sha256': hashlib.sha256(canonical(payload)).hexdigest()}
        identity['source_annotations'] = compressor_annotations(payload, identity, source)
        try:
            body = self.owner.compress(payload, identity)
        except PreDispatchBudgetStopped:
            return self._raw(source, index, 'compression_budget_unavailable', [])
        except APIUncertainFailure as error:
            # The host owns finite physical retries and retains every unknown
            # reservation. A failed auxiliary service must not discard the team.
            authority = self.owner.shared_provider_budget()
            attempts = [{'request_id': request_id, 'status': 'transport_unknown',
                'error_type': type(error).__name__, 'usage_known': False,
                'accounting_is_authoritative_team_snapshot': True,
                'authoritative_team_budget': authority}]
            return self._raw(source, index, 'compressor_transport_failed_accounting_retained', attempts)
        # Source, access and accounting-integrity failures are not disguised as
        # a successful raw fallback. They propagate to the owning episode.
        if not isinstance(body, dict) or not isinstance(body.get('usage'), dict):
            raise AccountingConflict('Compressor returned no authoritative usage')
        attempts = [{'request_id': request_id, 'status': 'settled', 'usage': copy.deepcopy(body['usage']),
            'response_model': body.get('model', 'unavailable'),
            'system_fingerprint': body.get('system_fingerprint', 'unavailable')}]
        try:
            choice = body['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise SourceRejected('compressor_output_not_complete')
            selection = json.loads(choice['message']['content'])
            facts = self._validate_selection(selection, source, ref)
            segments = []
            for name in order:
                for fid in selection['fields'][name]:
                    if segments:
                        segments.append({'text': '\n', 'fact_id': None})
                    segments.append({'text': f"{name} [{fid}; {facts[fid]['provenance']}]: ", 'fact_id': None})
                    segments.append({'text': fact_text(source, facts[fid]), 'fact_id': fid})
            summary = ''.join(item['text'] for item in segments)
            count = self.token_counter(summary)
            if type(count) is not int or count < 0 or count > 512:
                raise SourceRejected('rendered_summary_exceeds_512_local_estimated_tokens')
        except (SourceRejected, KeyError, IndexError, TypeError, ValueError) as error:
            return self._raw(source, index, str(error), attempts)
        return {'version': VERSION, 'condition': self.condition, 'L0': index,
            'representation': 'structured_summary' if self.condition == 'C1' else 'L0_L1',
            'L1': summary, 'L1_tokens_estimated': count, 'selection': selection,
            'L1_source_segments': segments,
            'fallback_reason': None, 'compressor_attempts': attempts}


class CommunicationBridge:
    def __init__(self, world, owner, directory, condition, token_counter):
        if condition not in {'C0', 'C1', 'C2'} or owner.spec['id'] != 'REVIEW2':
            raise ValueError('The pilot changes only communication within frozen REVIEW2')
        self.world, self.owner, self.condition = world, owner, condition
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = ImmutableCommunicationStore(self.directory/'sources')
        self.records, self.rendered, self.events = {}, {}, []
        self.original_read = world._action_read_work_event
        self.renderer = RealCommunicationRenderer(condition, self.store, owner,
            authorize=self.authorize, token_counter=token_counter)

    def emit(self, kind, **data):
        row = {'version': VERSION, 'ordinal': len(self.events)+1, 'kind': kind, **data}
        with (self.directory/'events.jsonl').open('ab') as stream:
            stream.write(canonical(row)+b'\n')
        self.events.append(row)

    def publish(self, event):
        sequence = event['sequence']
        if sequence in self.records:
            old = self.records[sequence]
            source, _ = source_from_event(event, episode_id=self.owner.window_id,
                                          task_id=self.world._software()['case']['case_id'])
            if self.store.get(old['ref']) != source:
                raise SourceRejected('An already published communication changed')
            return old
        source, field = source_from_event(event, episode_id=self.owner.window_id,
                                          task_id=self.world._software()['case']['case_id'])
        ref = self.store.publish(source)
        record = {'ref': ref, 'field': field, 'sequence': sequence,
            'sender': source['sender'], 'recipient': event['recipient'], 'kind': event['kind']}
        self.records[sequence] = record
        self.emit('published', **{k:v for k,v in record.items() if k != 'kind'}, event_kind=record['kind'], facts_complete=source['facts_complete'],
                  fact_rule=FACT_RULE_VERSION, fact_count=len(source['facts']),
                  semantic_truth_validated=False, private_evidence_imported=False)
        return record

    def sync(self):
        with self.world.store.lock():
            self.world.state = self.world.store.load()
            for event in self.world.state['software_events']:
                if event.get('kind') in {'work_message', 'handoff', 'delegate', 'task_returned'}:
                    self.publish(event)

    def authorize(self, ref, recipient, level):
        record = next((r for r in self.records.values() if r['ref'] == ref), None)
        if record is None or record['recipient'] != recipient:
            return False
        # Existing World ACL is authoritative; never consult sender-private files.
        with self.world.store.lock():
            self.world.state = self.world.store.load()
            from .software_role_baseline_world_v141 import PROJECT
            event = self.original_read(recipient, PROJECT, record['sequence'])
        return event.get('recipient') == recipient and event.get('actor_id') == record['sender']

    def project(self, observation, member):
        self.sync()
        value = copy.deepcopy(observation)
        for group in ('messages', 'handoffs'):
            if len(value.get(group, [])) > PREVIEW_COUNT:
                raise SourceRejected('The frozen baseline preview count changed')
            for item in value.get(group, []):
                record = self.records.get(item['sequence'])
                if record is None:
                    raise SourceRejected('A visible addressed message lacks immutable publication')
                key = (item['sequence'], member)
                if key not in self.rendered:
                    role = 'reviewer' if member == 'member_002' else 'developer'
                    self.rendered[key] = self.renderer.render(record['ref'], member, role,
                        f"{self.owner.window_id}:{member}:communication:{item['sequence']}")
                    self.emit('representation_prepared', sequence=item['sequence'], recipient=member,
                        **copy.deepcopy(self.rendered[key]), not_yet_provider_presented=True)
                rendered = self.rendered[key]
                source = self.store.get(record['ref'])
                original_preview = source['raw_text'][:PREVIEW_CHARACTERS]
                if item.get(record['field']) != original_preview:
                    raise SourceRejected('The existing C0 text preview changed before treatment')
                index = {**record['ref'], 'event_sequence': item['sequence'],
                    'kind': record['kind'], 'sender': record['sender'],
                    'representation': rendered['representation'],
                    'L2': {'tool': 'read_work_event', 'sequence': item['sequence'], 'level': 'L2',
                           'version_hash': record['ref']['version_hash']},
                    'L3': {'tool': 'read_work_event', 'sequence': item['sequence'], 'level': 'L3',
                           'version_hash': record['ref']['version_hash']}}
                item['communication'] = index
                if rendered['representation'] != 'raw':
                    item[record['field']] = rendered['L1']
                    item[record['field']+'_truncated'] = False
                else:
                    # Raw fallback uses the existing bounded display in every
                    # condition; full originals remain available on demand.
                    item[record['field']] = original_preview
                    item[record['field']+'_truncated'] = len(source['raw_text']) > PREVIEW_CHARACTERS
                    if rendered.get('fallback_reason'):
                        index['fallback_reason'] = rendered['fallback_reason']
        return value

    def read(self, actor, project_id, sequence, level=None, version_hash=None,
             start_character=None, max_characters=None):
        event = self.original_read(actor, project_id, sequence)
        if level is None:
            if any(v is not None for v in (version_hash, start_character, max_characters)):
                raise ValueError('Communication page parameters require an explicit level')
            return event
        if event.get('kind') not in {'work_message', 'handoff', 'delegate', 'task_returned'}:
            raise ValueError('Communication layers apply only to your addressed published messages')
        record = self.publish(event)
        if version_hash != record['ref']['version_hash'] or actor not in {record['recipient'], record['sender']}:
            raise ValueError('The requested exact publication version is unavailable to this recipient')
        if level not in {'L2', 'L3'}:
            raise ValueError('Choose L2 or L3')
        start = 0 if start_character is None else start_character
        size = 8192 if max_characters is None else max_characters
        if type(start) is not int or start < 0 or type(size) is not int or not 1 <= size <= 8192:
            raise ValueError('Invalid communication page')
        source = self.store.get(record['ref'])
        # L2 contains exact protected published claims. They are not renamed as
        # independently executed test evidence. L3 is the original text only.
        text = (source['raw_text'] if level == 'L3' or not source['facts_complete'] else
            '\n'.join(fact_text(source, f) for f in source['facts']
                      if f['critical'] or f['field'] in {'test_status', 'unknown'}))
        page = text[start:start+size]
        result = {'kind': 'communication_pull', **record['ref'], 'sequence': sequence,
            'actor_id': source['sender'], 'recipient': actor, 'level': level, 'text': page,
            'start_character': start, 'next_character': start+len(page) if start+len(page) < len(text) else None,
            'total_characters': len(text), 'facts_are': 'published_sender_claims_not_independent_test_evidence',
            'L2_unstructured_raw_fallback': level == 'L2' and not source['facts_complete']}
        self.emit('retrieved', recipient=actor, sequence=sequence, level=level,
                  source_ref=record['ref'], returned_characters=len(page), charged_on_next_model_input=True)
        return result


def extend_tools(definitions):
    result = copy.deepcopy(definitions)
    for tool in result:
        if tool['name'] == 'read_work_event':
            tool['description'] += (' Communication events optionally accept level=L2 (exact protected '
                'published claims) or L3 (original text), with the communication index version_hash. '
                'Claims are not verified test evidence. Both levels retain the same original event ACL; '
                'omitting level returns the unchanged event. Pagination defaults to 0/8192 characters.')
            tool['parameters']['properties'].update({
                'level': {'type': ['string', 'null'], 'enum': ['L2', 'L3', None]},
                'version_hash': {'type': ['string', 'null']},
                'start_character': {'type': ['integer', 'null'], 'minimum': 0},
                'max_characters': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 8192}})
    return result


def bind_world(world, bridge):
    if hasattr(world, 'communication_v157'):
        raise ValueError('Communication world binding must be installed once')
    original_tools = world._tool_definitions
    def definitions(self, project_id):
        return extend_tools(original_tools(project_id))
    def read(self, actor, project_id, sequence, level=None, version_hash=None,
             start_character=None, max_characters=None):
        return bridge.read(actor, project_id, sequence, level, version_hash, start_character, max_characters)
    world._tool_definitions = MethodType(definitions, world)
    world._action_read_work_event = MethodType(read, world)
    world.communication_v157 = bridge
