"""CPU-only failure and privacy controls for the communication mechanism."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from proworksim.software_communication_pilot_v156 import (
    CONDITIONS, FIELDS, PULL_SCHEMA, PROMPT_SHA256, CommunicationRenderer,
    CompressionTransient, ImmutableCommunicationStore, SourceRejected,
)
from proworksim.software_communication_runtime_v156 import SharedTeamPool, AccountingConflict


class ScriptedTransport:
    evidence_domain = 'cpu_synthetic'
    def __init__(self, reply=None, mutate=None, failures=None):
        self.calls, self.reply, self.mutate, self.failures = [], reply, mutate, list(failures or [])

    def __call__(self, raw, *, identity):
        payload = json.loads(raw)
        self.calls.append((payload, identity))
        if self.failures:
            error = self.failures.pop(0)
            if error is not None:
                raise error
        data = json.loads(payload['messages'][1]['content'])
        selection = {'source_id': data['source_id'], 'version_hash': data['version_hash'],
                     'fields': {f: [r['fact_id'] for r in data['facts'] if r['field'] == f] for f in FIELDS}}
        if self.mutate:
            self.mutate(selection)
        return self.reply or {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(selection)}}],
                              'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
                              'model': 'scripted-flash', 'system_fingerprint': 'cpu-only'}


class CommunicationControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pool = SharedTeamPool(self.root/'pool', 'team-test')
        self.store = ImmutableCommunicationStore(self.root/'sources')
        parts = [('conclusion', 'Fix attempted.', True), ('test_status', 'pytest failed: E7.', False),
                 ('next_action', 'Please inspect code.', True), ('unknown', 'Regression status unknown.', False)]
        raw, facts = '', []
        for n, (field, text, critical) in enumerate(parts):
            start = len(raw)
            raw += text + '\n'
            facts.append({'fact_id': f'f{n}', 'field': field, 'start_character': start,
                          'end_character': start+len(text), 'critical': critical,
                          'provenance': 'sender_claim'})
        self.source = {'source_id': 'msg-1', 'sender': 'member_001', 'recipients': ['member_002'],
                       'task_id': 'repo__issue-1', 'raw_text': raw, 'facts': facts, 'facts_complete': True,
                       'metadata': {'artifact_version': 'patch-v1', 'base_hash': 'abc',
                                    'test_refs': ['test-failed-1']},
                       'evidence': [{'evidence_id': 'test-failed-1', 'kind': 'public_test',
                                     'text': 'FAILURE E7\nprivate-marker-not-default', 'version_hash': 'test-v1'}]}
        self.ref = self.store.publish(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def renderer(self, condition='C1', transport=None, **kwargs):
        return CommunicationRenderer(condition, self.store, self.pool,
            transport or ScriptedTransport(), authorize=lambda *args: True,
            token_counter=lambda text: len(text.split()), input_bound=lambda payload: 2000, **kwargs)

    def test_c0_has_zero_compressor_calls_same_raw_and_refs(self):
        t = ScriptedTransport()
        r = self.renderer('C0', t).render(self.ref, 'member_002', 'reviewer', 'r0')
        self.assertEqual(r['raw_text'], self.source['raw_text'])
        self.assertEqual(r['L0']['metadata']['test_refs'], ['test-failed-1'])
        self.assertEqual(t.calls, [])
        self.assertEqual(self.pool.snapshot()['physical_attempts'], 0)

    def test_c1_c2_model_requests_have_different_selection_context_same_params(self):
        transcripts = []
        for c in ('C1', 'C2'):
            t = ScriptedTransport()
            r = self.renderer(c, t).render(self.ref, 'member_002', 'reviewer', c)
            self.assertIsNone(r['fallback_reason'])
            self.assertIn('pytest failed: E7.', r['L1'])
            self.assertNotIn('private-marker-not-default', json.dumps(r))
            self.assertEqual(r['L0']['freshness'], 'unknown')
            p = t.calls[0][0]
            self.assertEqual((p['temperature'], p['top_p'], p['max_tokens']), (.2, 1, 512))
            transcripts.append(json.loads(p['messages'][1]['content']))
        self.assertNotEqual(PROMPT_SHA256['C1'], PROMPT_SHA256['C2'])
        self.assertEqual(transcripts[0]['recipient_role'], 'generic')
        self.assertEqual(transcripts[1]['recipient_role'], 'reviewer')
        self.assertNotEqual(transcripts[0]['field_priority'], transcripts[1]['field_priority'])
        self.assertEqual(self.pool.snapshot()['per_purpose']['compressor']['total_tokens'], 240)

    def test_fabrication_wrong_version_and_critical_omission_fallback_retains_cost(self):
        mutations = [lambda d: d.update(version_hash='0'*64),
                     lambda d: d['fields']['conclusion'].append('fabricated-pass'),
                     lambda d: d['fields'].__setitem__('test_status', []),
                     lambda d: d['fields'].__setitem__('unknown', [])]
        for n, mutate in enumerate(mutations):
            r = self.renderer(transport=ScriptedTransport(mutate=mutate)).render(
                self.ref, 'member_002', 'reviewer', 'bad'+str(n))
            self.assertEqual(r['representation'], 'raw')
            self.assertEqual(r['raw_text'], self.source['raw_text'])
            self.assertTrue(r['fallback_reason'])
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 480)

    def test_unstructured_source_fallback_does_not_silently_extract(self):
        d = copy.deepcopy(self.source)
        d.update(source_id='unstructured', facts_complete=False, facts=[])
        t = ScriptedTransport()
        r = self.renderer(transport=t).render(self.store.publish(d), 'member_002', 'reviewer', 'raw')
        self.assertEqual(r['representation'], 'raw')
        self.assertEqual(t.calls, [])
        d['facts_complete'] = True
        with self.assertRaises(SourceRejected):
            self.store.publish(d)

    def test_summary_limit_applies_to_host_rendered_text(self):
        r = self.renderer()
        r.token_counter = lambda text: 513
        result = r.render(self.ref, 'member_002', 'reviewer', 'long')
        self.assertEqual(result['fallback_reason'], 'rendered_summary_exceeds_512_tokens')
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 120)

    def test_retry_and_uncertain_each_consume_team_attempt_and_unknown_reservation(self):
        t = ScriptedTransport(failures=[CompressionTransient('timeout'), None])
        r = self.renderer(transport=t).render(self.ref, 'member_002', 'reviewer', 'retry')
        view = self.pool.snapshot()
        self.assertEqual(view['physical_attempts'], 2)
        self.assertEqual(view['known_actual_tokens'], 120)
        self.assertEqual(view['unresolved_reserved_tokens'], 2512)
        self.assertEqual(len(r['compressor_attempts']), 2)
        self.assertIsNone(r['fallback_reason'])

    def test_actual_overrun_is_not_hidden_by_raw_fallback(self):
        t = ScriptedTransport(reply={'usage': {'prompt_tokens': 3000, 'completion_tokens': 20,
                                             'total_tokens': 3020}})
        with self.assertRaises(AccountingConflict):
            self.renderer(transport=t).render(self.ref, 'member_002', 'reviewer', 'overrun')
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 3020)

    def test_unknown_response_usage_fallback_retains_reservation(self):
        r = self.renderer(transport=ScriptedTransport(reply={'choices': []})).render(
            self.ref, 'member_002', 'reviewer', 'missing')
        self.assertEqual(r['fallback_reason'], 'compressor_usage_unknown')
        self.assertEqual(self.pool.snapshot()['unresolved_reserved_tokens'], 2512)

    def test_replay_after_restart_cannot_dispatch(self):
        t = ScriptedTransport()
        self.renderer(transport=t).render(self.ref, 'member_002', 'reviewer', 'identity')
        self.store = ImmutableCommunicationStore(self.root/'sources')
        with self.assertRaises(SourceRejected):
            self.renderer(transport=t).render(self.ref, 'member_002', 'reviewer', 'identity')
        self.assertEqual(len(t.calls), 1)

    def test_same_pull_schema_and_acl_all_conditions_and_old_version(self):
        args = {**self.ref, 'level': 'L3', 'start_character': 0, 'max_characters': 8192}
        pages = []
        for c in CONDITIONS:
            r = self.renderer(c)
            pages.append(r.pull(args, 'member_002')['text'])
            with self.assertRaises(PermissionError):
                r.pull(args, 'member_003')
            r.authorize = lambda *args: False
            with self.assertRaises(PermissionError):
                r.pull(args, 'member_002')
        self.assertEqual(pages[0], pages[1])
        self.assertEqual(pages[1], pages[2])
        self.assertIn('private-marker-not-default', pages[0])
        self.assertEqual(PULL_SCHEMA['function']['name'], 'communication_pull')
        self.assertEqual(self.pool.snapshot()['physical_attempts'], 0)
        changed = copy.deepcopy(self.source)
        changed['supersedes'] = self.ref
        changed['metadata']['artifact_version'] = 'patch-v2'
        newref = self.store.publish(changed)
        self.assertNotEqual(self.ref['version_hash'], newref['version_hash'])
        self.assertEqual(self.store.get(self.ref)['metadata']['artifact_version'], 'patch-v1')

    def test_source_tamper_and_private_evidence_rejected(self):
        d = copy.deepcopy(self.source)
        d['evidence'][0]['kind'] = 'hidden_test'
        with self.assertRaises(SourceRejected):
            self.store.publish(d)
        path = self.store._path(self.ref)
        source = json.loads(path.read_bytes())
        source['metadata']['artifact_version'] = 'forged'
        path.write_text(json.dumps(source))
        restarted = ImmutableCommunicationStore(self.root/'sources')
        with self.assertRaises(SourceRejected):
            restarted.get(self.ref)

    def test_compressor_budget_stop_raw_fallback_preserves_existing_usage_and_hold(self):
        self.pool = SharedTeamPool(self.root/'small-pool', 'small-team', token_limit=3000)
        self.pool.reserve('old-settled', 'condenser', 200, 100)
        self.pool.settle('old-settled', {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120})
        self.pool.reserve('old-unknown', 'condenser', 1000, 700)
        self.pool.uncertain('old-unknown', {'reason': 'previous-timeout'})
        before = self.pool.snapshot()
        t = ScriptedTransport()
        r = self.renderer(transport=t).render(self.ref, 'member_002', 'reviewer', 'no-budget')
        self.assertEqual(r['fallback_reason'], 'compression_budget_unavailable')
        self.assertEqual(r['raw_text'], self.source['raw_text'])
        self.assertEqual(r['compressor_attempts'], [])
        self.assertEqual(t.calls, [])
        self.assertEqual(self.pool.snapshot(), before)

    def test_live_transport_cannot_be_accidentally_enabled(self):
        with self.assertRaises(PermissionError):
            self.renderer(transport=lambda *a, **kw: None)


if __name__ == '__main__':
    unittest.main()
