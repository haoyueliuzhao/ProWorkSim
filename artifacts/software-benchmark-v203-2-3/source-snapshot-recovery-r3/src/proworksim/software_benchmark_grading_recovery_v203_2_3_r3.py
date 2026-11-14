"""New independent attempts scored with the qualified r4 HTTP/TLS environment."""
from __future__ import annotations
from functools import lru_cache
import inspect,textwrap
from pathlib import Path
from types import FunctionType
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_3_r4 as previous
from . import software_benchmark_scope_v203_2_3_r3 as scope
from . import software_benchmark_project_closure_v203_2_3_r3 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_delivery_reuse_v175 import bind_host

VERSION=previous.VERSION
MODULE='proworksim.software_benchmark_grading_recovery_v203_2_3_r3'
OLD_PLAN=scope.PREVIOUS_BATCH_ROOT/'execution-plan.json'


def original_environment_config(config,plan_ref):
    if plan_ref!=reference(scope.PLAN_FILE):raise ValueError('Wrong independent recovery plan')
    current=scope.validate_plan(scope.load(plan_ref));old=scope.load(reference(OLD_PLAN))
    rows=[r for r in current['rows'] if scope.load(r['configuration'])==config]
    if len(rows)!=1:raise ValueError('Only an exact frozen recovery configuration may be scored')
    row=rows[0];prior=[r for r in old['rows'] if r['slot_id']==row['original_slot_id']]
    if len(prior)!=1 or any(row[k]!=prior[0][k] for k in ('instance_id','repo','seed','group_id','condition_id')):
        raise ValueError('Recovery changed original task, condition, or seed')
    canonical=scope.load(old['environments'][config['instance_id']]['configuration'])
    if (base.environment_identity(config)!=base.environment_identity(canonical)
            or config['public_task']!=canonical['public_task'] or config['public_test_entry']!=canonical['public_test_entry']):
        raise ValueError('An independent attempt changed the qualified official/public task environment')
    return canonical


def scorer(policy,*,manifest_provider=None):
    value=previous.scorer(policy,manifest_provider=manifest_provider)
    namespace=value.validate_request.__globals__
    namespace['validate_delivery_evidence']=closure.validate_delivery_evidence
    value.validate_delivery_evidence=closure.validate_delivery_evidence
    def validate(ref,config,plan_ref):
        canonical=original_environment_config(config,plan_ref)
        alias=scope.load(ref)
        expected_path=scope.COORDINATOR_ROOT/'qualifications'/(config['instance_id']+'.json')
        if (Path(ref['path']).resolve()!=expected_path or alias.get('version')!='v203.2.3-independent-recovery-environment-link-r3'
                or alias.get('plan')!=plan_ref or alias.get('instance_id')!=config['instance_id']
                or alias.get('original_plan')!=reference(OLD_PLAN)
                or alias.get('environment_identity')!=base.environment_identity(canonical)):
            raise ValueError('Recovery qualification link changed its task, plan, or exact environment')
        return previous.validate_qualification(alias['original_qualification'],canonical,reference(OLD_PLAN))
    namespace['validate_qualification']=validate;value.validate_qualification=validate
    prior_manifest=value.installation_manifest
    def manifest():
        result=prior_manifest()
        if manifest_provider is not None:return result
        return {**result,'managed_delivery_validator':reference(closure.__file__),
            'independent_recovery_candidate_binding':reference(__file__),
            'old_paid_attempts_not_reused_as_candidate_results':True}
    namespace['installation_manifest']=manifest;value.installation_manifest=manifest
    return value


_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_host=_ns['host']
def host(policy,scoring):return bind_host(_parent_host(policy,scoring))
_ns.update(scorer=scorer,host=host)
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_ns))
_methods={k:clone_function(v,_ns) for k,v in vars(base.Grading).items() if isinstance(v,FunctionType)}
_source=textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'","'v203.2.3.run'")
_local={};exec(compile(_source,__file__+':grading-child','exec'),_ns,_local);_methods['run_request']=_local['run_request']
_ns['Grading']=type('Grading',(base.Grading,),_methods)
for _name in ('score_request','main'):
    _source=inspect.getsource(getattr(base,_name)).replace("'v105.run'","'v203.2.3.run'")
    exec(compile(_source,__file__+':'+_name,'exec'),_ns)
for _name in ('factory','score_request','main','command','Grading','cold_manifest'):
    globals()[_name]=_ns[_name]
if __name__=='__main__':main()
