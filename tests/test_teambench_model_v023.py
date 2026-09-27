"""Explicit CPU model-transport fixtures: never actual model evaluation data."""
from pathlib import Path

import pytest

from proworksim.teambench_isolation_v022 import facility_probe
from proworksim.teambench_model_v023 import run_episode
from scripts.teambench_model_v023 import ExplicitFakeOwner

ASSETS = Path('runs/teambench-v022-os-isolation-verified')


@pytest.mark.parametrize('variant', ['correct', 'forged_pass', 'string_only', 'wrong_pipeline'])
def test_real_tools_and_fixed_grader_keep_actual_verification_separate(tmp_path, variant):
    if not ASSETS.exists() or not facility_probe()['available']:
        pytest.skip('Previously pinned D2 fixture and existing OS isolation required')
    owner = ExplicitFakeOwner(variant)
    result = run_episode(owner, ASSETS / 'generated/seed0',
                         ASSETS / 'reviewed-source/tasks/D2_data_quality/grade.sh', tmp_path / variant, seed=0)
    evidence = result['responsibility']
    assert result['grader']['status'] == 'graded'
    assert result['grader']['pipeline_rerun_isolated']
    assert evidence['explicit_fixed_submission'] and evidence['fixed_workspace_unchanged']
    assert evidence['full_joint_responsibility'] is (variant == 'correct')
    assert evidence['supported_attestation'] is (variant in {'correct', 'wrong_pipeline'})
    assert evidence['verifier_computation_executed'] is (variant in {'correct', 'wrong_pipeline'})
    assert result['grader']['score']['pass'] is (variant != 'wrong_pipeline')
    if variant in {'forged_pass', 'string_only'}:
        assert evidence['unsupported_pass']  # Native grade pass is insufficient.
    elif variant == 'wrong_pipeline':
        assert evidence['formal_attestation']['verdict'] == 'fail'
    assert len(owner.requests) == (8 if variant == 'forged_pass' else 13)
    assert all('expected.json' not in str(request) for request in owner.requests)


def test_external_comparison_preserves_missing_pair_and_declared_denominator():
    from proworksim.teambench_model_v023 import SEEDS, VERSION, compare_checkpoints
    first = {'version': VERSION, 'checkpoint': 'initial', 'seeds': list(SEEDS), 'episodes': []}
    final = {'version': VERSION, 'checkpoint': 'final', 'seeds': list(SEEDS), 'episodes': []}
    for seed in SEEDS:
        row = {'seed': seed, 'case_identity': {'fixture': seed}, 'responsibility': {'full_joint_responsibility': False}}
        first['episodes'].append(row)
        if seed != SEEDS[-1]:
            final['episodes'].append({**row, 'responsibility': {'full_joint_responsibility': True}})
    result = compare_checkpoints(first, final)
    assert result['known_pairs'] == 2 and result['mean_full_responsibility_difference'] is None
    assert result['unknown_compatible_bounds'] == [1/3, 1.0]
    assert result['pairs'][-1]['final'] is None
