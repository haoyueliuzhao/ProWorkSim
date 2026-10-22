"""Zero-model inventory, priority floor, and worker-routing controls."""
import argparse
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from proworksim import software_benchmark_preparation_priority_v055_r1 as p
from proworksim import software_benchmark_queue_native_host_v055_r5 as host
from proworksim import software_benchmark_queue_native_host_v055_r4 as disk
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def fixture():
    names=['ready','failed','cold-first','cold-second','cold-third']
    old={'rows':[{'slot':{'instance_id':name,'arm':arm},'generation':{'status':'pending'}}
                 for name in names for arm in ('REF','MATCH','PROJECT')]}
    new={'rows':[{'slot':{'instance_id':name},'generation':{'status':'pending'}} for name in names],
         'preparation':{name:{'readiness':{'status':'qualified' if name=='ready' else 'failed' if name=='failed' else 'pending'}} for name in names}}
    return old,new


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    checks=[]; old,new=fixture()
    demand=p.preparation_demand(old,new)
    assert demand['selected_task_ids']==['cold-first'] and demand['priority_reserve_required']
    checks.append('one_ready_replenishes_first_cold_skips_failed_and_deduplicates_three_consumers')
    new['preparation']['ready']['readiness']['status']='pending'
    demand2=p.preparation_demand(old,new)
    assert demand2['selected_task_ids']==['ready','cold-first']
    checks.append('zero_ready_caps_distinct_cold_selection_at_two_original_order')
    new['preparation']['ready']['readiness']['status']='qualified'
    new['preparation']['cold-first']['worker']={'status':'running'}
    underway=p.preparation_demand(old,new)
    assert underway['selected_task_ids']==[] and not underway['priority_reserve_required']
    checks.append('durable_preparation_counts_toward_inventory_and_releases_priority_hold')
    for row in old['rows']:
        row['scores']={'ignored':'any model outcome'}
    assert p.preparation_demand(old,new)==underway
    checks.append('score_fields_do_not_change_inventory_selection')
    G=disk.GiB
    boundary=disk.admission(276*G,0,20*G,kind='generation')
    assert p.priority_admission(boundary,demand)['admitted']
    below=disk.admission(276*G-1,0,20*G,kind='generation')
    gate=p.priority_admission(below,demand)
    assert not gate['admitted'] and gate['minimum_remaining_bytes']==256*G
    assert p.priority_admission(below,underway)['admitted']
    checks.append('priority_256GiB_replaces_100GiB_floor_without_extra_100_and_stops_at_minus_one')
    malformed=p.priority_admission({'kind':'generation','admitted':False},demand)
    assert not malformed['admitted'] and malformed['priority_capacity_metadata_missing']
    checks.append('missing_capacity_metadata_defers_without_exception')
    # r5 may bypass only the aggregate unused-ready count; it still uses original
    # worker launch and holds the common disk lock through durable intent.
    old,new=fixture();subject=host.NativeHostCoordinator.__new__(host.NativeHostCoordinator)
    subject.state=new;subject.revision_ref={'test':'only'};subject._preparation_disk_closed=False
    subject._priority_demand=demand
    subject.disk_admitted=lambda *a,**k:{'admitted':True,'kind':'preparation'}
    lock_events=[];launched=[]
    class Lock:
        def __enter__(self):lock_events.append('lock')
        def __exit__(self,*args):lock_events.append('unlock')
    def launch(self,name):
        assert lock_events[-1]=='lock'
        launched.append(name)
        self.state['preparation'][name]['worker']={'status':'running'}
    with patch.object(host.previous,'disk_dispatch_lock',return_value=Lock()), \
         patch.object(host.backlog,'prewarm_backlog',return_value={'admit_new_preparation':False,'unused_ready_tasks':127}), \
         patch.object(host.original.Coordinator,'launch_preparation',launch):
        subject.launch_preparation('cold-first')
        subject.launch_preparation('cold-third')
    assert launched==['cold-first'] and lock_events==['lock','unlock','lock','unlock']
    checks.append('starving_consumer_bypasses_large_aggregate_backlog_only_for_selected_template_under_same_lock')
    source_refs=[reference(p.__file__),reference(host.__file__),reference(__file__)]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    print(write_new(args.output,{'version':'v055-shared-preparation-priority-cpu-control-r1','passed':True,
        'checks':checks,'sources':source_refs,'model_calls':0,'actual_worker_launches':0,'rootfs_deletions':0,
        'formal_queue_writes':0,'actual_preparations':0}))

if __name__=='__main__':main()
