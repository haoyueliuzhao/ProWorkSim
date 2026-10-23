"""CPU-only guards for the same-attempt two-worker deferred scorer takeover."""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_deferred_scoring_parallel_v054_r2 as parallel

original = parallel.original


def item(instance='django__django-10097'):
    return {'exception_id': 'a' * 32, 'slot': {'slot_id': 'slot-one', 'instance_id': instance},
            'domain': 'scoring', 'endpoint': 'code', 'original_request': {'key': 'request'},
            'original_completion': {'key': 'completion'}}


class Controls(unittest.TestCase):
    def test_holds_have_no_new_endpoint_side_effect(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in parallel.HOLDS:
                self.assertEqual(parallel.disposition(item(name), root), 'held_for_deterministic_failure_review')
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_held_result_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);value = item('psf__requests-1142')
            folder = root / 'exceptions' / value['exception_id'];folder.mkdir(parents=True)
            (folder / 'result.json').write_text('{}')
            self.assertEqual(parallel.disposition(value, root), 'existing_result')

    def test_original_child_exit_and_pid_reuse(self):
        expected = {'pid': 123, 'start_ticks': 456}
        self.assertTrue(parallel.exact_process_alive(expected, {**expected, 'state': 'S'}))
        self.assertFalse(parallel.exact_process_alive(expected, {**expected, 'state': 'Z'}))
        self.assertFalse(parallel.exact_process_alive(expected, None))
        self.assertFalse(parallel.exact_process_alive(expected, {'pid': 123, 'start_ticks': 999, 'state': 'S'}))

    def test_capacity_wait_preserves_original_lease_and_does_not_consume(self):
        lease = object();attempts = []
        def acquire():
            attempts.append(1)
            if len(attempts) < 3:
                raise BlockingIOError('busy')
            return lease
        self.assertIs(parallel.waiting_lease(acquire, clock=lambda: 1, sleep=lambda _: None), lease)
        self.assertEqual(len(attempts), 3)
        def busy():
            raise BlockingIOError('busy')
        clock = iter([0, 31])
        with self.assertRaises(parallel.CapacityWait):
            parallel.waiting_lease(busy, clock=lambda: next(clock), sleep=lambda _: None)

    def test_capacity_defer_writes_no_started_or_unresolved_result(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);value = item()
            request = {'preparation_only': False, 'actor_feedback': False, 'attempt': 1,
                       'trusted_output_root': str(root / 'grader'), 'limits': {'timeout_seconds': 1800}}
            def read(ref):
                return request if ref['key'] == 'request' else {'status': 'exited', 'returncode': 1}
            with (patch.object(original, 'read_ref', side_effect=read),
                  patch.object(original, 'expected_identity', return_value=({}, 'retry-id')),
                  patch.object(original, 'existing_report', return_value=None),
                  patch.object(original, 'grader_lease', side_effect=parallel.CapacityWait('busy')),
                  patch.object(original.subprocess, 'Popen') as spawn):
                with self.assertRaises(parallel.CapacityWait):
                    original.process_exception(value, root, datasets={})
            folder = root / 'exceptions' / value['exception_id']
            self.assertFalse((folder / 'started.json').exists())
            self.assertFalse((folder / 'result.json').exists())
            spawn.assert_not_called()

    def test_consumed_attempt_without_report_never_starts_third(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);value = item();folder = root / 'exceptions' / value['exception_id']
            folder.mkdir(parents=True);(folder / 'started.json').write_text('{"original":true}')
            request = {'preparation_only': False, 'actor_feedback': False, 'attempt': 1}
            with (patch.object(original, 'read_ref', return_value=request),
                  patch.object(original, 'expected_identity', return_value=({}, 'retry-id')),
                  patch.object(original, 'existing_report', return_value=None),
                  patch.object(original.subprocess, 'Popen') as spawn):
                result = original.process_exception(value, root, datasets={})
            self.assertEqual(result['status'], 'unresolved')
            self.assertEqual(result['additional_scoring_attempts'], 1)
            self.assertIn('never replay', result['reason'])
            self.assertEqual((folder / 'started.json').read_text(), '{"original":true}')
            spawn.assert_not_called()

    def test_original_consumed_attempt_receipt_is_adopted_without_new_score(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);value = item();folder = root / 'exceptions' / value['exception_id']
            folder.mkdir(parents=True);(folder / 'started.json').write_text('{}')
            request = {'preparation_only': False, 'actor_feedback': False, 'attempt': 1}
            official = {'resolved': False, 'run_id': 'retry-id', 'receipt': {'path': '/sealed/receipt'}}
            with (patch.object(original, 'read_ref', return_value=request),
                  patch.object(original, 'expected_identity', return_value=({}, 'retry-id')),
                  patch.object(original, 'existing_report', side_effect=[None, official]),
                  patch.object(original.subprocess, 'Popen') as spawn):
                result = original.process_exception(value, root, datasets={})
            self.assertEqual(result['status'], 'official_report')
            self.assertTrue(result['recovered_after_driver_interruption'])
            self.assertEqual(result['additional_scoring_attempts'], 1)
            self.assertEqual(result['official'], official)
            spawn.assert_not_called()

    def test_result_identity_cannot_cross_inventory(self):
        value = item();result = {'exception_id': value['exception_id'], 'slot_id': 'another-slot', 'domain': 'scoring'}
        with self.assertRaisesRegex(ValueError, 'crosses'):
            parallel.validate_result(value, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        parallel.write_new(args.output, {'passed': result.wasSuccessful(), 'controls': result.testsRun,
            'errors': len(result.errors), 'failures': len(result.failures), 'new_model_calls': 0,
            'real_scorer_calls': 0, 'services_mutated': False,
            'sources': [parallel.reference(parallel.__file__), parallel.reference(__file__)]})
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
