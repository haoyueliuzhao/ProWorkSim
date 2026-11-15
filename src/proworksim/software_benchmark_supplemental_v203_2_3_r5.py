"""Official grading of prelocked code after a failed public-test interface.

Original generation remains technical_unknown. No actor synchronization or
normal-generation status is invented; only the candidate admission is replaced.
"""
from pathlib import Path
from functools import lru_cache
from types import FunctionType
import json, subprocess
from . import software_benchmark_grading_recovery_v203_2_3_r3 as previous
from . import software_benchmark_grading_v105 as base
from .software_benchmark_candidates_v054 import reference, checked
from .software_benchmark_expansion_episode_v069 import clone_function

scope=previous.scope
MODULE='proworksim.software_benchmark_supplemental_v203_2_3_r5'
OUT=scope.ARTIFACT_ROOT/'terminal-repair-r5'
KIND='supplemental_locked_code_after_public_test_interface_failure'

def authority():
    a=scope.load(reference(OUT/'authorization.json'))
    if a['source']!=reference(__file__) or a['inventory']!=reference(OUT/'inventory.json') or a['model_calls_allowed']!=0:
        raise PermissionError('Supplemental authorization changed')
    return a

def command(args):return [str(scope.ROOT/'.venv/bin/python'),'-B',str(scope.ROOT/'tools/run_offline_scorer_v096.py'),'-m',MODULE,*args]

@lru_cache(maxsize=1)
def cold_manifest():
    p=subprocess.run(command(['--manifest']),cwd=scope.ROOT,env=base.clean_environment(),capture_output=True,text=True,timeout=90)
    if p.returncode:raise RuntimeError(p.stderr[-3000:])
    return json.loads(p.stdout)

def scorer(policy,*,manifest_provider=None):
    authority()
    value=previous.scorer(policy)
    ns=value.validate_request.__globals__
    original_planned=ns['_planned']; original_manifest=value.installation_manifest
    def planned(request):
        if request.get('measurement_kind')!=KIND:raise ValueError('Supplemental endpoint must be explicitly labeled')
        return original_planned({**request,'measurement_kind':'full_verified_comparison'})
    def validate_candidate(request,resource,config,plan):
        a=authority()
        if resource['role']!='score' or request['resource_key'] not in a['allowed_resource_keys']:
            raise PermissionError('Only eleven unused code-score resources authorized')
        inv=scope.load(a['inventory']); matches=[r for r in inv['rows'] if r['row']['slot_id']==request['slot_id'] and r['state']=='locked_supplemental_candidate_verified']
        if len(matches)!=1:raise ValueError('Candidate identity missing')
        item=matches[0]
        if request['generation_result']!=item['result'] or request['configuration']!=item['row']['configuration']:
            raise ValueError('Original generation/source binding changed')
        result=scope.load(item['result']);quiet=scope.load(item['quiescence'])
        if result['status']!='technical_unknown' or not quiet['quiescent'] or quiet['cleanup_errors']:
            raise ValueError('Original stopped generation/cleanup proof differs')
        for key in ('original_lock','candidate','tree','binding','patch_receipt','patch','first_RPC_fault'):checked(item[key])
        lock=scope.load(request['candidate_lock']);original=scope.load(item['original_lock']);receipt=scope.load(item['patch_receipt'])
        expected={**original,'patch_receipt':{**receipt,'patch':item['patch']},'supplemental_source':item['original_lock'],'generation_remains_technical_unknown':True}
        if lock!=expected or not receipt['round_trip_verified'] or receipt['candidate_tree_sha256']!=original['tree_sha256']:
            raise ValueError('Supplemental lock changed the unique original candidate')
        value.validate_qualification(request['qualification'],config,request['plan'])
        if resource['image_id']!=config['scorer_request_base']['image']['image_id']:raise ValueError('Image changed')
        return lock
    def manifest():
        if manifest_provider:return manifest_provider()
        return {**original_manifest(),'supplemental_candidate_validator':reference(__file__),'generation_not_reclassified':True,'no_model_feedback':True}
    ns.update(_planned=planned,validate_candidate_request=validate_candidate,installation_manifest=manifest)
    value.validate_candidate_request=validate_candidate;value.installation_manifest=manifest
    return value

_ns={**previous.factory.__globals__,'scope':scope,'MODULE':MODULE,'scorer':scorer,'cold_manifest':cold_manifest,'command':command}
_methods={k:clone_function(v,_ns) for k,v in vars(previous.Grading).items() if isinstance(v,FunctionType)}
_ns['Grading']=type('Grading',(previous.Grading,),_methods)
for name in ('factory','score_request','main'):
    _ns[name]=clone_function(getattr(previous,name),_ns)
factory=_ns['factory'];score_request=_ns['score_request'];main=_ns['main']
if __name__=='__main__':main()
