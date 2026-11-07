"""Actual saved score receipts, read-only CPU reuse; never rerun a grader."""
import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim.software_benchmark_candidates_v054 import reference


def module():
    path=Path(__file__).parents[1]/'tools/watch_same_tree_scoring_v151.py'
    spec=importlib.util.spec_from_file_location('same_tree151_cpu',path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('index,expected',[(10209,True),(10203,False)])
def test_existing_known_code_result_reuses_delivery_without_another_container(index,expected):
    mod=module()
    row=next(r for r in mod.scoring.load(reference(mod.scoring.PLAN))['rows'] if r['slot_index']==index)
    ref=reference(mod.ROOT/f'runs/software-benchmark-v149/closed-export-recovery-r1/{index}/recovery-result.json')
    code=mod.existing_attempts(row,'code')[0]
    value=mod.reuse_same_tree(row,ref,code)
    assert value['resolved'] is expected
    assert value['new_containers']==0 and value['new_model_calls']==0
    assert value['historical_additional_delivery_scores']
    assert value['state']=='same_tree_official_result_reused'


def test_a_different_official_receipt_cannot_supply_the_delivery_result():
    mod=module()
    rows=mod.scoring.load(reference(mod.scoring.PLAN))['rows']
    row=next(r for r in rows if r['slot_index']==10209)
    other=next(r for r in rows if r['slot_index']==10203)
    ref=reference(mod.ROOT/'runs/software-benchmark-v149/closed-export-recovery-r1/10209/recovery-result.json')
    code=copy.deepcopy(mod.existing_attempts(row,'code')[0])
    code['receipt']=mod.existing_attempts(other,'code')[0]['receipt']
    with pytest.raises(ValueError,match='exact official'):
        mod.reuse_same_tree(row,ref,code)
