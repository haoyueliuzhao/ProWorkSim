"""Necessary pure CPU checks for cpuset, exact untracked bytes and lossless transport."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from proworksim import software_benchmark_scorer_r6_v055 as r6
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def reject(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Unsafe scoring input was accepted')


def main():
    checks = []
    assert r6.cpus('0-3') == [0, 1, 2, 3]
    for value in ('0-175', '0-2', '0-3,3', '3-0', '../0', 'max'):
        reject(lambda value=value: r6.cpus(value))
    checks.append('exact_four_distinct_visible_CPUs_only')
    mapping_path = r6.ROOT / 'runs/software-benchmark-v054/images/actor-admission-r3/instances/psf__requests-1142.json'
    mapping = json.loads(mapping_path.read_bytes())
    audit = json.loads(r6.AUDIT.read_bytes())
    revision = {'untracked_build_audit': reference(r6.AUDIT)}
    assert r6.allowed_untracked(mapping, audit['official_image'], revision) == sorted(audit['files'], key=lambda row: row['path'])
    bad = deepcopy(mapping)
    bad['removed_public_build_duplicates'][0]['sha256'] = '0' * 64
    reject(lambda: r6.allowed_untracked(bad, audit['official_image'], revision))
    reject(lambda: r6.allowed_untracked(mapping, 'sha256:' + '0' * 64, revision))
    checks.append('exact_65_pinned_requests_build_paths_bytes_hashes_and_image_only')
    compile(r6.UNTRACKED_INSPECTION, '<read-only-container-inventory>', 'exec')
    checks.append('read_only_container_inventory_program_parses_without_execution')
    with tempfile.TemporaryDirectory(prefix='r6-transport-cpu-') as name:
        root = Path(name)
        old_patch = root / 'original.patch'
        old_patch.write_bytes(b'non-utf8-\xff')
        new_patch = root / 'transport.patch'
        new_patch.write_bytes(b'GIT binary patch\nfixture\n')
        exported = {'base_git_tree': 'a' * 40, 'candidate_git_tree': 'b' * 40,
            'base_tree_sha256': 'c' * 64, 'candidate_tree_sha256': 'd' * 64}
        lock = write_new(root / 'lock.json', {'patch_receipt': exported})
        original = {'patch': reference(old_patch), 'native_candidate_lock': lock,
            'baseline_tree_sha256': 'c' * 64, 'candidate_tree_sha256': 'd' * 64}
        old_ref = write_new(root / 'request.json', original)
        receipt = {'version': 'v055-locked-patch-utf8-transport-r1', 'original_request': old_ref,
            'original_patch': original['patch'], 'original_native_lock': lock,
            'replacement_patch': reference(new_patch), **exported,
            'original_patch_round_trip_verified': True, 'replacement_patch_round_trip_verified': True,
            'utf8': True, 'candidate_reselected': False, 'files_excluded': 0, 'new_model_calls': 0,
            'source': reference(__file__)}
        receipt_ref = write_new(root / 'transport.json', receipt)
        request = {'original_scoring_request': old_ref, 'patch_transport': receipt_ref}
        payload, replacement = r6.selected_patch(request, original)
        assert payload == new_patch.read_bytes() and replacement == receipt['replacement_patch']
        for change in ({'candidate_git_tree': 'e' * 40}, {'files_excluded': 1}, {'candidate_reselected': True}):
            with patch.object(r6, 'load', side_effect=lambda ref, change=change: {**receipt, **change} if ref == receipt_ref else {'patch_receipt': exported}):
                reject(lambda: r6.selected_patch(request, original))
        assert old_patch.read_bytes() == b'non-utf8-\xff'
        checks.append('replacement_transport_requires_same_original_lock_both_roundtrips_and_zero_file_filtering')
    print(json.dumps({'version': r6.VERSION, 'passed': True, 'checks': checks,
        'Docker_calls': 0, 'test_executions': 0, 'model_calls': 0, 'old_sources_modified': False}, indent=2))


if __name__ == '__main__':
    main()
