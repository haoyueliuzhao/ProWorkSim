"""Pure review-shape and unauthorized-entry controls; no activation or sealing."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    from proworksim.software_benchmark_candidates_v054 import reference,write_new
    denied=[]
    def no_external(event,_args):
        if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto',
                     'subprocess.Popen','os.system','os.fork','os.posix_spawn'}:
            denied.append(event)
            raise RuntimeError('Review-shape controls cannot execute services, root tools or networking')
    sys.addaudithook(no_external)
    seal=module('seal_fixed_organization_v131')
    activate=module('activate_fixed_organization_v131')
    scope=seal.scope
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    inventory=scope.load(reference(scope.ARTIFACT_ROOT/'organization-sdk-controls-r1/member-schema-inventory.json'))
    schemas={'schemas':inventory['schemas'],'neutral_calls':0,'provider_search_or_fetch':False}
    bundle={'probe':{'organization_ids':list(scope.GROUP_IDS),'model_calls':0,
        'all_controller_and_worker_entrypoints_imported':True,'forbidden_operation_counts':{'network':0,'process':0}}}
    parent=scope.load(reference(scope.ARTIFACT_ROOT/'aggregate-parent-authorization-r1/proposal.json'))
    unit={'unit':scope.API_UNIT,'memory_max_bytes':32*scope.GIB,'cpu_quota_percent':800,'restart':'no'}
    shape=seal.validate_review_shapes(plan,bundle,schemas,parent,unit)
    assert shape['passed'] and shape['runtime_authorized'] is False
    assert tuple(seal.postgrant_sequence())==activate.PHASES
    rejected=[]
    for key,value in [('memory_max_bytes',833*scope.GIB),('slice','foreign.slice')]:
        changed=copy.deepcopy(parent)
        changed[key]=value
        try:
            seal.validate_review_shapes(plan,bundle,schemas,changed,unit)
        except ValueError:
            rejected.append(key)
        else:
            raise AssertionError('A changed shared boundary was accepted')
    probe=scope.load(reference(activate.PROBE_RESULT))
    resolution=scope.load(reference(scope.NETWORK_RESOLUTION_FILE))
    assert activate.validate_probe_evidence(probe,resolution)
    changed=copy.deepcopy(probe)
    for row in changed['probes']:
        if row['port']==443:
            row['TLS_check_hostname']=False
    assert not activate.validate_probe_evidence(changed,resolution)
    original=scope.require_allowed
    guard_calls=[]
    def refuse(operation,**_kwargs):
        guard_calls.append(operation)
        raise PermissionError('Synthetic missing grant')
    scope.require_allowed=refuse
    try:
        try:
            activate.activate()
        except PermissionError:
            pass
        else:
            raise AssertionError('An ungranted activation entered execution')
    finally:
        scope.require_allowed=original
    assert guard_calls==['v131.prepare'] and not denied
    assert not activate.OUTPUT.exists()
    output=scope.ARTIFACT_ROOT/'seal-activation-controls-r1/summary.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    return write_new(output,{'version':'v131-seal-activation-shape-controls-r1','passed':True,
        'source':reference(__file__),'sealer_source':reference(seal.__file__),
        'activation_source':reference(activate.__file__),
        'plan':reference(scope.PLAN_FILE),'actual_member_inventory':reference(scope.ARTIFACT_ROOT/'organization-sdk-controls-r1/member-schema-inventory.json'),
        'shape_fixture_is_not_bundle_or_runtime_qualification':True,
        'changed_parent_rejected':rejected,'existing_actual_probe_readonly_validation':True,
        'disabled_TLS_verification_rejected':True,'new_scope_guard_precedes_all_external_actions':guard_calls,
        'activation_created':False,'source_seal_created':False,'approved_authorization_written':False,
        'model_calls':0,'Docker_operations':0,'root_commands':0,'network_connections':0,
        'forbidden_operation_attempts':denied})


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
