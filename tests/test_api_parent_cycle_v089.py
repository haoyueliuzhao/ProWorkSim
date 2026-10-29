import pytest

from proworksim import software_benchmark_api_parent_v089 as parent


def test_new_cycle_uses_immediate_predecessor_and_private_receipts():
    ns = parent.require_qualified.__globals__
    assert ns['CREATED'] == parent.CREATED
    assert ns['RELEASED'] == parent.RELEASED
    assert ns['approved'] is parent._approved_cycle
    assert ns['__file__'] == parent._prior.__file__
    assert parent._previous.CREATED != parent.CREATED
    assert parent._previous.RELEASED != parent.RELEASED
    assert parent._previous.RUN.name == 'api-parent-cycle-r1'
    assert parent._previous.RUN.parent.name == 'software-benchmark-v085'
    assert parent.stop_empty.__globals__ is ns


def test_exact_scope_cannot_be_expanded_or_adopt_an_existing_object():
    refs = dict(source={'s': 1}, prior_authority={'a': 2}, prior_release={'r': 3})
    value = {'version': parent.CYCLE_VERSION, 'status': 'approved_by_existing_explicit_scope',
        'source': refs['source'], 'original_authorization': refs['prior_authority'],
        'predecessor_released': refs['prior_release'], 'slice': parent.SLICE,
        'memory_max_bytes': parent.MEMORY_BYTES, 'memory_swap_max_bytes': 0,
        'tasks_max': parent.TASKS_MAX, 'simultaneous_objects': 1,
        'adopt_existing_object': False, 'modify_existing_host_configuration': False}
    assert parent.validate_cycle(value, **refs) == value
    for change in ({'memory_max_bytes': parent.MEMORY_BYTES + 1},
                   {'adopt_existing_object': True}, {'predecessor_released': {'other': True}}):
        with pytest.raises(PermissionError):
            parent.validate_cycle({**value, **change}, **refs)
