"""Task/member accounting stays hierarchical in the organization summary."""
import importlib.util
import json
from pathlib import Path

from proworksim.software_benchmark_alignment_contract_v131 import condition
from proworksim.software_benchmark_candidates_v054 import write_new


def test_members_share_one_team_cost_and_no_missing_score_is_a_failure(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('v131_summary_CPU', root/'tools/summarize_fixed_organization_v131.py')
    summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary)
    monkeypatch.setattr(summary.scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(summary.scope, 'GRADING_ROOT', tmp_path/'grading')
    condition_value = condition('REVIEW')
    row = {'slot_id': 'v131:fixture__repo-1:'+condition_value['condition_id']+':1',
        'slot_index': 9000, 'instance_id': 'fixture__repo-1', 'organization_id': 'REVIEW',
        'group_id': 'REVIEW', 'arm': 'PROJECT', 'execution_arm': 'PROJECT', 'seed': 1,
        'fixed_members': condition_value['fixed_members'], 'condition_id': condition_value['condition_id'],
        'configuration': write_new(tmp_path/'config.json', {'CPU_fixture': True})}
    folder = tmp_path/'episodes/9000'
    folder.mkdir(parents=True)
    write_new(folder/'result.json', {'slot_id':row['slot_id'],'configuration':row['configuration'],
        'status':'closed','delivery_validation':{'submitted':False}})
    records = []
    for member, total in [('member_001', 20), ('member_002', 30)]:
        records.append({'slot_id':row['slot_id'],'condition':row['condition_id'],'group_id':'REVIEW',
            'member_id':member,'usage_id':'agent','status':'settled',
            'usage':{'prompt_tokens':total-2,'completion_tokens':2,'total_tokens':total},
            'settled_nanoyuan':100,'reserved_nanoyuan':1000})
    observed = summary.outcome(row, {}, records, True)
    assert observed['known_token_totals']['total_tokens'] == 50
    assert observed['by_member']['member_001']['total_tokens'] == 20
    assert observed['by_member']['member_002']['total_tokens'] == 30
    assert observed['team_budget_tokens'] == 5_000_000 and observed['usage_complete'] is True
    assert observed['code']['resolved'] is None and observed['code']['state'] == 'not_scored'
    assert observed['known_settled_nanoyuan'] == 200
    assert json.loads((folder/'result.json').read_bytes())['status'] == 'closed'
