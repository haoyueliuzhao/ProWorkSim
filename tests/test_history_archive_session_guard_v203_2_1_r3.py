"""Frozen SSH master, stable session class and exact PAM negative controls."""
import copy
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def module():
 p=ROOT/'tools/archive_passive_pilot_history_v203_2_1_r3.py';spec=importlib.util.spec_from_file_location('archive_session_guard_r3',p)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_reviewed_and_new_standard_session_with_same_frozen_master(module):
 policy=module.validated_witness();master=policy['ssh_master']
 for w in policy['observed_ssh_examples']:
  e=module.decide_process(w['process'],w['parent'],[('cwd','/')],['fd-directory'],['/history'],policy,1021,master=master)
  assert e['ssh_master']==master and e['excluded_fields_not_proven_free_of_history_references']
 # Class supports another authenticated session only with a root sshd parent,
 # same session scope and the unchanged root master identity.
 w=copy.deepcopy(policy['observed_ssh_examples'][1]);w['process'].update(pid=3000001,ppid=3000000,starttime_ticks=950000002)
 w['parent'].update(pid=3000000,starttime_ticks=950000001)
 assert module.exact_exclusion(w['process'],w['parent'],policy,1021,master=master)
 pam=policy['pam_helper'];assert module.exact_exclusion(pam['process'],pam['parent'],policy,1021)


def test_unknown_worker_root_master_reuse_and_weakened_parent_evidence_rejected(module):
 policy=module.validated_witness();original=policy['observed_ssh_examples'][1]
 for target,key,value in [('process','uid_vector',[1021,0,1021,1021]),('process','name','python'),
  ('process','comm','worker'),('process','cgroup',['0::/user.slice/user-1021.slice/experiment.scope']),
  ('parent','uid_vector',[1021]*4),('parent','name','python'),('parent','comm','python'),
  ('parent','ppid',999999),('parent','starttime_ticks',original['process']['starttime_ticks'])]:
  w=copy.deepcopy(original);w[target][key]=value
  with pytest.raises(PermissionError,match='Unreviewed unreadable'):
   module.decide_process(w['process'],w['parent'],[],['maps'],['/history'],policy,1021,master=policy['ssh_master'])
 for key,value in [('pid',999),('starttime_ticks',1),('comm','python'),('uid_vector',[1021]*4)]:
  master={**policy['ssh_master'],key:value}
  assert module.exact_exclusion(original['process'],original['parent'],policy,1021,master=master) is None
 pam=copy.deepcopy(policy['pam_helper']);pam['parent']['starttime_ticks']+=1
 assert module.exact_exclusion(pam['process'],pam['parent'],policy,1021) is None


def test_readable_history_reference_always_wins_over_helper_exclusion(module):
 policy=module.validated_witness();w=policy['observed_ssh_examples'][0]
 with pytest.raises(PermissionError,match='Actual historical path reference'):
  module.decide_process(w['process'],w['parent'],[('fd','/history/request.json')],['maps'],['/history'],policy,1021,master=policy['ssh_master'])
 worker={'pid':5,'name':'python','uid_vector':[1021]*4}
 with pytest.raises(PermissionError,match='Unreviewed unreadable'):
  module.decide_process(worker,{},[],['fd-directory'],['/history'],policy,1021)
 assert module.decide_process(worker,{},[('cwd','/other')],[],['/history'],policy,1021) is None
