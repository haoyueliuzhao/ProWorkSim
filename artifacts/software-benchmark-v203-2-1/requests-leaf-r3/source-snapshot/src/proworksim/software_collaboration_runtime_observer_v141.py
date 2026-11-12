"""Bounded evaluation-side hooks for actual v141 SDK requests and world receipts.

No observer event is added to an agent conversation. A failed measurement is
quarantined in this team sidecar, never retried as a tool or a model action.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MethodType

from .software_collaboration_observation_v141 import ObservationLog
from .storage import atomic_write, json_bytes


def sha(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


class RuntimeObservationBridge:
    def __init__(self, folder, *, team_id, members, token_counter=None, tokenizer_id=None,
                 require_content_counter=False):
        if require_content_counter and (token_counter is None or not tokenizer_id):
            raise ValueError('Formal content measurement requires a frozen local tokenizer')
        self.folder = Path(folder)
        self.log = ObservationLog(self.folder, team_id=team_id, members=members,
                                  token_counter=token_counter, tokenizer_id=tokenizer_id)
        self.errors, self.partial = [], set()
        self.tool_requests, self.reads, self.messages, self.received = {}, {}, {}, {}
        self.publications, self.opportunities, self.acquisitions = {}, {}, {}
        self.validations, self.integrations, self.transitions = {}, {}, []
        self.serial, self.closed = 0, False

    def eid(self, prefix):
        self.serial += 1
        return f'{prefix}:{self.serial}'

    def safely(self, scope, fn, *args):
        try:
            return fn(*args)
        except Exception as error:
            # Deliberately omit payloads/private text from the error summary.
            row = {'scope': scope, 'type': type(error).__name__, 'message': str(error)[:1000]}
            if len(self.errors) < 64:
                self.errors.append(row)
            self.partial.add(scope)
            try:
                atomic_write(self.folder/'measurement-errors.json', json_bytes(self.errors))
            except Exception:
                # Disk pressure must not turn a successfully returned provider
                # response into a transport failure or create a model retry.
                self.partial.add('observer_error_log_unwritable')
            return None

    def provider_uncertain(self, member, payload):
        request = payload['request_id']
        self.log.record_usage('uncertain:'+request, member, request, payload.get('usage_id', 'agent'),
            'uncertain', None, receipt={'request_id': request, 'return_status': 'uncertain'})

    def provider_returned(self, member, payload, result):
        request, wire = payload['request_id'], payload['wire']
        evidence = {'request_id': request, 'wire_sha256': sha(wire), 'response_sha256': sha(result)}
        usage = result.get('usage')
        self.log.record_usage('usage:'+request, member, request, payload.get('usage_id', 'agent'),
            'settled' if isinstance(usage, dict) else 'uncertain', usage,
            receipt=evidence)
        for choice in result.get('choices', []):
            for call in choice.get('message', {}).get('tool_calls', []):
                self.tool_requests[(member, call['id'])] = request
        exposed = []
        for message in wire.get('messages', []):
            text = message.get('content')
            if not isinstance(text, str):
                continue
            try:
                body = json.loads(text)
            except (ValueError, TypeError):
                # A summary has no exact source-span mapping. Original reads
                # remain known returns, while actual summarized exposure is unknown.
                if message.get('role') == 'user' and payload.get('usage_id') == 'condenser':
                    self.partial.add('presentations')
                continue
            key = (member, message.get('tool_call_id'))
            if message.get('role') == 'tool' and key in self.reads:
                event, content_digest = self.reads[key]
                if sha(body) == content_digest:
                    exposed.append(event)
                else:
                    self.partial.add('presentations')
            observation = body.get('observation') if isinstance(body, dict) else None
            if isinstance(observation, dict):
                for item in observation.get('messages', []):
                    if not isinstance(item, dict):
                        continue
                    sequence = item.get('sequence', item.get('message_sequence'))
                    sent = self.messages.get(sequence)
                    if sent and sent['recipient'] == member and item.get('body') == sent['body']:
                        receive_key = (member, sequence)
                        if receive_key not in self.received:
                            event = self.eid('received')
                            self.log.record_message_received(event, member, sent['event'],
                                actually_obtained=True, evidence=evidence)
                            self.received[receive_key] = event
                        exposed.append(self.received[receive_key])
        self.log.record_information_presented('input:'+request, member, request,
            list(dict.fromkeys(exposed)), actual_input=evidence, evidence=evidence)

    def bind(self, runtime):
        self.runtime = runtime
        actual = runtime.prepared.world
        actual.collaboration_observer_v141 = self
        for member in self.log.members:
            self.log.record(self.eid('initial-role'), 'role_state', member, state_id='initial:'+member,
                state={'source': 'frozen_predeclared_role_contract', 'organization_id': runtime.fixed_spec['id'],
                       'member': member, 'dynamic_membership': False},
                evidence={'fixed_organization_sha256': sha(runtime.fixed_spec)})
        original = runtime.execute
        bridge = self

        def execute(this, member, name, arguments, association):
            # A small exact version reference; do not duplicate repository trees.
            before = actual.org_current_identity(member)['source_reference']
            response = original(member, name, arguments, association)
            bridge.safely('actions', bridge.executed, member, name, arguments, association, response, before)
            return response
        runtime.execute = MethodType(execute, runtime)

    def _opportunity(self, publication, recipient, evidence):
        key = (publication, recipient)
        if key not in self.opportunities:
            event = self.eid('opportunity')
            self.log.record(event, 'artifact_opportunity', recipient, publication=publication,
                            eligible=True, evidence=evidence)
            self.opportunities[key] = event
        return self.opportunities[key]

    def executed(self, member, name, arguments, association, response, before):
        tool_id = association.get('model_tool_call_id')
        request = self.tool_requests.get((member, tool_id))
        evidence = {'model_tool_call_id': tool_id, 'model_call_id': association.get('model_call_id'),
                    'response_sha256': sha(response)}
        self.log.record_action(self.eid('action'), member, name, request,
            response.get('ok') if isinstance(response, dict) else None, evidence=evidence)
        if request is None:
            self.partial.add('actions')
        if not isinstance(response, dict) or response.get('ok') is not True:
            return
        result = response.get('result', {})
        if not isinstance(result, dict):
            return
        current = self.runtime.prepared.world.org_current_identity(member)['source_reference']
        if current != before:
            event = self.eid('transition')
            self.log.record(event, 'version_transition', member,
                from_reference=before, to_reference=current, evidence=evidence)
            self.transitions.append((event, member, before, current))
        if name == 'read_file':
            expected = {'source_reference', 'path', 'text_sha256', 'start_character', 'end_character', 'total_characters', 'text'}
            if expected <= result.keys():
                event = self.eid('read')
                self.log.record_information_read(event, member, source_reference=result['source_reference'],
                    path=result['path'], full_text_sha256=result['text_sha256'],
                    start=result['start_character'], end=result['end_character'], total=result['total_characters'],
                    text=result['text'], authorized=True, evidence=evidence)
                self.reads[(member, tool_id)] = (event, sha(response))
            else:
                self.partial.add('reads')
        elif name == 'send_message':
            event = self.eid('sent')
            self.log.record_message_sent(event, member, [arguments['recipient']], arguments['body'], evidence=evidence)
            self.messages[result['message_sequence']] = {'event': event, 'recipient': arguments['recipient'],
                                                        'body': arguments['body']}
        elif name == 'org_declare_role':
            self.log.record(self.eid('role'), 'role_state', member, state_id=str(result.get('event_sequence', self.serial)),
                state={'source': 'explicit_member_declaration', **arguments}, evidence=evidence)
        elif name in {'create_task', 'claim_task', 'release_task', 'revise_task', 'offer_transfer',
                      'accept_transfer', 'decline_transfer', 'declare_dependency', 'remove_dependency'}:
            self.log.record(self.eid('task'), 'task_state', member,
                state_id=str(arguments.get('task_id', name)), state={'operation': name, 'arguments': arguments,
                    'result_sha256': sha(result)}, evidence=evidence)
        elif name == 'fix_patch':
            patch_id = result['patch_id']
            event = self.eid('publication')
            self.log.record(event, 'artifact_published', member, patch_id=patch_id,
                source_reference=result['source_reference'], content_identity={
                    'files_sha256': result.get('files_sha256'),
                    'entry_metadata_sha256': result.get('entry_metadata_sha256')}, evidence=evidence)
            self.publications[patch_id] = (event, member)
            # The world ACL, rather than a broadcast assumption, establishes a
            # legal chance to adopt a published partner source.
            source = result['source_reference']
            for share in self.runtime.prepared.world.state.get('shares', []):
                if share.get('object_id') == source['object_id'] and share.get('version_id') == source['version_id']:
                    for recipient in share.get('actor_ids', []):
                        if recipient in self.log.members and recipient != member:
                            self._opportunity(event, recipient, {**evidence, 'world_share_sha256': sha(share)})
        elif name == 'handoff_patch':
            publication, author = self.publications[arguments['patch_id']]
            recipient = arguments['to_member']
            if recipient != author:
                self._opportunity(publication, recipient, evidence)
        elif name == 'integrate_patch':
            patch_id = arguments['patch_id']
            publication, author = self.publications[patch_id]
            if author != member and result.get('status') != 'conflicted' and not result.get('conflicts'):
                # Successful managed integrate itself proves legal source access.
                opportunity = self._opportunity(publication, member, evidence)
                event = self.eid('acquired')
                self.log.record(event, 'artifact_acquired', member,
                    opportunity=opportunity, adopted_reference=current, evidence=evidence)
                self.acquisitions[(member, patch_id)] = (event, current)
                if member == self.log.members[0]:
                    event = self.eid('integrated')
                    self.log.record(event, 'artifact_integrated', member, publication=publication,
                        result_reference=current, explicit_agent_action=True, evidence=evidence)
                    self.integrations[patch_id] = (event, current, len(self.transitions))
        elif name == 'run_tests':
            executed = result.get('execution', {}).get('executed')
            if executed is None:
                executed = result.get('executed')
            if type(executed) is not bool:
                self.partial.add('artifacts')
                return
            for (actor, patch_id), (acquisition, adopted) in self.acquisitions.items():
                if actor == member and adopted == result.get('source_reference'):
                    event = self.eid('validated')
                    self.log.record(event, 'artifact_validated', member, acquisition=acquisition,
                        tested_reference=adopted, executed=executed, passed=result.get('passed'), evidence=evidence)
                    self.validations[(member, patch_id)] = (event, result.get('passed') is True)
        elif name == 'org_review_patch':
            item = self.validations.get((member, arguments['patch_id']))
            if item:
                self.log.record(self.eid('review'), 'artifact_review', member, validation=item[0],
                                decision=arguments['decision'], evidence=evidence)
            else:
                self.partial.add('artifacts')
        elif name == 'read_work_event':
            sent = self.messages.get(result.get('sequence'))
            if (result.get('kind') == 'work_message' and sent and sent['recipient'] == member
                    and sent['body'] == result.get('body')):
                # A successful explicit, ACL-checked reread is a fresh return.
                # The model only receives it on a later exact tool-result input.
                event = self.eid('message-reread')
                self.log.record_message_received(event, member, sent['event'],
                    actually_obtained=True, evidence=evidence)
                self.reads[(member, tool_id)] = (event, sha(response))
            else:
                self.partial.add('presentations')

    def finalize(self, terminal_reference, delivery_reference, lock_receipt):
        if self.closed:
            raise ValueError('Only one candidate closure can finalize observation')
        actor = self.log.members[0]
        lock = self.eid('candidate')
        self.log.record(lock, 'candidate_locked', actor, reference=terminal_reference,
                        generation_closed=True, evidence=lock_receipt)
        chain = []
        if delivery_reference:
            included = set(self.runtime.prepared.world._software()['deliveries'][-1]['included_patch_ids'])
            for patch, (integration, adopted, start) in self.integrations.items():
                validated = self.validations.get((actor, patch))
                if patch not in included or not validated or not validated[1]:
                    continue
                transitions, current = [], adopted
                for event, who, before, after in self.transitions[start:]:
                    if who == actor and before == current:
                        transitions.append(event)
                        current = after
                        if current == delivery_reference:
                            break
                if current == delivery_reference:
                    chain.append({'integration': integration, 'validation': validated[0], 'transitions': transitions})
                else:
                    self.partial.add('artifacts')
            self.log.record(self.eid('delivery'), 'final_delivery', actor, candidate_lock=lock,
                legal=True, submitted_reference=delivery_reference, artifact_chain=chain, evidence=lock_receipt)
        # Exact summary and transformed history provenance are only claimed
        # when every dispatched input has an exact observed source association.
        for channel in ('roles', 'tasks', 'messages', 'reads', 'presentations', 'artifacts', 'usage', 'actions'):
            complete = channel not in self.partial and not self.errors
            self.log.record_coverage(self.eid('coverage'), channel, complete, evidence=lock_receipt)
        summary = self.log.summary()
        summary.update(runtime_measurement_errors=self.errors, runtime_partial_channels=sorted(self.partial),
                       content_counter_available=self.log.tokenizer_id is not None)
        atomic_write(self.folder/'summary.json', json_bytes(summary))
        self.closed = True
        self.log.close()
        return summary
