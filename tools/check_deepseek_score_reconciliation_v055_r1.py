"""Finite CPU controls for immutable requests, capacity waits and no replay."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from proworksim.software_benchmark_candidates_v054 import write_new

SOURCE = Path(__file__).with_name('reconcile_deepseek_scores_v055_r1.py')
spec = importlib.util.spec_from_file_location('deep_reconciliation_controlled', SOURCE)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def reject(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Modified scientific request was accepted')


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='deep-score-reconcile-cpu-') as name:
        root = Path(name)
        with patch.object(driver, 'OUT', root):
            original = {'attempt': 1, 'receipt_output': str(root / 'old-pointer.json'),
                'patch': {'path': '/unchanged.patch'}, 'trusted_output_root': str(root / 'outputs'),
                'limits': driver.EXPECTED_LIMITS, 'candidate_tree_sha256': 'a' * 64}
            original_ref = write_new(root / 'original.json', original)
            revision = {'path': '/sealed-revision', 'sha256': 'b' * 64, 'bytes': 10}
            item = {'endpoint_id': 'fixture', 'slot': {'slot_id': 'v055-fixture'}, 'endpoint': 'code',
                'category': 'test_timeout_1800', 'original_request': original_ref, 'execution_revision': revision,
                'lane': 0, 'original_identity': None, 'original_run_id': None,
                'retry_identity': {'fixture': True}, 'retry_run_id': 'fixture-new'}
            folder = root / 'endpoints' / item['endpoint_id']
            revised = driver.retry_request(original, folder, original_ref, revision, 0)
            item['retry_request'] = revised
            driver.validate_retry(original, revised, folder, item)
            bad = deepcopy(revised)
            bad['candidate_tree_sha256'] = 'c' * 64
            reject(lambda: driver.validate_retry(original, bad, folder, item))
            reject(lambda: driver.retry_request({**original, 'attempt': 2}, folder, original_ref, revision, 0))
            assert original['attempt'] == 1 and original['patch'] == revised['patch']
            checks.append('only_attempt2_pointer_and_sealed_execution_metadata_change')
            sets = [set(driver.r6.cpus(value)) for value in driver.CPUSETS]
            assert len(set.union(*sets)) == 16 and all(not value & {0, 1, 2, 3, 4, 5, 6, 7} for value in sets)
            with driver.grader_slot(0):
                try:
                    driver.grader_slot(0)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError('Shared grader lease was not exclusive')
            checks.append('four_disjoint_Deep_lanes_shared_exclusive_locks_and_separate_Qwen_CPUs')
            with patch.object(driver, 'existing_report', return_value=None), patch.object(driver, 'host_capacity', return_value={'admit': False}), patch.object(driver.subprocess, 'Popen') as spawned:
                result = driver.process_item(item, {'plan': 'fixture'}, None)
                assert result['status'] == 'resource_wait' and not (folder / 'result.json').exists()
                assert not (folder / 'started.json').exists()
                spawned.assert_not_called()
            with patch.object(driver, 'existing_report', return_value=None), patch.object(driver, 'host_capacity', return_value={'admit': True}), driver.grader_slot(0), patch.object(driver.subprocess, 'Popen') as spawned:
                result = driver.process_item(item, {'plan': 'fixture'}, None)
                assert result['status'] == 'resource_wait' and not (folder / 'result.json').exists()
                assert not (folder / 'started.json').exists()
                spawned.assert_not_called()
            checks.append('memory_or_shared_slot_wait_writes_no_final_result_and_consumes_no_attempt')
            write_new(folder / 'started.json', {'permanent_intent': True})
            with patch.object(driver, 'existing_report', return_value=None), patch.object(driver.subprocess, 'Popen') as spawned:
                result = driver.process_item(item, {'plan': 'fixture'}, None)
                assert result['additional_attempts'] == 1 and result['status'] == 'preserved_technical_unknown'
                spawned.assert_not_called()
            checks.append('durable_attempt_intent_prevents_every_automatic_second_replay')
            with patch.object(driver, 'process_item', side_effect=RuntimeError('synthetic endpoint failure')):
                result = driver.safe_process_item(item, {'plan': 'fixture'}, None)
                assert result['error']['type'] == 'RuntimeError' and result['no_automatic_replay'] is True
            checks.append('unexpected_endpoint_errors_cannot_cancel_other_lanes')
    print(json.dumps({'version': driver.VERSION, 'passed': True, 'checks': checks,
        'model_calls': 0, 'Docker_calls': 0, 'test_executions': 0, 'original_records_modified': False}, indent=2))


if __name__ == '__main__':
    main()
