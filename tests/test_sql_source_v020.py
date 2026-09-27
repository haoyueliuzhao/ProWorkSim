"""CPU source admission; never launch a model or execute upstream Python tests."""
import copy
from pathlib import Path

import pytest

from proworksim.sql_source_v020 import CASES, PINS, public_task, task
from scripts.sql_source_experiment_v020 import main

ASSETS = Path('runs/assets/sql-v020')


@pytest.fixture
def assets():
    if not all((ASSETS / name / pin['file']).exists() for name, pin in PINS.items()):
        pytest.skip('Pinned external SQLite source files have not been downloaded')
    return ASSETS


def test_public_projection_does_not_publish_executable_tests_or_reference(assets):
    row = copy.deepcopy(task(assets, CASES[0]))
    row['sol_sql'] = ['PRIVATE_REFERENCE_CANARY']
    row['test_cases'] = ["raise RuntimeError('PRIVATE_TEST_MUST_NOT_EXECUTE')"]
    visible = public_task(row)
    assert set(visible) == {'instance_id', 'db_id', 'dialect', 'version', 'category', 'query', 'issue_sql'}
    assert 'PRIVATE_' not in str(visible)
    visible['issue_sql'].append('changed by reader')
    assert len(row['issue_sql']) == 1
    with pytest.raises(ValueError, match='predeclared'):
        task(assets, 'TRAIN_120')


def test_source_sqlite_and_world_build_controls_preserve_negative_results(assets, tmp_path):
    report = main(assets, tmp_path / 'run')
    assert report['all_controls_pass'] and report['database_unchanged']
    assert report['model_calls'] == report['training_examples'] == report['parameter_updates'] == 0
    assert report['official_python_tests_executed'] is False
    overlap = report['lineage']['overlap']
    assert overlap['database_ids'] == overlap['published_sqlite_sha256'] == []
    assert overlap['query_and_issue_normalized_exact_matches'] == 3
    assert len(overlap['query_and_issue_pairs']) == 5
    assert [row['instance_id'] for row in report['cases']] == list(CASES)
    for row in report['cases']:
        assert row['passed'] and all(row['checks'].values())
        assert row['managed']['copied_correct_product_without_build']['independent_rows_match']
        assert not row['managed']['copied_correct_product_without_build']['real_sql_build']
        assert not row['managed']['wrong_valid']['passed']
        assert row['managed']['wrong_valid']['execution_status'] == 'success'
        assert row['source_adoption']['version_id'] == 'v1'
    grouped = next(row for row in report['cases'] if row['instance_id'] == 'TRAIN_303')
    assert grouped['native']['original_issue']['status'] == 'success'
    assert grouped['native']['original_issue']['rows'] == 1
    assert grouped['managed']['original_issue']['execution_status'] == 'execution_error'
    assert grouped['managed']['original_issue']['error']['type'] == 'BinderException'
    with pytest.raises(FileExistsError):
        main(assets, tmp_path / 'run')
