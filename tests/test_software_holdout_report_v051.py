"""New report arithmetic controls: original denominators and paired missingness."""
import pytest

from scripts.software_holdout_v051_report import CONDITIONS, bounded, paired


def test_missing_fixed_task_does_not_disappear_or_become_zero():
    tasks = [str(i) for i in range(8)]
    rows = [{'task_id': task, 'condition': condition, 'F': int(condition == 'B')}
            for task in tasks for condition in CONDITIONS]
    complete = paired(rows, 'B', 'S_star', 'F', tasks)
    assert complete['mean'] == 1 and complete['bounds'] == [1, 1]
    for row in rows:
        if row['task_id'] == '0':
            row['F'] = None
    missing = paired(rows, 'B', 'S_star', 'F', tasks)
    assert missing['mean'] is None and missing['known_pairs'] == 7
    assert missing['denominator'] == 8 and missing['bounds'] == [.75, 1]
    mean = bounded([None] + [1] * 7)
    assert mean == {'denominator': 8, 'known': 7, 'unknown': 1, 'mean': None, 'bounds': [.875, 1]}
    with pytest.raises(ValueError, match='every task'):
        paired(rows[4:], 'B', 'S_star', 'F', tasks)
