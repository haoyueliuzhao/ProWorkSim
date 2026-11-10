import threading
from proworksim import software_benchmark_scope_v192 as scope
from proworksim.software_benchmark_candidates_v054 import reference

def guard(*args,**kwargs):
    from proworksim.software_benchmark_alignment_contract_v192 import VERSION
    return {'status':'approved','execution_alignment_version':VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':reference(scope.PLAN_FILE),'constraints':scope.CONSTRAINTS}

def test_real_host_entry_uses_the_new_condition_usage_closure_and_capacity():
    from proworksim.software_benchmark_episode_v192 import build_episode
    from proworksim.software_context_capacity_v192 import bind_capacity
    from proworksim import software_benchmark_sdk_bundle_v192 as bundle
    episode=build_episode(scope=scope,guard=guard)
    assert episode._run.__globals__['runtime'] is bundle
    assert episode.allowed_organization_ids==('M0','M1-5','M1-10','M1-5K')
    assert episode._run.__globals__['validate_closed_usage'].__module__.endswith('_v192')
    stop=threading.Event();bind_capacity(episode,scope.dispatch_view(guard),stop,lambda _:None)
    assert episode.run_episode.__globals__['_run'] is episode._run
    assert episode._run.__globals__['wait_capacity'] is episode.wait_capacity

def test_only_the_selected_requests_task_gets_private_offline_capability():
    from proworksim.software_benchmark_grading_v192 import private_environment,MODULE
    environment=private_environment(scope.dispatch_view(guard))
    assert MODULE=='proworksim.software_benchmark_grading_v192'
    assert environment.TASKS==frozenset({'psf__requests-5414'})
    assert environment.TLS_TASKS==frozenset()
    assert environment.capabilities('psf__requests-5414')==['NET_ADMIN']
    assert environment.capabilities('psf__requests-1766')==[]
    assert environment.provider('psf__requests-1766') is None
