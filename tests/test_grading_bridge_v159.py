"""Only new private scoring namespaces receive the qualified1724 overlay."""
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_grading_v159 as grading
from proworksim import software_benchmark_scope_v159 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def test_actual_create_attrs_and_score_share_private_qualified_router():
    scorer=grading.scorer(scope.dispatch_view(scope.require_grading_allowed),manifest_provider=lambda:{'CPU_only':True})
    router=scorer.environment
    assert router.TLS_TASKS==frozenset({'psf__requests-1724'})
    assert router.capabilities('psf__requests-1724')==['NET_BIND_SERVICE']
    assert router.capabilities('sympy__sympy-17318')==[]
    for fn in (scorer.Containers.create,scorer.validate_attrs,scorer._score):
        assert fn.__globals__['environment'] is router
    assert scorer._score.__globals__['evaluator_for_qualified_1724'] is grading.evaluator_for_qualified_1724
    assert router.resolution_bridge['path'].startswith(str(scope.BATCH_ROOT))
    old=scope.load(reference(scope.original_scope.PLAN_FILE))
    config=scope.load(old['environments']['psf__requests-1724']['configuration'])
    assert router.verify_qualified_reuse(config)['original_controls_revalidated'] is True


def make_wrapper(keys):
    namespace={'cleanup_container':lambda *args:None}
    exec('def actual(*args, **kwargs): return "actual-original-evaluator"',namespace)
    original=namespace['actual'];adapters={key:lambda *args:None for key in keys}
    def wrapped(spec,*args,**kwargs):
        return adapters.get(spec.instance_id,original)(spec,*args,**kwargs)
    return wrapped,original


def test_nonreset1724_exposes_original_cleanup_while_other_tasks_keep_reset():
    outer,actual=make_wrapper({'astropy__astropy-7336','pylint-dev__pylint-6528'})
    assert grading.evaluator_for_qualified_1724(outer,'psf__requests-1724') is actual
    assert grading.evaluator_for_qualified_1724(outer,'astropy__astropy-7336') is outer
    assert grading.evaluator_for_qualified_1724(outer,'sympy__sympy-17318') is outer
    with pytest.raises(ValueError):
        bad,_=make_wrapper({'unknown-task'})
        grading.evaluator_for_qualified_1724(bad,'psf__requests-1724')
