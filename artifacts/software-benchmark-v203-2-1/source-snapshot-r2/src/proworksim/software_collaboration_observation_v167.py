"""Observe accepted World review receipts without inventing an acquisition/test."""
from __future__ import annotations

from . import software_collaboration_observation_v156 as previous

VERSION = 'v167-world-review-and-bounded-test-observation-r1'
ObservationError = previous.ObservationError


class ObservationLog(previous.ObservationLog):
    def _append_line(self, value):
        if 'meta' in value:
            self._meta['version'] = VERSION
            value = {'meta': self._meta}
        # Bypass v156's version replacement, retaining the append-only writer.
        return previous.old.ObservationLog._append_line(self, value)

    def _replay(self):
        self._meta['version'] = VERSION
        return previous.old.ObservationLog._replay(self)

    def _validate(self, event_id, kind, actor, data):
        if kind != 'world_review':
            return super()._validate(event_id, kind, actor, data)
        fingerprint, duplicate = self._common(event_id, actor, kind, data)
        if duplicate:
            return fingerprint
        publication = self._patch(data.get('publication'))
        receipt, current = data['receipt'], data['current_identity']
        previous.old._ref(data['original_receipt'])
        previous.old._version(current['source_reference'])
        if (actor == publication['actor'] or receipt['actor_id'] != actor
                or receipt['author'] != publication['actor']
                or receipt['patch_id'] != publication['data']['patch_id']
                or receipt['identity']['source_reference'] != publication['data']['source_reference']
                or receipt['decision'] not in {'accept', 'request_changes'}):
            raise ObservationError('World review lost member, decision or publication identity')
        for key, expected in publication['data']['content_identity'].items():
            if receipt['identity'].get(key) != expected:
                raise ObservationError('World review changed the published candidate content')
        if receipt['decision'] == 'request_changes':
            # The World allows an untested change request against a visible patch.
            if receipt.get('adopted_source_reference') is not None or receipt.get('test_evidence') is not None:
                raise ObservationError('Do not invent validation for an untested change request')
            return fingerprint
        test = receipt.get('test_evidence') or {}
        if (receipt['adopted_source_reference'] != current['source_reference']
                or self.current_versions.get(actor, current['source_reference']) != current['source_reference']
                or test.get('actor_id') != actor or test.get('executed') is not True
                or type(test.get('passed')) not in {bool, type(None)}):
            raise ObservationError('Acceptance requires the actual reviewer and current executed test')
        for key in ('source_reference', 'files_sha256', 'entry_metadata_sha256'):
            if test.get(key) != current[key]:
                raise ObservationError('Acceptance test must bind this exact current version')
        for key in ('files_sha256', 'entry_metadata_sha256'):
            if current[key] != receipt['identity'][key]:
                raise ObservationError('Accepted current tree differs from the fixed patch')
        return fingerprint

    def summary(self):
        value = super().summary()
        rows = [r for r in self._rows.values() if r['kind'] == 'world_review']
        accepted = [r for r in rows if r['data']['receipt']['decision'] == 'accept']

        def current(row):
            data = row['data']
            pub = self._rows[data['publication']]
            return (data['current_identity']['source_reference'] == self.current_versions.get(
                        row['actor'], data['current_identity']['source_reference'])
                    and pub['data']['source_reference'] == self.current_versions.get(
                        pub['actor'], pub['data']['source_reference']))

        value['version'] = VERSION
        value['review']['accept_decisions'] += len(accepted)
        value['review']['current_version_acceptances'] += sum(current(r) for r in accepted)
        value['review']['authoritative_world_receipts'] = len(rows)
        value['artifacts']['independent_review_events'] += len(rows)
        value['public_tests']['full_session_hierarchy_retained_in_report'] = True
        value['public_tests']['inline_sessions_scope'] = 'command_root_only'
        return value
