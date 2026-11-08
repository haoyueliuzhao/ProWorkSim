"""Administrative binding of qualified1724 scoring to a new candidate scope.

The v162 provider, CA material and original real endpoint probe are immutable.
Only scope/resolution provenance is rebound, explicitly as reuse rather than a
new probe. Actual relay authorization always calls the supplied new policy;
this module grants no Docker/network permission and performs no network IO.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import FunctionType,SimpleNamespace

from . import software_benchmark_requests1724_v162 as original
from . import software_benchmark_requests1724_qualification_v164 as qualification
from . import software_benchmark_environment_v141 as original_frozen
from .software_benchmark_candidates_v054 import reference,checked
from .software_benchmark_grading_v105 import environment_identity

VERSION='v165-qualified1724-new-scope-endpoint-reuse-r1'
TASK=original.TASK
REUSE_SOURCE='v165_verified_v162_endpoint_reuse_no_new_probe'
ADMINISTRATIVE_FIELDS=frozenset({'scope','network_resolution','resolution_source'})
SOURCE_SCOPE=qualification.control_scope
EXPECTED_NETWORK_LIMITS={
    'maximum_real_tls_sessions':6,'real_tls_session_connections':512,
    'real_tls_session_payload_bytes':64*1024**2,'real_tls_all_sessions_connections':3072,
    'real_tls_all_sessions_payload_bytes':384*1024**2,
}


def _load(ref):return original._load(ref)


def _retain(path,value):
    try:return original_frozen._retain(path,value)
    except FileExistsError:
        ref=reference(path)
        if _load(ref)!=value:raise ValueError('Concurrent preparation changed frozen1724 bindings')
        return ref


def _clone(function,namespace):
    value=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value


def _verified_source():
    resolution_ref=reference(SOURCE_SCOPE.RESOLUTION_FILE)
    source_scope=reference(SOURCE_SCOPE.__file__)
    source=_load(resolution_ref)
    original_frozen.validate_resolution(resolution_ref,scope_ref=source_scope,
        expected_source='v162_current_DNS_and_bounded_endpoint_probe')
    probe=_load(source['diagnostic'])
    overlay=_load(reference(qualification.OVERLAY_FILE))
    if (overlay.get('version')!=qualification.VERSION or overlay.get('passed') is not True
            or overlay.get('instance_id')!=TASK or overlay.get('network_resolution')!=resolution_ref):
        raise ValueError('The endpoint must belong to the independently qualified1724 controls')
    return {'scope':source_scope,'resolution_ref':resolution_ref,'resolution':source,
            'probe':probe,'qualified_overlay':reference(qualification.OVERLAY_FILE),
            'environment_ref':overlay['environment_revision']}


def _policy(policy,scope_ref):
    checked(scope_ref)
    if (not callable(getattr(policy,'require_v066_allowed',None))
            or not getattr(policy,'__file__',None) or reference(policy.__file__)!=scope_ref
            or scope_ref==reference(SOURCE_SCOPE.__file__)):
        raise ValueError('Use the exact new candidate policy, not the consumed control authority')
    constraints=getattr(policy,'CONSTRAINTS',{})
    if any(constraints.get(key)!=value for key,value in EXPECTED_NETWORK_LIMITS.items()):
        raise ValueError('The new scope must explicitly bound six1724 candidate sessions to3072 connections/384MiB')
    if constraints.get('requests_private_capability_tasks')!=[TASK]:
        raise ValueError('Only1724 may obtain this new scope\'s private networking capability')
    return constraints


def bridge_value(scope_ref):
    checked(scope_ref);source=_verified_source();old=source['resolution']
    return {'version':VERSION,'source':REUSE_SOURCE,'scope':scope_ref,'instance_id':TASK,
        'hostname':old['hostname'],'ports':copy.deepcopy(old['ports']),
        'ipv4':copy.deepcopy(old['ipv4']),'selected_ip':old['selected_ip'],'automatic_retry':False,
        'diagnostic':old['diagnostic'],'source_probe_scope':source['scope'],
        'source_resolution':source['resolution_ref'],'source_qualified_overlay':source['qualified_overlay'],
        'source_probe_finished_unix':source['probe'].get('finished_unix'),
        'new_DNS_lookup':False,'new_network_probe':False,'old_probe_rewritten':False,
        'source_control_authority_reopened':False,'new_authority_must_be_supplied_separately':True,
        'TCP_destination_and_limits_changed':False,'TLS_and_CA_material_changed':False}


def validate_bridge(resolution_ref,*,scope_ref,expected_source):
    if expected_source!=REUSE_SOURCE or _load(resolution_ref)!=bridge_value(scope_ref):
        raise ValueError('1724 endpoint-reuse bridge changed scope, original probe, IP or ports')
    return _load(resolution_ref)


def _profile_equivalence(new_manifest):
    value=_load(new_manifest) if isinstance(new_manifest,dict) and set(new_manifest)=={'path','bytes','sha256'} else copy.deepcopy(new_manifest)
    source=_verified_source();old=_load(source['environment_ref'])
    if not isinstance(value,dict) or set(value)!=set(old):
        raise ValueError('Only the original qualified1724 profile shape is admitted')
    bridge=validate_bridge(value['network_resolution'],scope_ref=value['scope'],expected_source=value['resolution_source'])
    changed={key for key in value if value[key]!=old[key]}
    if changed-ADMINISTRATIVE_FIELDS or any(value[key]!=old[key] for key in set(old)-ADMINISTRATIVE_FIELDS):
        raise ValueError('The candidate environment changed more than scope/resolution administrative provenance')
    if value['adapter']!=reference(original.__file__):
        raise ValueError('The actual tested provider implementation must remain byte-identical')
    return {'version':VERSION,'passed':True,'instance_id':TASK,'scope_binding_adapter':reference(__file__),
        'qualified_overlay':source['qualified_overlay'],'source_environment_manifest':source['environment_ref'],
        'new_environment_manifest':new_manifest if set(new_manifest)=={'path','bytes','sha256'} else None,
        'administrative_fields_changed':sorted(changed),
        'allowed_administrative_fields':sorted(ADMINISTRATIVE_FIELDS),
        'same_provider_code_CA_permissions_tests_limits':True,
        'endpoint_reuse_bridge':value['network_resolution'],'new_scope':value['scope'],
        'source_probe_scope':bridge['source_probe_scope'],'new_probe_claimed':False,
        'source_authority_reopened':False,'new_policy_guard_required':True,
        'new_Docker_operations':0,'new_network_connections':0,'new_model_calls':0,
        'score_cache_reuse':False,'candidate_score_must_use_own_run_and_patch_identity':True}


def verify_qualified_reuse(new_manifest,config):
    """Read-only provenance/actual-control proof for one future candidate config."""
    proof=_profile_equivalence(new_manifest)
    evidence=qualification.build_evidence()
    if (_load(reference(qualification.EVIDENCE_FILE))!=evidence
            or _load(reference(qualification.OVERLAY_FILE))!=qualification.qualified_overlay(evidence)):
        raise ValueError('The original gold/empty task-specific qualification changed')
    if config.get('instance_id')!=TASK or environment_identity(config)!=evidence['actual_environment_identity']:
        raise ValueError('Candidate task/image/dataset/baseline/official-scoring inputs differ from qualified controls')
    return {**proof,'target_environment_identity':environment_identity(config),
            'original_controls_revalidated':True,'official_score_rule_or_test_groups_changed':False}


def environment_for(policy,*,scope_ref,directory,resolution_bridge_ref=None):
    """Pure preparation of a new private provider/router; no grant is consumed."""
    _policy(policy,scope_ref)
    directory=Path(directory).resolve()
    if directory.is_relative_to(SOURCE_SCOPE.BATCH_ROOT.resolve()):
        raise ValueError('Never write new candidate bindings into the historical control run')
    if getattr(policy,'BATCH_ROOT',None) is not None and not directory.is_relative_to(Path(policy.BATCH_ROOT).resolve()):
        raise ValueError('New bindings must stay within the supplied candidate policy\'s batch')
    if resolution_bridge_ref is None:
        resolution_bridge_ref=_retain(directory/'endpoint-reuse-bridge.json',bridge_value(scope_ref))
    validate_bridge(resolution_bridge_ref,scope_ref=scope_ref,expected_source=REUSE_SOURCE)
    private_frozen=SimpleNamespace(**{**vars(original.frozen),'validate_resolution':validate_bridge,'_retain':_retain})
    namespace={**vars(original),'frozen':private_frozen}
    namespace['validate_transport_evidence']=_clone(original.validate_transport_evidence,namespace)
    factory=_clone(original.cold_environment,namespace)
    environment=factory(policy,scope_ref=scope_ref,directory=directory/'provider',
        resolution_ref=resolution_bridge_ref,resolution_source=REUSE_SOURCE)
    prepared=environment.prepare()
    fields=environment.request_fields(TASK)
    equivalence=_retain(directory/'qualified-profile-equivalence.json',_profile_equivalence(fields['environment_revision']))
    # The router is new; its underlying per-container provider remains the
    # exact tested v162 implementation. Official manifests retain both sources.
    environment.__file__=__file__
    environment.binding_revision=VERSION
    environment.resolution_bridge=resolution_bridge_ref
    environment.qualified_profile_equivalence=equivalence
    environment.provider_bindings=prepared
    environment.verify_qualified_reuse=lambda config:verify_qualified_reuse(fields['environment_revision'],config)
    return environment


def bind_qualification(existing):
    """New private scorer integration; no running module globals are changed."""
    if sys.modules.get(getattr(existing,'__name__',None)) is existing:
        raise ValueError('Only a newly constructed private scorer can receive this overlay')
    namespace=existing.score_request.__globals__;environment=existing.environment
    if (namespace.get('environment') is not environment
            or existing.Containers.create.__globals__.get('environment') is not environment
            or existing.validate_attrs.__globals__.get('environment') is not environment):
        raise ValueError('Actual candidate create/attrs/score globals must share the same private1724 router')
    original_validate=existing.validate_qualification
    def validate(ref,config,plan_ref):
        if config.get('instance_id')!=TASK or _load(ref).get('version')!=qualification.VERSION:
            return original_validate(ref,config,plan_ref)
        original_proof=qualification.validate_qualification(ref,config,plan_ref)
        fields=environment.request_fields(TASK)
        proof=verify_qualified_reuse(fields['environment_revision'],config)
        return {**original_proof,'candidate_environment_revision':fields['environment_revision'],
                'candidate_network_resolution':fields['network_resolution'],
                'candidate_environment_equivalence':proof,'new_authority_not_old_control_grant':True}
    namespace['validate_qualification']=validate
    existing.validate_qualification=validate
    return existing
