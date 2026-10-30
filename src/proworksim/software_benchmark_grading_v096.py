"""Async scoring for new original-ID results, with a cold scorer-only interpreter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

from . import software_benchmark_api_scope_v096 as scope
from . import software_benchmark_recovery_grading_v089 as base
from .software_benchmark_runtime_v096 import bindings
from .software_benchmark_candidates_v054 import reference, write_new
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v096-isolated-new-original-candidate-scoring-r1'
MODULE = 'proworksim.software_benchmark_grading_v096'


def clean_environment():
    value=dict(os.environ)
    for name in ('PYTHONHOME','PYTHONPATH','PYTHONEXECUTABLE','LD_LIBRARY_PATH','LD_PRELOAD'):
        value.pop(name,None)
    return value


def command(arguments):
    return [str(scope.ROOT/'.venv/bin/python'),'-B',str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
            '-m',MODULE,*arguments]


_namespace=clone_namespace(base,scope=scope,bindings=bindings,VERSION=VERSION,__file__=__file__,__name__=__name__)


def validate_qualification(ref,config,plan_ref):
    # The unchanged reuse validator loads the large original plans several
    # times. Reuse the original dispatcher's hash-checked parsed-object cache
    # in this private namespace; retain every original source/control check.
    from . import software_benchmark_qualification_reuse_v066 as reuse
    cached=clone_namespace(reuse)
    cached['load']=scope.load
    def original_check(proof,original_config,original_plan):
        if scope.load(proof).get('version')==reuse.VERSION:
            return cached['validate_reused'](proof,original_config,original_plan)
        return base.original_scorer.validate_qualification(proof,original_config,original_plan)
    observed=SimpleNamespace(**{**vars(base.original_scorer),'validate_qualification':original_check})
    return private_function(base.validate_qualification,scope=scope,
                            original_scorer=observed)(ref,config,plan_ref)


_namespace['validate_qualification']=validate_qualification


def scorer(policy,*,manifest_provider=None):
    value=private_function(base.scorer,**_namespace)(policy)
    original_manifest=value.installation_manifest

    def manifest():
        if manifest_provider is not None:
            return manifest_provider()
        return {**original_manifest(),'scoring_adapter':reference(__file__),
            'scorer_interpreter_profile':'fixed_offline_launcher_without_API_tokenizer_overlay',
            'host_launcher':reference(scope.ROOT/'tools/run_offline_scorer_v096.py'),
            'host_library_threads':1,
            'candidate_bytes_changed':False,'official_tests_and_scoring_rules_changed':False}

    value.score_request.__globals__['installation_manifest']=manifest
    value.__dict__['installation_manifest']=manifest
    return value


def cold_manifest():
    # Never introspect dependency versions from the API counter's sys.path.
    result=subprocess.run(command(['--manifest']),cwd=scope.ROOT,env=clean_environment(),
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
    if result.returncode:
        raise RuntimeError('Isolated scorer manifest failed: '+result.stderr[-2000:])
    return json.loads(result.stdout)


def host(policy,scoring):
    value=private_function(base._base,**_namespace)(policy,scoring)
    namespace=value.run_request.__globals__
    namespace['bootstrap_environment']=clean_environment
    value.__dict__['bootstrap_environment']=clean_environment
    return value


class Grading:
    def __init__(self,policy):
        self.policy=policy
        self.scorer=scorer(policy,manifest_provider=cold_manifest)
        self.base=host(policy,self.scorer)

    def __getattr__(self,name):
        return getattr(self.base,name)

    def run_request(self,request_ref,stop_event=None):
        request=scope.load(request_ref)
        scope.require_grading_allowed('v096.run',slot_id=request['slot_id'],instance_id=request['instance_id'])

        def fixed_python(arguments):
            if arguments[:2]!=['-m','proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the bounded official scorer child can be redirected')
            return command(arguments[2:])

        return private_function(self.base.run_request,fixed_python=fixed_python,
            bootstrap_environment=clean_environment)(request_ref,stop_event=stop_event)


_namespace.update(scorer=scorer,Grading=Grading)
factory=private_function(base.factory,**_namespace)


def score_request(request,*,validate_only=False):
    scope.require_grading_allowed('v096.run',slot_id=request['slot_id'],instance_id=request['instance_id'])
    policy=bindings.dispatch_view(scope.require_grading_allowed)
    module=scorer(policy)
    folder=Path(request['directory'])
    if folder!=scope.original.GRADING_ROOT/request['resource_key'] or (folder/'quiescence.json').exists():
        raise ValueError('Foreign or consumed scoring identity')
    execution=module.resolve_execution_request(request)
    from .software_benchmark_rescore_v095 import host_limits
    limits=host_limits(execution['cpuset_cpus'])
    if validate_only:
        module.validate_request(execution)
        return {'passed':True,'actual_original_validate_request_executed':True,
            'manifest_equal':scope.load(request['scorer_manifest'])==module.installation_manifest(),
            'host_limits':limits,'Docker_operations':0,'model_calls':0}
    write_new(folder/'v096-host-limits.json',limits)
    return module.score_request(request)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--manifest',action='store_true')
    modes.add_argument('--request',type=Path)
    modes.add_argument('--validate-request',type=Path)
    args=parser.parse_args()
    if args.manifest:
        module=scorer(bindings.dispatch_view(scope.require_grading_allowed))
        print(json.dumps(module.installation_manifest(),ensure_ascii=False))
        return
    request=json.loads((args.request or args.validate_request).read_bytes())
    value=score_request(request,validate_only=args.validate_request is not None)
    print(json.dumps(value if args.validate_request else {k:value[k] for k in ('resource_key','status','resolved')},ensure_ascii=False))


if __name__=='__main__':
    main()
