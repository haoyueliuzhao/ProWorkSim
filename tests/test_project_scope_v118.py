"""Pure admission checks on the actual new plan; no resource/client creation."""
import copy
import pytest

from proworksim import software_benchmark_scope_v118 as scope
from proworksim import software_benchmark_episode_v118 as episode
from proworksim import software_benchmark_sdk_bundle_v118 as bundle
from proworksim.software_benchmark_alignment_contract_v117 import VERSION as STRATEGY
from proworksim.software_benchmark_candidates_v054 import reference, write_new

pytestmark = pytest.mark.skipif(not scope.PLAN_FILE.is_file(), reason='Requires the local frozen v118 preparation')


def test_actual_project_inventory_and_disjoint_bounded_lanes():
    plan = scope.load(reference(scope.PLAN_FILE))
    assert scope.validate_plan(plan) is plan
    assert len(plan['rows']) == 50 and scope.CONSTRAINTS['maximum_containers'] == 302
    assert scope.CONSTRAINTS['maximum_named_volumes'] == 51
    for changed in ({**plan, 'rows': plan['rows'][:-1]},
                    {**plan, 'rows': [{**plan['rows'][0], 'arm': 'REF'}, *plan['rows'][1:]]},
                    {**plan, 'resource_role_counts': {}}):
        with pytest.raises(PermissionError):
            scope.validate_plan(changed)
    lanes = [scope.cpu_set('coordinator')]
    lanes += [scope.cpu_set(role, index) for index in range(16) for role in ('actor', 'controller')]
    lanes += [scope.cpu_set('grader', index) for index in range(2)]
    all_cpus = [value for lane in lanes for value in lane.split(',')]
    assert len(all_cpus) == len(set(all_cpus)) == 112


def test_new_host_entry_uses_actual_v118_bundle_and_rejects_prior_strategy(tmp_path, monkeypatch):
    source = write_new(tmp_path/'synthetic-source-index.json', {'files': []})
    authority = {'status': 'approved', 'execution_alignment_version': STRATEGY,
                 'source_index': source, 'plan': reference(scope.PLAN_FILE)}
    calls = []
    def guard(operation, **identity):
        calls.append((operation, identity))
        return copy.deepcopy(authority)
    value = episode.build_episode(scope=scope, guard=guard)
    assert value.runtime is bundle and value._run.__globals__['runtime'] is bundle
    assert value._run.__globals__['validate_actor_ready'] is episode.validate_actor_ready
    assert value.run_episode.__globals__['_run'] is value._run
    assert value.deployment_revision == episode.VERSION
    assert value.integration_points['effective_deadline'] == 1
    assert calls == [('v066.run', {})]
    authority['execution_alignment_version'] = 'v110-single-agent-strategy-alignment-r1'
    with pytest.raises(PermissionError, match='earlier experiment grant'):
        episode.build_episode(scope=scope, guard=guard)
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'absent-runtime-authorization.json')
    with pytest.raises(PermissionError):
        scope.require_allowed()
