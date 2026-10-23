"""Finite CPU guards for exact endpoint transfer and no third scoring attempt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_qwen_four_endpoint_scoring_r6_v055 as driver


def row(root):
    legacy, folder = root / 'old', root / 'new'
    legacy.mkdir()
    folder.mkdir()
    return {'exception_id': 'a' * 32, 'slot': {'slot_id': 'slot-one'}, 'endpoint': 'code',
            'original_request': {'path': '/original/request', 'sha256': 'a' * 64},
            'request': {'path': '/new/request', 'sha256': 'b' * 64},
            'legacy_folder': str(legacy), 'folder': str(folder), 'pointer': str(folder / 'pointer.json'),
            'output': str(root / 'output')}


PLAN = {'path': '/new/plan', 'sha256': 'c' * 64}


class Controls(unittest.TestCase):
    def test_request_changes_only_allowed_execution_fields(self):
        original = {'attempt': 1, 'patch': {'sha256': 'locked'}, 'limits': {'timeout_seconds': 1800},
                    'receipt_output': '/original/pointer', 'candidate_tree_sha256': 'candidate'}
        result = driver.revised_request(original, {'old': True}, {'r6': True}, '0-3', '/new/pointer', {'transport': True})
        expected = dict(original, attempt=2, receipt_output='/new/pointer')
        self.assertEqual({k: v for k, v in result.items() if k not in {
            'original_scoring_request', 'scoring_execution_revision', 'scoring_cpuset_cpus', 'patch_transport'}}, expected)
        self.assertEqual(original['attempt'], 1)
        with self.assertRaises(ValueError):
            driver.revised_request(dict(original, attempt=2), {}, {}, '0-3', '/new/pointer')

    def test_transfer_blocks_original_processor_without_fake_started(self):
        with tempfile.TemporaryDirectory() as directory:
            r = row(Path(directory))
            transfer = driver.register_transfer(PLAN, r)
            legacy = Path(r['legacy_folder'])
            self.assertFalse((legacy / 'started.json').exists())
            result = json.loads((legacy / 'result.json').read_bytes())
            self.assertEqual(result['status'], 'unresolved')
            self.assertEqual(result['r6_transfer'], transfer)
            # Original processor looks for this exact deterministic folder.
            root = Path(directory) / 'compat'
            (root / 'exceptions').mkdir(parents=True)
            (root / 'exceptions' / r['exception_id']).symlink_to(legacy, target_is_directory=True)
            item = {'exception_id': r['exception_id'], 'slot': r['slot'], 'domain': 'scoring', 'endpoint': 'code'}
            with patch.object(driver.old.subprocess, 'Popen') as spawn:
                observed = driver.old.process_exception(item, root, datasets={})
            self.assertEqual(observed, result)
            spawn.assert_not_called()
            self.assertEqual(driver.register_transfer(PLAN, r), transfer)

    def test_old_started_or_unrelated_result_rejects_transfer(self):
        for filename in ('started.json', 'result.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                r = row(Path(directory))
                (Path(r['legacy_folder']) / filename).write_text('{}')
                with self.assertRaises(ValueError):
                    driver.register_transfer(PLAN, r)
                self.assertFalse((Path(r['folder']) / 'transfer.json').exists())

    def test_r6_started_without_report_never_redispatches(self):
        with tempfile.TemporaryDirectory() as directory:
            r = row(Path(directory))
            (Path(r['folder']) / 'started.json').write_text('{"attempt":2}')
            with patch.object(driver.subprocess, 'Popen') as spawn, patch.object(driver, 'grader_lease') as lease:
                result = driver.process_row(PLAN, r)
            self.assertEqual(result['status'], 'technical_unknown')
            self.assertTrue(result['additional_attempt_consumed'])
            spawn.assert_not_called()
            lease.assert_not_called()

    def test_cross_identity_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            r = row(root)
            r.update(expected_identity=driver.write_new(root / 'expected.json', {'identity': 'correct'}),
                request=driver.write_new(root / 'request.json', {}), run_id='expected-run',
                identity_sha256='expected-sha', cpuset='0-3')
            identity = driver.write_new(root / 'identity.json', {'identity': 'wrong'})
            receipt = driver.write_new(root / 'receipt.json', {'run_id': 'wrong-run'})
            Path(r['pointer']).write_text(json.dumps({'identity': identity, 'receipt': receipt}))
            with self.assertRaisesRegex(ValueError, 'crosses'):
                driver.receipt(r)

    def test_busy_global_grader_waits_without_endpoint_failure(self):
        lease = object()
        with patch.object(driver.old, 'grader_lease', side_effect=[BlockingIOError('busy'), lease]), patch.object(driver.time, 'sleep') as sleep:
            self.assertIs(driver.grader_lease(), lease)
        sleep.assert_called_once_with(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        driver.write_new(args.output, {'passed': result.wasSuccessful(), 'controls': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors), 'new_model_calls': 0,
            'real_grader_calls': 0, 'services_mutated': False,
            'sources': [driver.reference(driver.__file__), driver.reference(__file__)]})
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
