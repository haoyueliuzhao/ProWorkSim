"""Fresh physical scorer resources; original task environments and qualifications."""
from __future__ import annotations
from functools import lru_cache
import inspect,textwrap
from types import FunctionType
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_3_r2 as previous
from . import software_benchmark_scope_v203_2_3_r2 as scope
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_delivery_reuse_v175 import bind_host

VERSION=previous.VERSION
MODULE='proworksim.software_benchmark_grading_redeployment_v203_2_3_r2'
OLD_PLAN=scope.PREVIOUS_BATCH_ROOT/'execution-plan.json'


def scorer(policy,*,manifest_provider=None):
    value=previous.scorer(policy,manifest_provider=manifest_provider)
    strict=value.validate_qualification
    def validate(ref,config,plan_ref):
        if plan_ref!=reference(scope.PLAN_FILE):raise ValueError('Wrong redeployment plan')
        current=scope.validate_plan(scope.load(plan_ref));old=scope.load(reference(OLD_PLAN))
        rows=[r for r in current['rows'] if scope.load(r['configuration'])==config]
        if len(rows)!=1 or rows[0] not in old['rows']:
            raise ValueError('Only identical frozen logical rows may use previous environment evidence')
        canonical=scope.load(old['environments'][config['instance_id']]['configuration'])
        if config['instance_id']=='psf__requests-1766':
            from .software_benchmark_requests_recovery_v203_2_3_r3 import validate_qualification
            return validate_qualification(ref,canonical,reference(OLD_PLAN))
        return strict(ref,canonical,reference(OLD_PLAN))
    value.validate_request.__globals__['validate_qualification']=validate
    value.validate_qualification=validate
    return value


_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_host=_ns['host']
def host(policy,scoring):
    return bind_host(_parent_host(policy,scoring))
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
