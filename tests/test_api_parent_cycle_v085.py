import pytest

from proworksim import software_benchmark_api_parent_v085 as parent


def test_private_lifecycle_binding_preserves_completed_predecessor():
    namespace = parent.require_qualified.__globals__
    assert namespace['CREATED'] == parent.CREATED
    assert namespace['RELEASED'] == parent.RELEASED
    assert namespace['approved'] is parent._approved_cycle
    assert parent._prior.CREATED != parent.CREATED
    assert parent._prior.RELEASED != parent.RELEASED
    assert parent.stop_empty.__globals__ is namespace
    assert namespace['create'].__globals__ is namespace
    assert namespace['__file__'] == parent._prior.__file__


@pytest.mark.parametrize('change', [
    {'memory_max_bytes': parent.MEMORY_BYTES + 1},
    {'adopt_existing_object': True},
    {'predecessor_released': {'sha256': 'different'}},
])
def test_scope_or_predecessor_cannot_be_widened(change):
    refs = dict(source={'s': 1}, prior_authority={'a': 2}, prior_release={'r': 3})
    value = {'version': parent.CYCLE_VERSION, 'status': 'approved_by_existing_explicit_scope',
        'source': refs['source'], 'original_authorization': refs['prior_authority'],
        'predecessor_released': refs['prior_release'], 'slice': parent.SLICE,
        'memory_max_bytes': parent.MEMORY_BYTES, 'memory_swap_max_bytes': 0,
        'tasks_max': parent.TASKS_MAX, 'simultaneous_objects': 1,
        'adopt_existing_object': False, 'modify_existing_host_configuration': False}
    assert parent.validate_cycle(value, **refs) == value
    with pytest.raises(PermissionError):
        parent.validate_cycle({**value, **change}, **refs)
