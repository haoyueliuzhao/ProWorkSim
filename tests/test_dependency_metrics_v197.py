import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('v197metrics',Path(__file__).resolve().parents[1]/'tools/score_dependency_annotations_v197.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_uncertainty_not_silently_negative_and_degenerate_agreement_not_pass():
    x=m.agreement([('useful','irrelevant'),('uncertain','essential')])
    assert x['known_binary_items']==1 and x['uncertain_items_excluded']==1
    assert x['essential_binary_cohen_kappa'] is None
    assert m.agreement([('essential','essential'),('useful','irrelevant')])['essential_binary_cohen_kappa']==1

def test_no_necessary_items_and_no_selected_items_are_not_perfect_recall_precision():
    x=m.point_metrics({'a':'useful'},[],set())
    assert x['essential_recall'] is None and x['evidence_precision_lower'] is None
    x=m.point_metrics({'a':'essential','b':'uncertain','c':'irrelevant'},['a','b'],{'a'})
    assert x['essential_recall']==1 and x['evidence_precision_lower']==.5 and x['evidence_precision_upper']==1
    assert x['critical_failure_recall']==1 and x['irrelevant_selected']==0
