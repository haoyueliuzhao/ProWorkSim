"""Non-authoritative lifecycle hooks with explicit normal/partial finalization."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import MethodType

from . import software_collaboration_runtime_observer_v141 as old
from .software_collaboration_observation_v156 import CHANNELS, ObservationLog
from .storage import atomic_write, json_bytes

sha = old.sha


class RuntimeObservationBridge(old.RuntimeObservationBridge):
    def __init__(self, folder, *, team_id, members, token_counter=None, tokenizer_id=None,
                 require_content_counter=False, explicit_source_presentations=False):
        if require_content_counter and (token_counter is None or not tokenizer_id):
            raise ValueError('Formal content measurement requires a frozen local tokenizer')
        self.folder = Path(folder)
        summary = self.folder / 'summary.json'
        if summary.exists() and json.loads(summary.read_text()).get('completion_status') == 'normal':
            raise ValueError('A finalized normal observation cannot be reopened as a new run')
        self.reopened = (self.folder / 'events.jsonl').exists()
        self.log = ObservationLog(self.folder, team_id=team_id, members=members,
                                  token_counter=token_counter, tokenizer_id=tokenizer_id)
        self.errors, self.partial = [], set(CHANNELS) if self.reopened else set()
        self.missing_intervals = (['reopened_without_continuous_runtime_state'] if self.reopened else [])
        self.tool_requests, self.reads, self.messages, self.received = {}, {}, {}, {}
        self.publications, self.opportunities, self.acquisitions = {}, {}, {}
        self.validations, self.integrations, self.transitions = {}, {}, []
        self.information_objects, self.message_objects = {}, {}
        self.serial, self.closed = len(self.log._rows), False
        self.explicit_source_presentations = explicit_source_presentations
        self.source_presentations = {}
        self.returned_requests = set()
        self.test_report_sources = {}

    def bind(self, runtime):
        self.runtime = runtime
        actual = runtime.prepared.world
        actual.collaboration_observer_v156 = self
        # Existing exporter hook is only a callback slot, not an old observer instance.
        actual.collaboration_observer_v141 = self
        for member in self.log.members:
            self.safely('roles', lambda member=member: self.log.record(
                self.eid('initial-role'), 'role_state', member, state_id='initial:'+member,
                state={'organization_id': runtime.fixed_spec['id'], 'dynamic_membership': False},
                evidence={'fixed_organization_sha256': sha(runtime.fixed_spec)}))
        original, bridge = runtime.execute, self

        def execute(this, member, name, arguments, association):
            before = bridge.safely('artifacts', lambda: actual.org_current_identity(member)['source_reference'])
            response = original(member, name, arguments, association)
            bridge.safely('actions', bridge.executed, member, name, arguments, association, response, before)
            return response
        runtime.execute = MethodType(execute, runtime)

    def _stage(self, actor, stage, obj, *, prior=None, evidence, **facts):
        event = self.eid(stage)
        self.log.record_lifecycle(event, actor, stage=stage, prior_event=prior,
                                  evidence=evidence, **obj, **facts)
        return event

    def _object(self, origin, identity, content, *, source=None, audience=None):
        return {'object_id': identity, 'origin_member': origin,
                'allowed_members': list(audience or [origin]),
                'content_sha256': content, 'source_reference': source}

    def _present_new_rows(self, rows):
        for row in rows:
            data, actor = row['data'], row['actor']
            if row['kind'] == 'message_received':
                sent = data['sent_event']
                if sent in self.message_objects:
                    obj, deliveries = self.message_objects[sent]
                    self.information_objects[row['event_id']] = (obj, deliveries[actor])
            elif row['kind'] == 'information_presented':
                for source in data['information_events']:
                    known = self.information_objects.get(source)
                    if known is None:
                        self.partial.add('lifecycle')
                        continue
                    obj, receipt = known
                    self._stage(actor, 'presented', obj, prior=receipt,
                        request_id=data['request_id'], actual_input=data['actual_input'], evidence=data['evidence'])

    def provider_returned(self, member, payload, result):
        def observe():
            self.returned_requests.add(payload['request_id'])
            if self.explicit_source_presentations:
                request = payload['request_id']
                evidence = {'request_id': request, 'wire_sha256': sha(payload['wire']), 'response_sha256': sha(result)}
                usage = result.get('usage')
                self.log.record_usage('usage:'+request, member, request, payload.get('usage_id', 'agent'),
                    'settled' if isinstance(usage, dict) else 'uncertain', usage, receipt=evidence)
                for choice in result.get('choices', []):
                    for call in choice.get('message', {}).get('tool_calls', []):
                        self.tool_requests[(member, call['id'])] = request
                return
            before = len(self.log._rows)
            super(RuntimeObservationBridge, self).provider_returned(member, payload, result)
            rows = list(self.log._rows.values())[before:]
            self.safely('lifecycle', self._present_new_rows, rows)
        return self.safely('usage', observe)

    def observe_source_presentations(self, member, built, response):
        """Consume verified source offsets; never expand summary ancestry as exposure."""
        from .software_input_provenance_v156 import verify_request, persist_request, digest
        verify_request(built)
        identity, manifest = built.manifest['identity'], built.manifest
        if (identity['member_id'] != member or identity['episode_id'] != self.log.team_id
                or response['request_id'] != identity['request_id']
                or response['request_payload_sha256'] != manifest['payload_sha256']):
            raise ValueError('Explicit input presentation identity or payload changed')
        self.log._member(member)
        request = identity['request_id']
        status = ('presented' if response['outcome'] == 'success' else
                  'not_dispatched' if response['outcome'] == 'cancelled_before_dispatch' else 'unknown')
        if status == 'presented' and request not in self.returned_requests:
            raise ValueError('Successful exposure lacks this runtime\'s actual returned request')
        capture = persist_request(self.folder/'source-presentation-inputs', built)
        rows, categories, presented_reports, report_bindings = [], Counter(), set(), []
        for span in manifest['spans']:
            if not span['semantic_input'] or span['kind'] not in {'text_fragment', 'unannotated_text'}:
                continue
            source = span['source']
            if source is not None:
                if source['category'] == 'Peer-message':
                    self.log._member(source['origin_member_id'])
                    if source['origin_member_id'] == member:
                        raise ValueError('Own content cannot be counted as peer presentation')
                categories[source['category']] += 1
                if source['category'] == 'Tool-feedback' and source['transformation'] != 'summary':
                    for parent in source['parent_source_ids']:
                        test = self.test_report_sources.get(parent)
                        if test is not None and status == 'presented':
                            presented_reports.add(test)
                            report_bindings.append({'test_event': test, 'source_parent': parent,
                                'occurrence_id': span['occurrence_id'], 'payload_start': span['payload_start'],
                                'payload_end': span['payload_end']})
            rows.append({'stage': status, 'actor': member, 'observed_at_utc': response.get('response_time'),
                'request_id': request, 'occurrence_id': span['occurrence_id'], 'source': source,
                'payload_start': span['payload_start'], 'payload_end': span['payload_end'],
                'payload_slice_sha256': span['payload_slice_sha256'],
                'decoded_text_sha256': span['decoded_text_sha256'],
                'json_pointer': span['json_pointer'], 'summary_parents_marked_presented': False})
        unknown = manifest['semantic_payload_bytes']-manifest['semantic_attributed_payload_bytes']
        value = {'version': 'v156-explicit-source-presentation-receipt-r1', 'request_id': request,
            'member_id': member, 'status': status, 'request_capture': capture,
            'response_id': response.get('response_id'), 'source_occurrences': rows,
            'known_source_occurrences_by_category': dict(categories),
            'semantic_unknown_bytes': unknown, 'summary_parents_marked_presented': False,
            'semantic_understanding_or_behavioral_use_claimed': False,
            'test_report_presentation_bindings': report_bindings}
        raw = json_bytes(value)
        if len(raw) > 32*1024**2:
            raise ValueError('Bounded source-presentation receipt exceeded 32 MiB')
        path = self.folder/'source-presentations'/(digest(request.encode())+'.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('An observed input presentation cannot change on callback replay')
        if not path.exists():
            atomic_write(path, raw)
        receipt = {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}
        self.log.record('source-input:'+request, 'source_presentations', member,
            request_id=request, status=status, manifest=receipt,
            known_source_occurrences=sum(categories.values()),
            unique_sources_in_request=len({r['source']['source_id'] for r in rows if r['source'] is not None}),
            semantic_payload_bytes=manifest['semantic_payload_bytes'], semantic_unknown_bytes=unknown,
            presented_test_reports=sorted(presented_reports),
            summary_parents_marked_presented=False, evidence={'payload_sha256': manifest['payload_sha256']})
        self.source_presentations[request] = {'status': status, 'unknown_bytes': unknown,
                                             'manifest': receipt, 'category_occurrences': dict(categories)}
        return receipt

    def source_presentation_coverage_proof(self):
        seen = {r for r, v in self.source_presentations.items() if v['status'] == 'presented'}
        complete = (not self.reopened and seen == self.returned_requests and all(
            v['unknown_bytes'] == 0 and v['status'] != 'unknown' for v in self.source_presentations.values()))
        return {'complete': complete, 'evidence': {'actual_returned_requests': len(self.returned_requests),
            'known_source_presented_requests': len(seen), 'exact_request_set_equal': seen == self.returned_requests,
            'all_source_manifests_sha256': sha(self.source_presentations),
            'semantic_byte_sources_complete': complete, 'provider_exact_token_coverage_claimed': False}}

    def provider_uncertain(self, member, payload):
        self.partial.update({'usage', 'presentations', 'lifecycle'})
        return self.safely('usage', super().provider_uncertain, member, payload)

    def executed(self, member, name, arguments, association, response, before):
        first = len(self.log._rows)
        # The old hook's acceptance test is replaced, while common world receipts
        # and source-range checks are retained unchanged.
        if name == 'org_review_patch':
            request = self.tool_requests.get((member, association.get('model_tool_call_id')))
            evidence = {'model_tool_call_id': association.get('model_tool_call_id'),
                        'model_call_id': association.get('model_call_id'), 'response_sha256': sha(response)}
            self.log.record_action(self.eid('action'), member, name, request,
                response.get('ok') if isinstance(response, dict) else None, evidence=evidence)
            if request is None:
                self.partial.add('actions')
            if not isinstance(response, dict) or response.get('ok') is not True:
                return
            item = self.validations.get((member, arguments['patch_id']))
            if item:
                current = self.runtime.prepared.world.org_current_identity(member)['source_reference']
                self.log.record_review(self.eid('review'), member, item[0], arguments['decision'],
                                       current_reference=current, evidence=evidence)
            elif arguments['decision'] == 'request_changes':
                current = self.runtime.prepared.world.org_current_identity(member)['source_reference']
                publication = self.publications[arguments['patch_id']][0]
                self.log.record_review(self.eid('review'), member, None, 'request_changes',
                    current_reference=current, publication=publication, evidence=evidence)
            else:
                self.partial.add('artifacts')
        else:
            super().executed(member, name, arguments, association, response, before)
        rows = list(self.log._rows.values())[first:]
        self.safely('lifecycle', self._action_lifecycle, member, name, response, rows)
        if name == 'run_tests' and isinstance(response, dict) and response.get('ok') is True:
            test_event = self.safely('public_tests', self.observe_public_test, member, response['result'])
            if test_event:
                self.reads[(member, association.get('model_tool_call_id'))] = (test_event, sha(response))
                tool_call = association.get('model_tool_call_id')
                if tool_call:
                    marker = f'sdk-tool-call:{self.log.team_id}:{member}:{tool_call}'
                    self.test_report_sources[marker] = test_event

    def _action_lifecycle(self, member, name, response, rows):
        for row in rows:
            data, event = row['data'], row['event_id']
            evidence = data['evidence']
            if row['kind'] == 'message_sent':
                obj = self._object(member, 'message:'+event, data['content']['sha256'],
                                   audience=[member, *data['recipients']])
                made = self._stage(member, 'produced', obj, evidence=evidence)
                published = self._stage(member, 'published', obj, prior=made, evidence=evidence)
                deliveries = {recipient: self._stage(recipient, 'delivered', obj,
                    prior=published, evidence=evidence) for recipient in data['recipients']}
                self.message_objects[event] = (obj, deliveries)
            elif row['kind'] == 'information_read':
                obj = self._object(member, 'read:'+event, data['content']['sha256'], source=data['source_reference'])
                obtained = self._stage(member, 'retrieved', obj, authorized=True,
                    tool_receipt=evidence, evidence=evidence, origin_role='retrieval_requester_not_file_author')
                self.information_objects[event] = (obj, obtained)
            elif row['kind'] == 'message_received' and name == 'read_work_event':
                known = self.message_objects.get(data['sent_event'])
                if known:
                    obj, deliveries = known
                    obtained = self._stage(member, 'retrieved', obj, prior=deliveries[member],
                        authorized=True, tool_receipt=evidence, evidence=evidence)
                    self.information_objects[event] = (obj, obtained)
            elif row['kind'] == 'version_transition':
                result = response.get('result', {})
                content = result.get('files_sha256')
                if isinstance(content, str) and len(content) == 64:
                    obj = self._object(member, 'source:'+sha(data['to_reference']), content,
                                       source=data['to_reference'])
                    self._stage(member, 'produced', obj, evidence=evidence)
            elif row['kind'] == 'artifact_published':
                audience = [member]
                for share in self.runtime.prepared.world.state.get('shares', []):
                    source = data['source_reference']
                    if share.get('object_id') == source['object_id'] and share.get('version_id') == source['version_id']:
                        audience.extend(a for a in share.get('actor_ids', []) if a in self.log.members)
                obj = self._object(member, 'artifact:'+data['patch_id'], sha(data['content_identity']),
                    source=data['source_reference'], audience=list(dict.fromkeys(audience)))
                pub = self._stage(member, 'published', obj, evidence=evidence)
                self.information_objects[event] = (obj, pub)
            elif row['kind'] == 'artifact_acquired':
                opportunity = self.log._rows[data['opportunity']]
                publication = opportunity['data']['publication']
                obj, published = self.information_objects[publication]
                retrieved = self._stage(member, 'retrieved', obj, prior=published,
                    authorized=True, tool_receipt=evidence, evidence=evidence)
                action = next(r for r in rows if r['kind'] == 'action')
                self._stage(member, 'behaviorally_used', obj, prior=retrieved,
                    action_event=action['event_id'], source_action_binding={'publication': publication,
                        'acquisition': event, 'actual_tool': name, 'result_reference': data['adopted_reference']},
                    evidence=evidence)

    def observe_public_test(self, member, result):
        """Retain v141 parser output; nested session counts never inflate root counts."""
        execution = result.get('execution', {})
        executed = execution.get('executed', result.get('executed'))
        if type(executed) is not bool:
            raise ValueError('Public-test execution status is missing')
        report = result.get('test_evidence', execution.get('test_evidence'))
        if not isinstance(report, dict):
            raise ValueError('Session-bound public-test evidence is missing')
        raw = json_bytes(report)
        if len(raw) > 4*1024**2:
            raise ValueError('Public-test observation report exceeds the established evidence bound')
        digest = sha(report)
        path = self.folder / 'public-test-reports' / (digest+'.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            atomic_write(path, raw)
        elif path.read_bytes() != raw:
            raise ValueError('A public report identity cannot change its contents')
        sessions = [{k: s.get(k) for k in ('run_id', 'parent_run_id', 'root', 'exitstatus', 'counts')}
                    for s in report.get('sessions', [])]
        source = result.get('source_reference', execution.get('source_reference'))
        # The same framework report arriving twice is not another test run.
        event = 'public-test:'+sha({'member': member, 'report': digest, 'execution': execution, 'source': source})
        evidence = {'report_sha256': digest, 'execution_sha256': sha(execution)}
        recorded = self.log.record(event, 'public_test', member, source_reference=source,
            executed=executed, passed=result.get('passed'),
            command={'argv': execution.get('argv'), 'returncode': execution.get('returncode'),
                     'timed_out': execution.get('timed_out'), 'executed': executed},
            report={'path': str(path), 'sha256': digest, 'bytes': len(raw), 'saved': True},
            sessions=sessions, validation_status=result.get('validation_status'), evidence=evidence)
        if recorded['duplicate']:
            return event
        report_obj = self._object(member, 'test-report:'+digest, digest, source=source)
        made = self._stage(member, 'produced', report_obj, evidence=evidence,
                           origin_role='public_test_runner_not_model')
        self.information_objects[event] = (report_obj, made)
        if executed:
            obj = self._object(member, 'tested-source:'+sha(source), execution.get('input_tree_sha256') or sha(source),
                               source=source)
            self._stage(member, 'validated', obj, test_event=event,
                        passed=result.get('passed'), evidence=evidence)
        # Saved reports are not automatically presented to the model.
        return event

    def finalize(self, terminal_reference=None, delivery_reference=None, lock_receipt=None, *,
                 completion_status='unknown', coverage_evidence=None, missing_intervals=None,
                 recovery=False):
        if self.closed:
            return json.loads((self.folder/'summary.json').read_text())
        proof = lock_receipt or {'reason': 'no_trustworthy_candidate_closure'}
        gaps = [*self.missing_intervals, *(missing_intervals or [])]
        recovery = bool(recovery or self.reopened)
        if completion_status not in {'normal', 'partial', 'unknown'}:
            raise ValueError('Explicit observation completion status is required')
        normal_boundary = completion_status == 'normal' and not recovery and not gaps
        if completion_status == 'normal' and (recovery or gaps or self.errors or self.partial):
            completion_status = 'partial'
        if terminal_reference is not None:
            self.safely('artifacts', self._close_candidates, terminal_reference, delivery_reference, proof)
        if self.errors and completion_status == 'normal':
            completion_status = 'partial'
        self.log.record(self.eid('closure'), 'observation_closure', self.log.members[0],
            status=completion_status, recovery=recovery, missing_intervals=gaps, evidence=proof)
        for channel in sorted(CHANNELS):
            supplied = (coverage_evidence or {}).get(channel, {})
            if channel == 'presentations' and self.explicit_source_presentations:
                supplied = self.source_presentation_coverage_proof()
            relevant_errors = [e for e in self.errors if e['scope'] in
                {channel, 'closure', 'observer_error_log_unwritable'} or
                (channel == 'presentations' and e['scope'] in {'request_capture', 'response_capture'})]
            complete = (normal_boundary and channel not in self.partial
                        and not relevant_errors and supplied.get('complete') is True
                        and isinstance(supplied.get('evidence'), dict) and bool(supplied['evidence']))
            evidence = {'closure_receipt': proof, 'coverage_proven': complete,
                'observation_started_at_initial_state': not recovery and not gaps,
                'finalized_normally': normal_boundary,
                'channel_proof': supplied.get('evidence'), 'missing_proof_is_unknown': not bool(supplied)}
            self.log.record_coverage(self.eid('coverage'), channel, complete, evidence=evidence)
        value = self.log.summary()
        value.update(completion_status=completion_status, runtime_measurement_errors=self.errors,
            runtime_partial_channels=sorted(self.partial), missing_intervals=gaps,
            recovery=recovery, content_counter_available=self.log.tokenizer_id is not None,
            coverage_status={c: 'complete' if value['coverage'].get(c) else 'partial_or_unknown' for c in CHANNELS})
        atomic_write(self.folder/'summary.json', json_bytes(value))
        self.closed = True
        self.log.close()
        return value

    def _close_candidates(self, terminal, delivery, proof):
        actor = self.log.members[0]
        lock = self.eid('candidate')
        self.log.record(lock, 'candidate_locked', actor, reference=terminal,
                        generation_closed=True, evidence=proof)
        if delivery is None:
            return
        included = set(self.runtime.prepared.world._software()['deliveries'][-1]['included_patch_ids'])
        chain = []
        for patch, (integration, adopted, start) in self.integrations.items():
            validation = self.validations.get((actor, patch))
            if patch not in included or validation is None:
                continue
            if not self.log._rows[validation[0]]['data']['executed']:
                continue
            transitions, current = [], adopted
            for event, who, before, after in self.transitions[start:]:
                if who == actor and before == current:
                    transitions.append(event)
                    current = after
                    if current == delivery:
                        break
            if current != delivery:
                self.partial.add('artifacts')
                continue
            chain.append({'integration': integration, 'validation': validation[0], 'transitions': transitions})
        delivered = self.eid('delivery')
        self.log.record(delivered, 'final_delivery', actor, candidate_lock=lock,
            legal=True, submitted_reference=delivery, artifact_chain=chain, evidence=proof)
        for item in chain:
            pub = self.log._rows[item['integration']]['data']['publication']
            obj, published = self.information_objects[pub]
            self._stage(actor, 'incorporated_into_delivery', obj, prior=published,
                delivery_event=delivered, integration_event=item['integration'], evidence=proof)

    def close_partial(self, reason, *, evidence=None, recovery=False):
        self.partial.update(CHANNELS)
        self.missing_intervals.append(str(reason))
        return self.finalize(lock_receipt=evidence or {'reason': str(reason)},
                             completion_status='partial', recovery=recovery)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.closed:
            try:
                self.close_partial('exceptional_exit' if exc_type else 'exit_without_normal_finalize',
                    evidence={'exception_type': exc_type.__name__ if exc_type else None})
            except Exception:
                self.log.close()
                if exc_type is None:
                    raise
        return False
