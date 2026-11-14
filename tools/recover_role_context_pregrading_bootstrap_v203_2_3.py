"""Recover one proven pre-Docker launcher rejection; never repeat a score/model.

The v058 cold launcher intentionally drops custom environment variables. Set the
already-sealed zero-model prep selector inside that cold interpreter instead.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ['PWS_V20323_PREPARATION_GRADING'] = '1'
from proworksim import software_benchmark_grading_v203_2_3 as grading
from proworksim import software_benchmark_preparation_grading_v203_2_3 as guard
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_benchmark_expansion_episode_v069 import clone_function

ROOT = grading.scope.ROOT
BOOTSTRAP = "import os,runpy,sys; os.environ['PWS_V20323_PREPARATION_GRADING']='1'; sys.argv=['proworksim.software_benchmark_grading_v203_2_3',*sys.argv[1:]]; runpy.run_module('proworksim.software_benchmark_grading_v203_2_3',run_name='__main__')"


def command(arguments):
    if arguments[:2] != ['-m','proworksim.software_benchmark_scorer_v066']:
        raise ValueError('Only the existing control child can use this bootstrap')
    return [str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-c',BOOTSTRAP,*arguments[2:]]


def main():
    guard.require_allowed()
    policy = grading.scope.dispatch_view()
    owner = grading.Grading(policy)
    root = grading.scope.GRADING_ROOT
    key = 'control-psf__requests-1766-gold'
    folder = root/key
    claim_ref = reference(grading.scope.BATCH_ROOT/'resource-claims'/ (key+'.json'))
    claim = grading.scope.load(claim_ref)
    failed = grading.scope.load(reference(folder/'completion.json'))
    failure_text = (folder/'stderr.log').read_text()
    if (failed.get('returncode') != 1 or 'Concrete v203.2.3 Docker and runtime authorization is not sealed' not in failure_text
            or (folder/'official-output').exists() or (folder/'quiescence.json').exists()
            or Path(claim['lease']).read_bytes() != checked(claim_ref).read_bytes()
            or claim['authorization'] != reference(guard.AUTH_FILE)):
        raise PermissionError('Recovery requires the exact active pre-Docker rejected bootstrap')
    plan = grading.scope.load(reference(grading.scope.PLAN_FILE))
    config = grading.scope.load(plan['environments']['psf__requests-1766']['configuration'])
    from proworksim.software_benchmark_scorer_v054 import install_offline_guard
    install_offline_guard(Path(config['scorer_request_base']['docker_socket']))
    import docker
    client = docker.DockerClient(base_url='unix://'+config['scorer_request_base']['docker_socket'],timeout=30)
    try:
        client.containers.get(claim['docker_name'])
    except docker.errors.NotFound:
        pass
    else:
        raise PermissionError('Never repeat a creation if the exact intended object exists')
    finally:
        client.close()
    archive = folder/'bootstrap-failure-r1'
    archive.mkdir(exist_ok=False)
    preserved = []
    for name in ('started.json','completion.json','stderr.log','stdout.log'):
        path = folder/name
        path.rename(archive/name)
        preserved.append(reference(archive/name))
    authority = grading.scope.retain(guard.AUTH_FILE.parent/'bootstrap-recovery-authority.json', {
        'version':'v203.2.3-pre-Docker-bootstrap-recovery-r1', 'status':'approved',
        'source':reference(__file__), 'original_authority':reference(guard.AUTH_FILE),
        'active_capacity_claim':claim_ref, 'original_failed_host_launch':preserved,
        'exact_intended_container_absent':True, 'official_output_absent':True,
        'existing_grading_and_source_seal_unchanged':True,
        'bootstrap':BOOTSTRAP, 'new_model_calls':0,'graded_attempts_replayed':0})
    used = False
    def reserve(resource_key, *, lane=None):
        nonlocal used
        if resource_key == key:
            if used or lane not in (None,claim['lane']):
                raise PermissionError('One existing reservation can enter its first create only once')
            guard.require_allowed(instance_id='psf__requests-1766')
            if Path(claim['lease']).read_bytes() != checked(claim_ref).read_bytes():
                raise PermissionError('Original grader reservation changed')
            used = True
            return claim_ref
        return policy.claim_resource(resource_key,lane=lane)
    private_policy = SimpleNamespace(**{**vars(policy),'claim_resource':reserve})
    runner = clone_function(owner.base.run_request, {
        **owner.base.run_request.__globals__, 'policy':private_policy,
        'fixed_python':command,'bootstrap_environment':grading.clean_environment})
    outcomes=[]
    for name in (key,'control-psf__requests-1766-empty'):
        ref=reference(root/name/'request.json')
        outcome=runner(ref)
        outcomes.append(outcome)
        print(json.dumps({'control':name,'outcome':outcome}),flush=True)
        if not owner.trustworthy_cleanup(ref):
            raise RuntimeError('Cleanup is not proven; do not enter another physical control')
    qualification=None
    error=None
    try:
        qualification=owner.qualify('psf__requests-1766')
    except (ValueError,KeyError,OSError,TypeError) as problem:
        error=type(problem).__name__+': '+str(problem)
    report={'version':'v203.2.3-pregrading-after-bootstrap-recovery-r1',
            'passed':qualification is not None,'qualification':qualification,'error':error,
            'outcomes':outcomes,'authority':authority,'model_calls':0,'graded_attempts_replayed':0}
    grading.scope.retain(guard.AUTH_FILE.parent/'result.json',report)
    print(json.dumps(report),flush=True)
    if error:raise RuntimeError(error)


if __name__=='__main__':main()
