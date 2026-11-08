"""Prepare independently bounded Requests1724 scoring metadata; no network/API."""
from __future__ import annotations
import argparse
from pathlib import Path
import json

from proworksim import software_benchmark_scope_v160 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def plan():
    predecessor=scope.ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/execution-plan-r2.json'
    prior=scope.load(reference(predecessor));environment=prior['environments'][scope.TASK]
    resources={key:{'role':'control','instance_id':scope.TASK,'patch_kind':key.rsplit('-',1)[1],
        'image_id':environment['image_id'],'endpoint':'environment_control'} for key in scope.CONTROL_KEYS}
    value={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'predecessor_plan':reference(predecessor),
        'environments':{scope.TASK:environment},'resources':resources,'rows':[],'generation_rows':[],
        'host_cpu_pool':reference(scope.SOURCE_CPU_POOL_FILE),'constraints':scope.CONSTRAINTS,
        'model_calls':0,'scoring_only':True,'model_candidates_changed':False,'task_identity_changed':False,
        'original_pending_task':'v157 second wave slots15757/15758/15759 remain uncalled',
        'new_control_keys_only':True,'maximum_new_containers':2,'new_volumes':0}
    scope.validate_plan(value)
    return scope.retain(scope.PLAN_FILE,value)


def sources():
    # Reuse the established scorer import closure, rehashing it at this new
    # independent deployment; add only the new1724 modules and owned tools.
    previous=scope.ROOT/'artifacts/software-benchmark-v157/environment-authorization-r3/sources.json'
    paths={r['path'] for r in scope.load(reference(previous))['files']}
    for pattern in ('src/proworksim/*v160.py','tools/*v160.py'):
        paths.update(str(p.resolve()) for p in scope.ROOT.glob(pattern))
    return scope.retain(scope.SOURCE_FILE,{'version':'v160-independent-scorer-source-closure-r1',
        'files':[reference(p) for p in sorted(paths)],'v157_source_files_changed':False})


def probe_authority():
    plan_ref=plan();source=sources()
    return scope.retain(scope.PROBE_AUTH_FILE,{'version':'v160-requests1724-probe-authority-r1',
        'status':'approved','scope':reference(scope.__file__),'source_index':source,
        'standing_policy':reference(scope.STANDING_POLICY_FILE),'plan':plan_ref,
        'instance_id':scope.TASK,'hostname':'httpbin.org','ports':[80,443],
        'maximum_connections':4,'maximum_application_bytes':65536,'model_calls':0,'Docker_operations':0,
        'shared_host_configuration_changes':0,'host_listener':False,'strict_TLS':True,'proxy_used':False,
        'user_authority_basis':'Standing experimental permission; root delegated independent1724 grading repair'})


def control_authority():
    prepared=scope.load(reference(scope.COORDINATOR_ROOT/'qualification-preparation.json'))
    if len(prepared['controls'])!=2:raise ValueError('Exactly gold/empty1724 controls required')
    source=sources()
    return scope.retain(scope.AUTH_FILE,{'version':'v160-requests1724-control-authority-r1','status':'approved',
        'scope':reference(scope.__file__),'plan':reference(scope.PLAN_FILE),'source_index':source,
        'standing_policy':reference(scope.STANDING_POLICY_FILE),'resource_keys':list(scope.CONTROL_KEYS),
        'requests':prepared['controls'],'constraints':scope.CONSTRAINTS,'maximum_containers':2,
        'maximum_concurrent_graders':1,'maximum_real_tls_sessions':2,
        'maximum_tcp_connections_total':1024,'maximum_transfer_bytes_total':134217728,
        'model_calls':0,'shared_host_configuration_changes':0,'new_volumes':0,
        'network_resolution':reference(scope.RESOLUTION_FILE),'host_listener':False,'host_mounts':False,
        'strict_TLS_and_original_CA':True,'official_test_patch_changed':False,'model_workspace_changed':False,
        'user_authority_basis':'Standing isolated experimental Docker permission; no shared-host operations'})


if __name__=='__main__':
    parser=argparse.ArgumentParser();p=parser.add_mutually_exclusive_group(required=True)
    p.add_argument('--plan',action='store_true');p.add_argument('--grant-probe',action='store_true');p.add_argument('--grant-controls',action='store_true')
    args=parser.parse_args()
    result=plan() if args.plan else probe_authority() if args.grant_probe else control_authority()
    print(json.dumps(result,ensure_ascii=False))
