"""The1724 exception cannot silently relabel tests or forgive other failures."""
from copy import deepcopy
from pathlib import Path
import json

import pytest
from proworksim import software_benchmark_requests1724_qualification_v164 as q


@pytest.fixture(scope='module')
def controls():
    instance=next(row for row in json.loads(q.DATASET.read_bytes()) if row['instance_id']==q.TASK)
    reports={}
    for kind in ('gold','empty'):
        folder=q.control_scope.GRADING_ROOT/('control-'+q.TASK+'-'+kind)
        reports[kind]=json.loads(next(folder.rglob('report.json')).read_bytes())[q.TASK]
    return instance,reports['gold'],reports['empty']


def test_only_actual_official_added_regression_discriminates_without_relabeling(controls):
    instance,gold,empty=deepcopy(controls)
    before=deepcopy((instance,gold,empty))
    proof=q.validate_discriminating_reports(instance,gold,empty)
    assert proof['gold_official_resolved'] is True and proof['empty_official_resolved'] is False
    assert proof['target_original_group']=='PASS_TO_PASS'
    assert proof['official_groups_unchanged'] is True
    assert (instance,gold,empty)==before


@pytest.mark.parametrize('change',['gold_failure','empty_success','extra_failure','F2P_failure','relabel','missing_patch_addition'])
def test_exception_rejects_every_other_outcome_or_metadata_change(controls,change):
    instance,gold,empty=deepcopy(controls)
    if change=='gold_failure':gold['resolved']=False
    elif change=='empty_success':empty['resolved']=True
    elif change=='extra_failure':empty['tests_status']['PASS_TO_PASS']['failure'].append(instance['PASS_TO_PASS'][0])
    elif change=='F2P_failure':empty['tests_status']['FAIL_TO_PASS']['failure'].append(instance['FAIL_TO_PASS'][0])
    elif change=='relabel':instance['FAIL_TO_PASS'].append(q.TARGET)
    elif change=='missing_patch_addition':instance['test_patch']=instance['test_patch'].replace('def test_unicode_method_name(self):','def different_test(self):')
    with pytest.raises(ValueError):q.validate_discriminating_reports(instance,gold,empty)
