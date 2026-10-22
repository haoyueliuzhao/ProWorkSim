"""Shared-template replenishment based only on consumer inventory and frozen order."""
from __future__ import annotations
from .software_benchmark_queue_native_host_v055_r4 import POLICY

VERSION = 'v055-multi-consumer-preparation-priority-r1'
READY_TARGET = 2
MAX_SELECTED = 2


def preparation_demand(v054_state, v055_state):
    """Supplement the new producer's backlog rule for any starving old consumer.

    Pending qualified tasks and already preparing tasks both count toward two
    future tasks. Failed environments are deferred, never selected for retries.
    Scores, candidate contents, and model answers are never inspected.
    """
    preparations = v055_state['preparation']
    order = {}
    for row in v055_state['rows']:
        name = row['slot']['instance_id']
        order.setdefault(name, len(order))
    running = {name for name, record in preparations.items()
               if record.get('worker', {}).get('status') == 'running'
               or record['readiness']['status'] == 'preparing'}
    selected, inventories = set(), {}
    for arm in ('REF', 'MATCH', 'PROJECT'):
        pending = [row['slot']['instance_id'] for row in v054_state['rows']
                   if row['slot']['arm'] == arm and row['generation']['status'] == 'pending']
        qualified = [name for name in pending if preparations[name]['readiness']['status'] == 'qualified']
        preparing = [name for name in pending if name in running]
        # Qualified and preparing are disjoint for inventory accounting.
        preparing = [name for name in preparing if name not in qualified]
        cold = [name for name in pending if preparations[name]['readiness']['status'] == 'pending'
                and name not in running]
        needed = max(0, READY_TARGET - len(qualified) - len(preparing))
        requested = cold[:needed]
        selected.update(requested)
        inventories[arm] = {'pending_qualified':len(qualified),'pending_preparing':len(preparing),
            'target_inventory':READY_TARGET,'shortfall':needed,'requested_cold_tasks':requested}
    selected = sorted(selected, key=order.__getitem__)[:MAX_SELECTED]
    return {'version':VERSION,'selected_task_ids':selected,'consumer_inventory':inventories,
        'running_preparation_count':len(running),'priority_reserve_required':bool(selected) and not running,
        'maximum_selected_cold_templates':MAX_SELECTED,
        'original_v055_unused_ready_backlog_rule_retained':True,
        'failed_templates_retried':False,'model_scores_used':False}


def priority_admission(base_gate, demand):
    gate = dict(base_gate)
    gate['preparation_priority'] = demand
    if gate.get('kind') == 'generation' and demand['priority_reserve_required']:
        if not {'minimum_remaining_bytes','estimated_unreserved_bytes_after_launch','admitted'} <= gate.keys():
            gate.update(admitted=False,priority_capacity_metadata_missing=True)
            return gate
        floor = max(gate['minimum_remaining_bytes'],
                    POLICY['cold_preparation_reservation_bytes'] + POLICY['preparation_floor_bytes'])
        gate.update(minimum_remaining_bytes=floor,
                    admitted=gate['admitted'] and gate['estimated_unreserved_bytes_after_launch'] >= floor,
                    preparation_launch_space_preserved=True)
    return gate
