"""Private scoring-only baseline/probe/reset bindings for the frozen pilot.

All changes execute inside newly owned, mount-free scoring containers before
candidate or official-test application. Official test patch and test commands
remain byte-identical. This module neither grants authority nor starts Docker.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace, ModuleType

from . import software_benchmark_grading_repairs_v097 as legacy
from . import software_benchmark_grader_probe_v097 as probe
from . import software_benchmark_test_reset_v099 as astropy_reset
from . import software_benchmark_test_reset_v114 as pylint_reset
from .software_benchmark_candidates_v054 import reference, write_new

VERSION='v157-pinned-clean-tree-and-legacy-probe-r1'
CLEAN_TASK='psf__requests-1142'
RESET_TASKS=frozenset({'astropy__astropy-7336','pylint-dev__pylint-6528'})


def _bind(function,namespace):
    value=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value


def clean_command(base_commit, official_tree):
    if any(not re.fullmatch('[0-9a-f]{40}',v or '') for v in (base_commit,official_tree)):
        raise ValueError('Only the pinned full official commit/tree may normalize a fresh scoring workspace')
    # This command has no variable user paths. It does not discard model work:
    # the freshly created official image has not received a candidate or tests.
    return ('set -eu\ncd /testbed\n'
        '[ "$(git -c safe.directory=/testbed rev-parse HEAD)" = '+base_commit+' ]\n'
        '[ "$(git -c safe.directory=/testbed rev-parse HEAD^{tree})" = '+official_tree+' ]\n'
        'git -c safe.directory=/testbed reset --hard '+base_commit+'\n'
        'git -c safe.directory=/testbed clean -fd\n')


def bind_scorer(existing, instances):
    rows={r['instance_id']:r for r in instances}
    if set(rows)!=RESET_TASKS:
        raise ValueError('Freeze exactly astropy7336 and pylint6528 reset sources')
    bound=legacy.bind_scorer(existing)
    ns=bound.score_request.__globals__
    base=ns['base'];archive=ns['archive']

    class ObservedContainer(bound.ObservedContainer):
        def start(self,*args,**kwargs):
            task=self.preparation['mapping']['instance_id']
            ns['policy'].require_v066_allowed('v066.grader.start',instance_id=task)
            self.delegate.reload()
            ns['validate_attrs'](self.delegate.attrs,self.preparation)
            result=self.delegate.start(*args,**kwargs)
            self.delegate.reload()
            ns['validate_attrs'](self.delegate.attrs,self.preparation)
            path=Path(self.preparation['path'])
            mapping=self.preparation['mapping']
            reset_ref=None
            if task==CLEAN_TASK:
                command=['/bin/bash','-c',"git -c safe.directory=/testbed -C /testbed rev-parse HEAD 'HEAD^{tree}' && git -c safe.directory=/testbed -C /testbed status --porcelain"]
                before=archive.checked_exec(self.delegate,command,timeout_note='Fresh official baseline before normalization')
                lines=before.splitlines()
                if len(lines)<2 or lines[:2]!=[self.preparation['base_commit'],mapping['official_tree']]:
                    raise ValueError('Never normalize an unpinned initial commit/tree')
                if len(before.encode())>1024*1024:
                    raise ValueError('Unexpectedly large original dirty baseline evidence')
                cleaned=archive.checked_exec(self.delegate,['/bin/bash','-c',clean_command(self.preparation['base_commit'],mapping['official_tree'])],timeout_note='Owned fresh scorer official baseline normalization')
                reset_ref=write_new(path.with_name('initial-baseline-normalization-v157.json'),{
                    'version':VERSION,'instance_id':task,'container_id':self.delegate.id,
                    'original_observation':before,'normalization_output':cleaned,
                    'baseline_commit':self.preparation['base_commit'],'official_tree':mapping['official_tree'],
                    'before_candidate_and_official_tests':True,'host_paths_mounted':False,
                    'ignored_environment_files_removed':False,'existing_candidate_modified':False})
            observation=self.delegate.exec_run(['/bin/bash','-c',
                "git -c safe.directory=/testbed -C /testbed rev-parse HEAD 'HEAD^{tree}' && git -c safe.directory=/testbed -C /testbed status --porcelain"])
            lines=observation.output.decode('utf-8',errors='replace').splitlines()
            hostconfig=self.delegate.attrs['HostConfig']
            observed={'scope':'preparation_only_before_eval_script','container_id':self.delegate.id,
                'image_id':self.delegate.attrs['Image'],'git_returncode':observation.exit_code,
                'head':lines[0] if len(lines)>=2 else None,'head_git_tree':lines[1] if len(lines)>=2 else None,
                'working_tree_clean':len(lines)==2 if observation.exit_code==0 else None,
                'host_config':{k:hostconfig.get(k) for k in ('NetworkMode','Memory','NanoCpus','PidsLimit','DeviceRequests','Devices','Binds')},
                'initial_baseline_normalization':reset_ref}
            path.write_bytes(base.canonical(observed))
            if (observed['git_returncode']!=0 or observed['head']!=self.preparation['base_commit']
                or observed['head_git_tree']!=mapping['official_tree'] or observed['working_tree_clean'] is not True):
                raise ValueError('Official initial baseline is not the pinned clean tree')
            inside,evidence=probe.observe(self.delegate,mapping['public_python'],path.with_name('private-boundary-probe-v097.json'))
            host={key:os.stat('/proc/self/ns/'+key).st_ino for key in archive.NAMESPACES}
            if inside['cpus']!=ns['cpus'](self.preparation['cpuset_cpus']):
                raise ValueError('Actual grader CPU affinity differs')
            observed.update(namespace_evidence=archive.namespace_evidence(inside['namespaces'],host),
                boundary_probe=evidence,source_image_id=self.preparation['image_id'],
                candidate_or_official_tests_changed=False,actual_cap_add=[],actual_cap_drop=['ALL'],
                effective_network_mode='none',resource_key=self.preparation['resource_key'])
            path.write_bytes(base.canonical(observed))
            return result

    class Containers(bound.Containers):
        create=_bind(bound.Containers.create,{**bound.Containers.create.__globals__,**ns,'ObservedContainer':ObservedContainer})

    prior=ns['diagnostics']
    def make_repaired_run_instance(harness,directory):
        original,provenance=prior.make_repaired_run_instance(harness,directory)
        prepared=SimpleNamespace(make_repaired_run_instance=lambda *_:(original,provenance))
        adapters={}
        metadata={}
        for task,mechanism in (('astropy__astropy-7336',astropy_reset),('pylint-dev__pylint-6528',pylint_reset)):
            adapters[task],metadata[task]=mechanism.diagnostics_adapter(prepared,[rows[task]]).make_repaired_run_instance(harness,directory)
        def run_instance(spec,*args,**kwargs):
            return adapters.get(spec.instance_id,original)(spec,*args,**kwargs)
        return run_instance,{**provenance,'selective_reset_by_task':metadata,
            'exact_reset_sources':{task:reference(mod.__file__) for task,mod in
                (('astropy__astropy-7336',astropy_reset),('pylint-dev__pylint-6528',pylint_reset))},
            'official_test_patch_and_test_commands_changed':False}
    inherited=bound.installation_manifest
    def manifest():
        current=inherited()
        if current.get('pilot_environment_adapter')==reference(__file__) and 'selective_reset_actual_hashes' in current:
            return current
        from swebench.harness import run_evaluation as harness
        hashes={}
        for task,mechanism in (('astropy__astropy-7336',astropy_reset),('pylint-dev__pylint-6528',pylint_reset)):
            _,proof=mechanism.repair_eval_script({**rows[task],'eval_script':harness.make_test_spec(rows[task]).eval_script})
            hashes[task]={k:proof[k] for k in ('repaired_eval_sha256','official_test_patch_sha256')}
        return {**current,'selective_reset_actual_hashes':hashes,'pilot_environment_adapter':reference(__file__),
            'fresh_baseline_normalization_tasks':[CLEAN_TASK],'legacy_boundary_probe':reference(probe.__file__),
            'selective_reset_tasks':sorted(RESET_TASKS),
            'selective_reset_by_task':{'astropy__astropy-7336':reference(astropy_reset.__file__),
                                      'pylint-dev__pylint-6528':reference(pylint_reset.__file__)},
            'official_test_patch_and_test_commands_changed':False}
    ns.update(ObservedContainer=ObservedContainer,Containers=Containers,installation_manifest=manifest,
        diagnostics=SimpleNamespace(**{**vars(prior),'make_repaired_run_instance':make_repaired_run_instance}))
    value=ModuleType(__name__+'.private_official_scorer');value.__dict__.update(ns)
    return value
