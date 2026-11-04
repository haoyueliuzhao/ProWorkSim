"""One local check of new group/child/aggregate-parent bindings, without Docker."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
denied = []


def audit(event, _args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto',
                 'subprocess.Popen','os.system','os.fork','os.posix_spawn'}:
        denied.append(event)
        raise RuntimeError('This binding control cannot obtain external execution')


sys.addaudithook(audit)


def main():
    from proworksim import software_benchmark_grading_v131 as grading
    from proworksim import software_benchmark_api_parent_v131 as parent
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    scope = grading.scope
    authority = []
    def guard(operation, **_identity):
        authority.append(operation)
        return {'CPU_fixture_only':True}
    policy = scope.dispatch_view(guard)
    policy.require_v066_allowed = guard
    scoring = grading.scorer(policy)
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    row = plan['rows'][0]
    request = {'plan':plan_ref,'resource_key':'score-'+str(row['slot_index']),
        'configuration':row['configuration'],'instance_id':row['instance_id'],
        'slot_id':row['slot_id'],'source_slot_id':row['source_slot_id'],
        'measurement_kind':row['measurement_kind'],'organization_id':row['organization_id'],
        'group_id':row['group_id']}
    actual, _, config = scoring._planned(request)
    assert actual == plan and config['organization_id']==row['organization_id']
    rejected=[]
    for key,value in [('group_id','FOREIGN'),('organization_id','FOREIGN')]:
        changed=copy.deepcopy(request)
        changed[key]=value
        try:
            scoring._planned(changed)
        except ValueError:
            rejected.append(key)
        else:
            raise AssertionError('Cross-group score was admitted')
    command=grading.command(['--request','fixture-request.json'])
    assert command[-4:]==['-m','proworksim.software_benchmark_grading_v131','--request','fixture-request.json']
    assert scoring.validate_request.__globals__['_planned'] is scoring._planned
    assert scoring.validate_request.__globals__['_generation_result'] is scoring._generation_result
    assert scoring.validate_request.__globals__['validate_candidate_request'] is scoring.validate_candidate_request
    concrete=scoring._v118_concrete_score
    assert concrete.__globals__['diagnostics'].make_repaired_run_instance is grading.previous.original.diagnostics.make_repaired_run_instance
    prior = parent.require_qualified
    parent.require_qualified=lambda:{'synthetic_CPU_parent_qualification':True}
    captured=[]
    class CapturedBeforeDocker(Exception):
        pass
    class Delegate:
        def create(self,**options):
            captured.append(options)
            raise CapturedBeforeDocker()
        def get(self,*_args):
            raise LookupError('No actual object exists')
    try:
        with tempfile.TemporaryDirectory(prefix='pws-v131-grader-binding-') as temporary:
            path=Path(temporary)/'claim.json'
            path.write_text(json.dumps({'key':'control-v131-psf__requests-1766-gold',
                'plan':plan_ref,'docker_name':'only-a-CPU-fixture-not-created'}))
            task='psf__requests-1766'
            image=plan['environments'][task]['image_id']
            observation={'mapping':{'instance_id':task},'capacity_claim':reference(path),
                'image_id':image,'cpuset_cpus':scope.cpu_set('grader',0)}
            tracking={'owned_container_ids':[]}
            client=scoring.Containers(Delegate(),image,observation,tracking)
            try:
                client.create(image=image)
            except CapturedBeforeDocker:
                pass
            else:
                raise AssertionError('The actual create body did not reach the bounded capture')
            assert len(captured)==1
            options=captured[0]
            assert options['cgroup_parent']==scope.CONTAINER_PARENT
            assert options['network_mode']=='none' and options['cap_drop']==['ALL']
            assert options['cap_add']==['NET_ADMIN','NET_BIND_SERVICE']
            assert options['mem_limit']==16*1024**3 and options['nano_cpus']==4_000_000_000
            assert options['extra_hosts']=={'httpbin.org':'127.0.0.1'}
            try:
                client.create(image=image,cgroup_parent='foreign.slice')
            except ValueError:
                pass
            else:
                raise AssertionError('A caller-supplied parent override escaped the original guard')
        for attrs in ({'HostConfig':{}},{'HostConfig':{'CgroupParent':'foreign.slice'}}):
            try:
                scoring.validate_attrs(attrs,observation)
            except PermissionError:
                pass
            else:
                raise AssertionError('Actual grading attrs accepted a foreign/missing parent')
        parent.validate_container_parent({'HostConfig':{'CgroupParent':scope.CONTAINER_PARENT},'State':{'Running':False}})
    finally:
        parent.require_qualified=prior
    assert not denied
    output=scope.ARTIFACT_ROOT/'grading-binding-controls-r2/summary.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    return write_new(output,{'version':'v131-actual-grading-binding-cpu-control-r1','passed':True,
        'source':reference(__file__),'grading_source':reference(grading.__file__),
        'scope_source':reference(scope.__file__),'plan':plan_ref,
        'group_substitutions_rejected':rejected,'child_module':'proworksim.software_benchmark_grading_v131',
        'concrete_TLS_evaluator_retained':True,'actual_Containers_create_body_executed':True,
        'captured_before_real_Docker':True,'expected_parent':scope.CONTAINER_PARENT,
        'caller_foreign_parent_rejected':True,'foreign_actual_parent_rejected':True,
        'synthetic_capacity_and_parent_proofs_are_not_runtime_qualification':True,
        'local_guard_calls':authority,'forbidden_operation_attempts':denied,
        'model_calls':0,'Docker_operations':0,'network_connections':0,'new_objects':0})


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
