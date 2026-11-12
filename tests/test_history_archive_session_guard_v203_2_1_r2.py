"""Pure exact-process classification controls; no live archival operations."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def module():
    p=ROOT/'tools/archive_passive_pilot_history_v203_2_1_r2.py'
    spec=importlib.util.spec_from_file_location('archive_session_guard_r2',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_two_exact_witnesses_only_exclude_unreadable_fields(module):
    rows=module.validated_witness()
    for witness in rows:
        decision=module.decide_process(witness['process'],witness['parent'],
            [('cwd','/'),('fd','socket:[synthetic]')],['exe','fd-directory'],['/historical/ledger'],rows,1021)
        assert decision['denied_fields']==['exe','fd-directory']
        assert decision['excluded_fields_not_proven_free_of_history_references'] is True
        assert decision['readable_fields_still_checked']==2


def test_pid_reuse_uid_cgroup_name_and_parent_changes_are_not_exempt(module):
    rows=module.validated_witness();w=rows[0]
    for target,key,value in [('process','pid',999999),('process','starttime_ticks',1),
        ('process','uid_vector',[1021,0,1021,1021]),('process','name','python'),
        ('process','cgroup',['0::/user.slice/user-1021.slice/experiment.scope']),
        ('parent','comm','python'),('parent','starttime_ticks',2),('parent','pid',999998)]:
        changed=copy.deepcopy(w);changed[target][key]=value
        with pytest.raises(PermissionError,match='Unreviewed unreadable'):
            module.decide_process(changed['process'],changed['parent'],[],['fd-directory'],
                ['/historical/ledger'],rows,1021)


def test_readable_historical_reference_rejected_even_for_exact_exempt_helper(module):
    rows=module.validated_witness();w=rows[1]
    with pytest.raises(PermissionError,match='Actual historical path reference'):
        module.decide_process(w['process'],w['parent'],
            [('fd','/historical/ledger/request-0001.json')],['maps'],['/historical/ledger'],rows,1021)
    # An ordinary fully readable process can pass without being on any whitelist;
    # only a denied field introduces the exact-helper classification requirement.
    worker={'pid':9,'name':'python','uid_vector':[1021]*4}
    assert module.decide_process(worker,None,[('cwd','/other')],[],['/historical/ledger'],rows,1021) is None
    with pytest.raises(PermissionError,match='Unreviewed unreadable'):
        module.decide_process(worker,None,[],['cwd'],['/historical/ledger'],rows,1021)
