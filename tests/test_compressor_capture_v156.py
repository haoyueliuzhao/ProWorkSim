"""Two CPU integrations exercising the actual renderer/capture/shared-pool path."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proworksim.software_communication_pilot_v156 import (
    FIELDS, CommunicationRenderer, CompressionTransient, ImmutableCommunicationStore,
)
from proworksim.software_communication_runtime_v156 import SharedTeamPool
from proworksim.software_compressor_capture_v156 import AuditedCompressorTransport
from proworksim.software_input_provenance_v156 import load_persisted_request, verify_request


class ReplyScript:
    evidence_domain = 'cpu_synthetic'
    def __init__(self, *, bad=False, once503=False):
        self.bad, self.once503, self.calls = bad, once503, []

    def __call__(self, raw, *, identity):
        self.calls.append((raw, copy.deepcopy(identity)))
        if self.once503:
            self.once503 = False
            error = CompressionTransient('http_503', usage={
                'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12})
            error.http_status = 503
            error.response_body = {'error': {'message': 'CPU synthetic 503'}, 'model': 'scripted-flash',
                                   'usage': error.usage}
            raise error
        data = json.loads(json.loads(raw)['messages'][1]['content'])
        fields = {f: [r['fact_id'] for r in data['facts'] if r['field'] == f] for f in FIELDS}
        if self.bad:
            fields['test_status'] = []
        return {'id': 'cpu-response:'+identity['request_id'], 'model': 'scripted-flash',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
                'source_id': data['source_id'], 'version_hash': data['version_hash'], 'fields': fields})}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}


class CaptureIntegration(unittest.TestCase):
    def setUp(self):
        target = os.getenv('PROWORKSIM_V156_CAPTURE_CONTROL_OUTPUT')
        self.tmp = None
        if target:
            self.root = Path(target)/self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            self.tmp = tempfile.TemporaryDirectory()
            self.root = Path(self.tmp.name)
        self.pool = SharedTeamPool(self.root/'pool', 'capture-team:'+self._testMethodName)
        self.store = ImmutableCommunicationStore(self.root/'sources')
        pieces = [('conclusion', '重复 "quoted"', True), ('change', '重复 "quoted"', False),
                  ('test_status', 'pytest failed: E7', False)]
        raw, facts = '', []
        for n, (field, text, critical) in enumerate(pieces):
            start = len(raw)
            raw += text+'\n'
            facts.append({'fact_id': 'fact-'+str(n), 'field': field, 'start_character': start,
                'end_character': start+len(text), 'critical': critical, 'provenance': 'sender_claim'})
        self.ref = self.store.publish({'source_id': 'published-message-7', 'sender': 'member_001',
            'recipients': ['member_002'], 'task_id': 'public__task-1', 'raw_text': raw,
            'facts_complete': True, 'facts': facts,
            'metadata': {'published_event_id': 'message-event-7', 'artifact_version': 'code-v2'},
            'evidence': []})

    def tearDown(self):
        if self.tmp:
            self.tmp.cleanup()

    def run_case(self, name, *, bad=False, once503=False):
        delegate = ReplyScript(bad=bad, once503=once503)
        capture = AuditedCompressorTransport(self.root/name, self.store, delegate, self.pool.snapshot()['team_id'])
        renderer = CommunicationRenderer('C2', self.store, self.pool, capture,
            authorize=lambda *args: True, token_counter=lambda text: len(text.split()),
            input_bound=lambda payload: 2000)
        result = renderer.render(self.ref, 'member_002', 'reviewer', name)
        (self.root/name/'render-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        return result, capture, delegate

    def checked_receipts(self, capture, delegate):
        self.assertEqual(len(capture.receipts), len(delegate.calls))
        for receipt, (wire, identity) in zip(capture.receipts, delegate.calls):
            self.assertFalse(receipt['budget_reserved_or_settled_by_wrapper'])
            self.assertEqual(Path(receipt['payload']['path']).read_bytes(), wire)
            capture_file = json.loads(Path(receipt['request_capture']['path']).read_text())
            built = load_persisted_request(capture_file)
            self.assertTrue(verify_request(built))
            self.assertEqual(built.manifest['identity']['request_id'], identity['request_id'])
            self.assertEqual(built.manifest['identity']['attempt_id'], identity['request_id'])
            self.assertEqual(built.manifest['identity']['member_id'], 'compression-service')
            self.assertFalse(built.manifest['identity']['autonomous_member'])
            sources = [s['source'] for s in built.manifest['spans'] if s['source']]
            self.assertEqual({s['category'] for s in sources}, {'Base/Template', 'Peer-message', 'Artifact'})
            peer_ids = {s['source_id'] for s in sources if s['category'] == 'Peer-message'}
            self.assertEqual(peer_ids, {self.ref['source_id']+':fact:fact-'+str(i) for i in range(3)})
            self.assertTrue(all(s['version_sha256'] is None for s in sources))
            response = json.loads(Path(receipt['response']['path']).read_text())
            self.assertEqual(response['provider_fingerprint']['status'], 'unavailable')
            self.assertEqual(response['provider_model']['value'], 'scripted-flash')

    def test_success_and_paid_schema_fallback_have_exact_provenance_and_usage(self):
        result, capture, delegate = self.run_case('success')
        self.assertIsNone(result['fallback_reason'])
        self.checked_receipts(capture, delegate)
        result, capture2, delegate2 = self.run_case('schema-fallback', bad=True)
        self.assertEqual(result['fallback_reason'], 'critical_fact_omitted')
        self.assertEqual(result['representation'], 'raw')
        self.checked_receipts(capture2, delegate2)
        self.assertEqual(self.pool.snapshot()['physical_attempts'], 2)
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 240)
        self.assertEqual(self.pool.snapshot()['per_purpose']['compressor']['requests'], 2)
        # A capture-level success records a received/paid response, not acceptance
        # of its summary: the renderer separately records schema fallback.
        self.assertEqual(capture2.receipts[0]['outcome'], 'success')

    def test_503_retry_keeps_each_attempt_exception_response_and_single_budget_charge(self):
        result, capture, delegate = self.run_case('retry', once503=True)
        self.assertIsNone(result['fallback_reason'])
        self.assertEqual(len(capture.receipts), 2)
        self.checked_receipts(capture, delegate)
        first = capture.receipts[0]
        self.assertEqual(first['outcome'], 'http_error')
        error = json.loads(Path(first['exception']['path']).read_text())
        self.assertEqual(error['http_status'], 503)
        self.assertEqual(error['usage']['total_tokens'], 12)
        response = json.loads(Path(first['response']['path']).read_text())
        self.assertEqual(response['usage']['total_tokens'], 12)
        self.assertNotEqual(capture.receipts[0]['request_id'], capture.receipts[1]['request_id'])
        self.assertEqual(self.pool.snapshot()['physical_attempts'], 2)
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 132)
        self.assertEqual(self.pool.snapshot()['unresolved_reserved_tokens'], 0)

    def test_observer_disk_failure_does_not_erase_paid_usage_or_replace_retry(self):
        from proworksim import software_compressor_capture_v156 as module
        original = module._write
        def fail_observation(path, data):
            if path.name in {'response-original.json', 'exception-original.json'}:
                raise OSError('synthetic observer-only storage failure')
            return original(path, data)
        with patch.object(module, '_write', side_effect=fail_observation):
            result, capture, delegate = self.run_case('observer-failure', once503=True)
        self.assertIsNone(result['fallback_reason'])
        self.assertEqual(len(delegate.calls), 2)
        self.assertEqual(self.pool.snapshot()['known_actual_tokens'], 132)
        self.assertEqual(self.pool.snapshot()['unresolved_reserved_tokens'], 0)
        self.assertEqual(len(capture.errors), 2)
        self.assertEqual(capture.receipts[0]['outcome'], 'http_error')
        self.assertEqual(capture.receipts[1]['outcome'], 'success')


if __name__ == '__main__':
    unittest.main()
