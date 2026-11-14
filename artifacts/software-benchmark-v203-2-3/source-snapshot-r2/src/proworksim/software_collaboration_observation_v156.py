"""Evidence-bound P0 observations; no model, solver authority or budget effects.

The v141 append-only storage, usage arithmetic and source-range checks are reused.
Only the new stream accepts v156 lifecycle/closure records. Old streams stay frozen.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from . import software_collaboration_observation_v141 as old
from .storage import json_bytes

VERSION = 'v156-independent-lifecycle-observer-r1'
ObservationError = old.ObservationError
CHANNELS = old.CHANNELS | {'lifecycle', 'public_tests'}
STAGES = ('produced', 'published', 'delivered', 'presented', 'retrieved',
          'behaviorally_used', 'validated', 'incorporated_into_delivery')
load_official_content_counter = old.load_official_content_counter


class ObservationLog(old.ObservationLog):
    def __init__(self, *args, **kwargs):
        self.current_versions = {}
        super().__init__(*args, **kwargs)

    def _append_line(self, value):
        if 'meta' in value:
            self._meta['version'] = VERSION
            value = {'meta': self._meta}
        return super()._append_line(value)

    def _replay(self):
        self._meta['version'] = VERSION
        return super()._replay()

    def _common(self, event_id, actor, kind, data):
        old._string(event_id, 'event_id')
        self._member(actor)
        if not isinstance(data, dict):
            raise ObservationError('Observation data must be an object')
        fingerprint = old._sha(old._json({'kind': kind, 'actor': actor, 'data': data}).encode())
        if event_id in self._events:
            if fingerprint != self._events[event_id]:
                raise ObservationError('An event ID cannot change its meaning')
            return fingerprint, True
        if len(self._events) >= old.MAX_EVENTS:
            raise ObservationError('Observation event bound reached')
        old._ref(data.get('evidence'))
        return fingerprint, False

    def _validate(self, event_id, kind, actor, data):
        custom = {'information_lifecycle', 'observation_closure', 'public_test',
                  'artifact_review', 'final_delivery', 'coverage', 'information_presented',
                  'source_presentations'}
        if kind not in custom:
            return super()._validate(event_id, kind, actor, data)
        fingerprint, duplicate = self._common(event_id, actor, kind, data)
        if duplicate:
            return fingerprint
        if kind == 'information_presented':
            request = old._string(data.get('request_id'), 'request_id')
            if request in self._presented_requests:
                raise ObservationError('One actual model input can only be presented once')
            owner = self._request_actors.get(request)
            if owner is not None and owner != actor:
                raise ObservationError('A provider request cannot cross member identities')
            ids = data.get('information_events')
            if not isinstance(ids, list) or len(ids) != len(set(ids)):
                raise ObservationError('Input information IDs must be unique')
            for key in ids:
                prior = self._prior(key, {'information_read', 'message_received', 'public_test'})
                if prior['actor'] != actor:
                    raise ObservationError('Another member\'s private receipt is not this input')
            old._ref(data.get('actual_input'))
        elif kind == 'source_presentations':
            request = old._string(data.get('request_id'), 'request_id')
            if self._request_actors.get(request, actor) != actor:
                raise ObservationError('Source presentation cannot cross request ownership')
            old._ref(data.get('manifest'))
            if data.get('status') not in {'presented', 'unknown', 'not_dispatched'}:
                raise ObservationError('Actual input exposure must preserve transport uncertainty')
            for key in ('known_source_occurrences', 'semantic_payload_bytes', 'semantic_unknown_bytes'):
                old._integer(data.get(key), key)
            if data.get('summary_parents_marked_presented') is not False:
                raise ObservationError('Summary lineage cannot manufacture original-text presentation')
            reports = data.get('presented_test_reports', [])
            if not isinstance(reports, list) or len(reports) != len(set(reports)):
                raise ObservationError('A report has one actual exposure per input, not per source span')
            for event in reports:
                report = self._prior(event, 'public_test')
                if report['actor'] != actor or data['status'] != 'presented':
                    raise ObservationError('Report presentation requires its own actual successful input')
        elif kind == 'artifact_review':
            decision = data.get('decision')
            if decision not in {'accept', 'request_changes', 'inconclusive'}:
                raise ObservationError('Review decision is invalid')
            if data.get('validation') is None:
                publication = self._patch(data.get('publication'))
                if decision == 'accept' or actor == publication['actor']:
                    raise ObservationError('Acceptance requires actually executed same-version validation')
                if data.get('reviewed_reference') != publication['data']['source_reference']:
                    raise ObservationError('Untested change requests must bind the fixed candidate')
                old._version(data.get('current_reference'))
                return fingerprint
            validation = self._prior(data.get('validation'), 'artifact_validated')
            tested = validation['data']['tested_reference']
            reviewed = data.get('reviewed_reference')
            current = data.get('current_reference')
            if (validation['actor'] != actor or data.get('decision') not in
                    {'accept', 'request_changes', 'inconclusive'}):
                raise ObservationError('Review identity or decision is invalid')
            if (old._version(reviewed) != old._version(tested)
                    or old._version(current) != old._version(reviewed)
                    or self.current_versions.get(actor, current) != current):
                raise ObservationError('Review requires the actual same current version')
            if validation['data']['executed'] is not True:
                raise ObservationError('Review requires a test actually executed on this version')
            # Accept is the recorded reviewer decision, not a test pass assertion.
        elif kind == 'final_delivery':
            lock = self._prior(data.get('candidate_lock'), 'candidate_locked')
            if actor != lock['actor'] or type(data.get('legal')) is not bool:
                raise ObservationError('Delivery requires the designated member and explicit legality')
            old._version(data.get('submitted_reference'))
            if any(r['kind'] == kind for r in self._rows.values()):
                raise ObservationError('Only one final legal-delivery observation is admitted')
            chain = data.get('artifact_chain', [])
            if not isinstance(chain, list) or len({i.get('integration') for i in chain}) != len(chain):
                raise ObservationError('Delivery provenance cannot duplicate integrations')
            for item in chain:
                integrated = self._prior(item.get('integration'), 'artifact_integrated')
                validated = self._prior(item.get('validation'), 'artifact_validated')
                acquired = self._prior(validated['data']['acquisition'], 'artifact_acquired')
                opportunity = self._prior(acquired['data']['opportunity'], 'artifact_opportunity')
                if (integrated['actor'] != actor or validated['actor'] != actor
                        or integrated['data']['publication'] != opportunity['data']['publication']
                        or validated['data']['executed'] is not True
                        or integrated['data']['result_reference'] != validated['data']['tested_reference']):
                    raise ObservationError('Delivery requires actual obtained and same-version tested work')
                current = integrated['data']['result_reference']
                for transition_id in item.get('transitions', []):
                    transition = self._prior(transition_id, 'version_transition')
                    if transition['actor'] != actor or transition['data']['from_reference'] != current:
                        raise ObservationError('Delivery source lineage is discontinuous')
                    current = transition['data']['to_reference']
                if current != data['submitted_reference']:
                    raise ObservationError('Integration does not reach the exact submitted version')
        elif kind == 'coverage':
            channel, complete = data.get('channel'), data.get('complete')
            if channel not in CHANNELS or type(complete) is not bool:
                raise ObservationError('Coverage requires an explicit known channel and bool')
            proof = data['evidence']
            if complete and (self._coverage.get(channel) is False or any(
                    proof.get(k) is not True for k in
                    ('coverage_proven', 'observation_started_at_initial_state', 'finalized_normally'))):
                raise ObservationError('Incomplete or unproven coverage cannot become complete')
        elif kind == 'observation_closure':
            if data.get('status') not in {'normal', 'partial', 'unknown'}:
                raise ObservationError('Closure status must preserve partial or unknown measurement')
            if not isinstance(data.get('missing_intervals'), list) or type(data.get('recovery')) is not bool:
                raise ObservationError('Closure must declare recovery and missing observation intervals')
            if data['status'] == 'normal' and (data['missing_intervals'] or data['recovery']):
                raise ObservationError('Recovery or missing intervals cannot claim continuous normal observation')
        elif kind == 'public_test':
            old._version(data.get('source_reference'))
            if (type(data.get('executed')) is not bool or type(data.get('passed')) not in {bool, type(None)}
                    or (data['passed'] is True and data['executed'] is not True)):
                raise ObservationError('Test execution and test pass are separate facts')
            old._ref(data.get('command'))
            old._ref(data.get('report'))
            if not isinstance(data.get('sessions'), list):
                raise ObservationError('Public tests require session identity records')
            sessions = data['sessions']
            ids = [s.get('run_id') for s in sessions]
            if len(ids) != len(set(ids)):
                raise ObservationError('A repeated session report must be deduplicated before observation')
            roots = [s for s in sessions if s.get('root') is True]
            if sessions and len(roots) != 1:
                raise ObservationError('Session evidence needs one command root')
            for session in sessions:
                old._string(session.get('run_id'), 'session ID')
                if not session.get('root') and session.get('parent_run_id') not in ids:
                    raise ObservationError('Child test session lost its parent')
        else:
            self._validate_lifecycle(actor, data)
        return fingerprint

    def _validate_lifecycle(self, actor, data):
        stage = data.get('stage')
        if stage not in STAGES:
            raise ObservationError('Unknown information lifecycle stage')
        old._string(data.get('object_id'), 'information object')
        old._string(data.get('observed_at_utc'), 'observation time')
        origin = data.get('origin_member')
        self._member(origin)
        allowed = data.get('allowed_members')
        if not isinstance(allowed, list) or not set(allowed) <= set(self.members) or origin not in allowed:
            raise ObservationError('Information access requires a frozen explicit audience')
        if actor not in allowed:
            raise ObservationError('Private information is not authorized for this actor')
        if data.get('source_reference') is not None:
            old._version(data['source_reference'])
        digest = data.get('content_sha256')
        if not isinstance(digest, str) or len(digest) != 64:
            raise ObservationError('Information lifecycle requires immutable content identity')
        prior = None
        if data.get('prior_event') is not None:
            prior = self._prior(data['prior_event'], 'information_lifecycle')
            for key in ('object_id', 'origin_member', 'content_sha256', 'source_reference'):
                if prior['data'].get(key) != data.get(key):
                    raise ObservationError('A lifecycle event cannot change its object or version')
            if allowed != prior['data']['allowed_members']:
                raise ObservationError('A lifecycle event cannot silently expand its audience')
        if stage in {'produced', 'published'}:
            if actor != origin:
                raise ObservationError('Only the observed origin can produce or publish its content')
        elif stage == 'delivered':
            if prior is None or prior['data']['stage'] != 'published':
                raise ObservationError('Delivery requires actual published information')
        elif stage == 'presented':
            if prior is None or (prior['actor'] != actor and actor != origin):
                raise ObservationError('Presentation needs this actor\'s own lawful source receipt')
            old._string(data.get('request_id'), 'actual presentation request')
            old._ref(data.get('actual_input'))
        elif stage == 'retrieved':
            if data.get('authorized') is not True:
                raise ObservationError('A denied retrieval cannot become information obtained')
            old._ref(data.get('tool_receipt'))
        elif stage == 'behaviorally_used':
            if prior is None or prior['actor'] != actor or prior['data']['stage'] not in {'presented', 'retrieved'}:
                raise ObservationError('Delivery/presentation alone is not evidence of behavior use')
            action = self._prior(data.get('action_event'), 'action')
            if action['actor'] != actor or action['data'].get('ok') is not True:
                raise ObservationError('Behavior use requires an actual successful bound action')
            old._ref(data.get('source_action_binding'))
        elif stage == 'validated':
            test = self._prior(data.get('test_event'), {'public_test', 'artifact_validated'})
            tested = test['data'].get('source_reference', test['data'].get('tested_reference'))
            if test['actor'] != actor or tested != data.get('source_reference') or test['data']['executed'] is not True:
                raise ObservationError('Validation requires actual same-version test execution')
            if data.get('passed') is not test['data']['passed']:
                raise ObservationError('Validation must retain the observed pass/fail/unknown result')
        elif stage == 'incorporated_into_delivery':
            delivery = self._prior(data.get('delivery_event'), 'final_delivery')
            integration = self._prior(data.get('integration_event'), 'artifact_integrated')
            publication = self._patch(integration['data']['publication'])
            if (delivery['actor'] != actor or delivery['data']['legal'] is not True
                    or not any(i['integration'] == integration['event_id'] for i in delivery['data']['artifact_chain'])
                    or publication['data']['source_reference'] != data.get('source_reference')
                    or publication['actor'] != data.get('origin_member')
                    or old._sha(json_bytes(publication['data']['content_identity'])) != data['content_sha256']):
                raise ObservationError('Incorporation requires the exact observed legal-delivery chain')

    def _apply(self, row, fingerprint):
        super()._apply(row, fingerprint)
        data = row['data']
        if row['kind'] == 'version_transition':
            self.current_versions[row['actor']] = data['to_reference']
        elif row['kind'] == 'artifact_acquired':
            self.current_versions[row['actor']] = data['adopted_reference']
        elif row['kind'] == 'artifact_published':
            self.current_versions[row['actor']] = data['source_reference']

    def record_lifecycle(self, event_id, actor, *, stage, object_id, origin_member,
                         allowed_members, content_sha256, evidence, source_reference=None,
                         prior_event=None, observed_at_utc=None, **facts):
        # Repeated event ID has a stable timestamp, preserving exact replay idempotence.
        prior = self._rows.get(event_id)
        stamp = (prior['data']['observed_at_utc'] if prior else
                 datetime.now(timezone.utc).isoformat())
        return self.record(event_id, 'information_lifecycle', actor, stage=stage,
            object_id=object_id, origin_member=origin_member, allowed_members=list(allowed_members),
            content_sha256=content_sha256, source_reference=source_reference, prior_event=prior_event,
            observed_at_utc=observed_at_utc or stamp, time_basis='observer_receipt', evidence=evidence, **facts)

    def record_review(self, event_id, actor, validation, decision, *, current_reference, evidence, publication=None):
        tested = (self._prior(validation, 'artifact_validated')['data']['tested_reference'] if validation
                  else self._patch(publication)['data']['source_reference'])
        return self.record(event_id, 'artifact_review', actor, validation=validation, decision=decision,
                           publication=publication, reviewed_reference=tested,
                           current_reference=current_reference, evidence=evidence)

    def summary(self):
        value = super().summary()
        rows = list(self._rows.values())
        stages = Counter(r['data']['stage'] for r in rows if r['kind'] == 'information_lifecycle')
        reviews = [r for r in rows if r['kind'] == 'artifact_review']
        accepted = [r for r in reviews if r['data']['decision'] == 'accept']

        def current_acceptance(row):
            validation = self._rows[row['data']['validation']]
            acquired = self._rows[validation['data']['acquisition']]
            opportunity = self._rows[acquired['data']['opportunity']]
            publication = self._rows[opportunity['data']['publication']]
            return (row['data']['reviewed_reference'] == self.current_versions.get(
                        row['actor'], row['data']['current_reference'])
                    and publication['data']['source_reference'] == self.current_versions.get(
                        publication['actor'], publication['data']['source_reference']))

        value.update(version=VERSION, lifecycle={stage: stages[stage] for stage in STAGES},
            lifecycle_stages_are_independent=True, presented_is_understood=False,
            validated_means_actual_validation_attempt_not_test_pass=True,
            review={'accept_decisions': len(accepted),
                    'current_version_acceptances': sum(current_acceptance(r) for r in accepted),
                    'accept_implies_test_pass': False},
            public_tests={'executed': sum(r['data']['executed'] for r in rows if r['kind'] == 'public_test'),
                          'passed': sum(r['data']['passed'] is True for r in rows if r['kind'] == 'public_test'),
                          'reports_saved': sum(r['data']['report'].get('saved') is True
                                               for r in rows if r['kind'] == 'public_test'),
                          'reports_presented': sum(self._rows[e]['kind'] == 'public_test'
                              for r in rows if r['kind'] == 'information_presented'
                              for e in r['data']['information_events']),
                          'nested_counts_added_to_root': False},
            closures=[r['data'] for r in rows if r['kind'] == 'observation_closure'])
        value['artifacts']['same_version_public_test_executed'] = sum(
            r['data']['executed'] for r in rows if r['kind'] == 'artifact_validated')
        source_rows = [r for r in rows if r['kind'] == 'source_presentations']
        value['source_presentations'] = {'requests': len(source_rows),
            'presented_requests': sum(r['data']['status'] == 'presented' for r in source_rows),
            'unknown_requests': sum(r['data']['status'] == 'unknown' for r in source_rows),
            'known_source_occurrences': sum(r['data']['known_source_occurrences'] for r in source_rows
                                            if r['data']['status'] == 'presented'),
            'fragment_occurrences': sum(r['data']['known_source_occurrences'] for r in source_rows
                                         if r['data']['status'] == 'presented'),
            'source_request_pairs': (sum(r['data']['unique_sources_in_request'] for r in source_rows
                if r['data']['status'] == 'presented') if all('unique_sources_in_request' in r['data']
                                                            for r in source_rows) else None),
            'semantic_unknown_bytes': sum(r['data']['semantic_unknown_bytes'] for r in source_rows),
            'summary_parent_originals_counted_as_presented': False,
            'byte_source_coverage_is_exact_token_coverage': False}
        value['lifecycle_direct_presentation_events'] = value['lifecycle']['presented']
        if source_rows:
            value['lifecycle']['presented'] = None
        value['lifecycle_presentation_count_unit'] = ('unavailable_legacy_event_counter_in_explicit_source_mode'
                                                     if source_rows else 'direct_information_presentation_events')
        value['lifecycle_stage_counts_are_not_a_same_unit_conversion_funnel'] = True
        value['public_tests']['reports_presented'] += sum(
            len(r['data'].get('presented_test_reports', [])) for r in source_rows)
        value['public_tests']['presentation_unit'] = 'one_report_with_an_actual_feedback_excerpt_per_request'
        value['public_tests']['presentation_does_not_imply_entire_test_log_visible'] = True
        return value
