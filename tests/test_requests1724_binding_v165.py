"""Reuse qualified evidence with new authority; no new Docker/network/model IO."""
from copy import deepcopy
from pathlib import Path
from types import ModuleType,SimpleNamespace

import pytest

from proworksim import software_benchmark_requests1724_binding_v165 as binding
from proworksim import software_benchmark_requests1724_v162 as original
from proworksim import software_benchmark_requests1724_qualification_v164 as qualification
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def policy(tmp_path):
    file=tmp_path/'new_candidate_scope.py';file.write_text('# CPU-only new six-session policy; grants no real IO.\n')
    calls=[]
    value=SimpleNamespace(__file__=str(file),BATCH_ROOT=tmp_path,
        CONSTRAINTS={**binding.EXPECTED_NETWORK_LIMITS,'requests_private_capability_tasks':[binding.TASK]},
        require_v066_allowed=lambda *a,**kw:calls.append((a,kw)))
    return value,reference(file),calls


def control_config():
    plan_ref=reference(binding.SOURCE_SCOPE.PLAN_FILE)
    plan=binding._load(plan_ref)
    return binding._load(plan['environments'][binding.TASK]['configuration']),plan_ref


def test_new_authority_old_probe_are_explicit_and_original_globals_untouched(tmp_path):
    new,scope,calls=policy(tmp_path)
    old_validator=original.frozen.validate_resolution
    environment=binding.environment_for(new,scope_ref=scope,directory=tmp_path/'bindings')
    assert environment.__file__==binding.__file__
    assert environment.tls.__file__==original.__file__
    fields=environment.request_fields(binding.TASK)
    bridge=binding._load(fields['network_resolution'])
    assert bridge['scope']==scope and bridge['source_probe_scope']==reference(binding.SOURCE_SCOPE.__file__)
    assert bridge['new_network_probe'] is False and bridge['new_DNS_lookup'] is False
    assert bridge['source_control_authority_reopened'] is False
    manifest=binding._load(fields['environment_revision'])
    source=binding._load(binding._verified_source()['environment_ref'])
    assert {k for k in source if source[k]!=manifest[k]}==binding.ADMINISTRATIVE_FIELDS
    assert original.frozen.validate_resolution is old_validator
    assert original.validate_transport_evidence.__globals__['frozen'].validate_resolution is old_validator
    assert environment.validate_transport_evidence.__globals__['frozen'].validate_resolution is binding.validate_bridge
    assert calls==[]
    environment.tls.transport._authorize(binding.TASK)
    assert calls==[(('v066.transport',),{'instance_id':binding.TASK})]
    config,_=control_config()
    proof=environment.verify_qualified_reuse(config)
    assert proof['passed'] and proof['original_controls_revalidated']
    assert proof['source_authority_reopened'] is False and proof['new_probe_claimed'] is False
    assert proof['candidate_score_must_use_own_run_and_patch_identity']


def test_changed_ip_permissions_CA_profile_or_target_config_is_not_administrative(tmp_path):
    new,scope,_=policy(tmp_path)
    environment=binding.environment_for(new,scope_ref=scope,directory=tmp_path/'bindings')
    fields=environment.request_fields(binding.TASK)
    bridge=binding._load(fields['network_resolution']);bridge['selected_ip']='8.8.8.8'
    bad=write_new(tmp_path/'bad-bridge.json',bridge)
    with pytest.raises(ValueError,match='changed scope'):
        binding.validate_bridge(bad,scope_ref=scope,expected_source=binding.REUSE_SOURCE)
    config,_=control_config()
    manifest=binding._load(fields['environment_revision'])
    for key,value in [('cap_add',['NET_ADMIN','NET_BIND_SERVICE']),('effective_CA_changed',False),('listen_ports',[80])]:
        changed=deepcopy(manifest);changed[key]=value
        with pytest.raises(ValueError,match='more than scope'):
            binding.verify_qualified_reuse(changed,config)
    wrong=deepcopy(config);wrong['scorer_request_base']['image']['image_id']='sha256:'+'0'*64
    with pytest.raises(ValueError,match='Candidate task/image'):
        binding.verify_qualified_reuse(fields['environment_revision'],wrong)


def test_six_session_budget_and_foreign_task_guard_cannot_expand(tmp_path):
    new,scope,_=policy(tmp_path)
    new.CONSTRAINTS['maximum_real_tls_sessions']=7
    with pytest.raises(ValueError,match='six1724'):
        binding.environment_for(new,scope_ref=scope,directory=tmp_path/'bindings')
    new.CONSTRAINTS['maximum_real_tls_sessions']=6
    new.CONSTRAINTS['requests_private_capability_tasks'].append('other-task')
    with pytest.raises(ValueError,match='Only1724'):
        binding.environment_for(new,scope_ref=scope,directory=tmp_path/'bindings')


def test_private_scorer_requires_identical_router_in_actual_create_attrs_and_score(tmp_path):
    new,scope,_=policy(tmp_path)
    environment=binding.environment_for(new,scope_ref=scope,directory=tmp_path/'bindings')
    private={'environment':environment}
    exec('def score_request(): return environment\ndef validate_attrs(): return environment\nclass Containers:\n def create(self): return environment\n',private)
    scorer=ModuleType('cpu_private_candidate_scorer')
    for key in ('score_request','validate_attrs','Containers'):setattr(scorer,key,private[key])
    scorer.environment=environment
    scorer.validate_qualification=lambda *a:None
    binding.bind_qualification(scorer)
    config,plan=control_config()
    proof=scorer.validate_qualification(reference(qualification.OVERLAY_FILE),config,plan)
    assert proof['passed'] and proof['new_authority_not_old_control_grant']
    scorer.environment=SimpleNamespace()
    with pytest.raises(ValueError,match='same private1724 router'):
        binding.bind_qualification(scorer)
