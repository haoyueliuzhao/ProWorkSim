import copy

import pytest

from proworksim.study_design_v020 import build_design, source_partition_audit, validate_design


def test_dense_window_is_proposal_not_admission_or_observed_support():
    d = build_design()
    assert validate_design(d)['train'] == 96
    assert len(d['P2']['evaluation_per_endpoint']) == 24
    assert all(w['observed_valid_classes'] is None for w in d['P2']['windows'])
    assert d['launchable'] is d['resource_approved'] is False
    mutated = copy.deepcopy(d)
    mutated['P2']['windows'][0]['slots'].pop()
    with pytest.raises(ValueError):
        validate_design(mutated)


def test_transitive_source_alias_and_ancestor_cannot_cross_purposes():
    rows = [
        {'asset_id': 'train', 'purpose': 'policy_training', 'database_sha256': ['db'], 'lineage_review': 'complete', 'evidence': ['pin']},
        {'asset_id': 'alias', 'purpose': 'policy_training', 'database_sha256': ['db'], 'ancestor_task': ['ancestor'], 'lineage_review': 'complete', 'evidence': ['pin']},
        {'asset_id': 'external', 'purpose': 'locked_evaluation', 'ancestor_task': ['ancestor'], 'lineage_review': 'complete', 'evidence': ['pin']},
    ]
    audit = source_partition_audit(rows)
    assert not audit['admitted']
    assert len(audit['components']) == 1
    assert audit['cross_purpose_conflicts'][0]['asset_ids'] == ['alias', 'external', 'train']


def test_missing_provenance_is_unresolved_not_independent_source():
    row = {'asset_id': 'new-name', 'purpose': 'locked_evaluation'}
    assert source_partition_audit([row])['unresolved_assets'] == ['new-name']
    with pytest.raises(ValueError):
        source_partition_audit([row, row])
