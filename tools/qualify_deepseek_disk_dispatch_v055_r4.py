"""Zero-model CPU boundary controls for disk reservation host r4."""
import argparse
import fcntl
from pathlib import Path
from unittest.mock import patch

from proworksim import software_benchmark_queue_native_host_v055_r4 as guard
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    checks = []
    G = guard.GiB
    assert guard.admission(120*G, 0, 20*G, kind='generation')['admitted']
    assert not guard.admission(120*G-1, 0, 20*G, kind='generation')['admitted']
    assert guard.admission(256*G, 0, 128*G, kind='preparation')['admitted']
    assert not guard.admission(256*G-1, 0, 128*G, kind='preparation')['admitted']
    checks.append('inclusive_generation_100GiB_and_preparation_128GiB_floors')
    assert guard.generation_reservation({'regular_file_bytes':2*G, 'entries':[{},{}]}) == 12*G+32768
    checks.append('two_clones_block_metadata_and_workspace_margin')
    def row(name, state='pending'):
        return {'slot': {'slot_id':name, 'instance_id':name}, 'generation': {'status':state}, 'scores':[]}
    state = {'rows':[row('new-active','running'), row('new-done','closed')],
             'preparation': {'prep':{'worker':{'status':'running'}}}}
    old = {'rows':[row('old-active','intent'), row('old-done','closed')]}
    with patch.object(guard, 'generation_estimate', return_value={'peak_bytes':20*G}):
        snapshot = guard.shared_disk_snapshot(v055_state=state,v054_state=old,cache={})
    assert snapshot['active_peak_reserved_bytes'] == 168*G and snapshot['metadata_error'] is None
    checks.append('both_queues_active_intents_plus_cold_prewarmer_charged_terminal_released')
    def snapshot_for(state):
        return {'free_bytes':200*G, 'active_peak_reserved_bytes':sum(r['generation']['status']=='running' for r in state['rows'])*20*G,
                'metadata_error':None}
    subject=guard.NativeHostCoordinator.__new__(guard.NativeHostCoordinator)
    subject.state={'rows':[row('task'+str(i)) for i in range(10)]}
    subject.revision_ref={'path':'cpu-only','sha256':'cpu-only','bytes':0}
    subject._generation_disk_closed=False
    subject.disk_snapshot=lambda:snapshot_for(subject.state)
    subject.template_reservation=lambda _: {'peak_bytes':20*G}
    launched=[]
    def fake_launch(self, row, record, *, kind, request=None):
        launched.append(kind)
        record['status']='running'
    with patch.object(guard.previous.NativeHostCoordinator,'launch',fake_launch):
        for item in subject.state['rows']:
            subject.launch(item,item['generation'],kind='generation')
        assert sum(r['generation']['status']=='running' for r in subject.state['rows']) == 5
        assert sum(r['generation']['status']=='pending' for r in subject.state['rows']) == 5
        subject.launch(subject.state['rows'][0],{},kind='score',request={'unchanged':True})
    assert launched == ['generation']*5+['score']
    checks.append('constant_free_async_burst_stops_after_five_durable_intents_scores_continue')
    subject._generation_disk_closed=False
    subject.state['rows'][0]['generation']['status']='closed'
    with patch.object(guard.previous.NativeHostCoordinator,'launch',fake_launch):
        subject.launch(subject.state['rows'][5],subject.state['rows'][5]['generation'],kind='generation')
    assert subject.state['rows'][5]['generation']['status']=='running'
    checks.append('terminal_collection_releases_reservation_without_replaying_previous_jobs')
    subject._generation_disk_closed=False
    subject.disk_snapshot=lambda:{'free_bytes':999*G,'active_peak_reserved_bytes':0,'metadata_error':{'reason':'missing_peer'}}
    with patch.object(guard.previous.NativeHostCoordinator,'launch',side_effect=AssertionError('must not launch')):
        subject.launch(subject.state['rows'][6],subject.state['rows'][6]['generation'],kind='generation')
    assert subject.state['rows'][6]['generation']['status']=='pending'
    checks.append('missing_peer_metadata_keeps_slot_pending_without_side_effects')
    with guard.disk_dispatch_lock():
        with (guard.ROOT/'runs/software-benchmark-v055/disk-dispatch-r4.lock').open('a+b') as other:
            try:
                fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                checks.append('shared_flock_excludes_independent_open_description')
            else:
                raise AssertionError('shared lock failed')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    receipt=write_new(args.output, {'version':'v055-disk-dispatch-host-r4-cpu-control','passed':True,
        'checks':checks,'model_calls':0,'grader_calls':0,'worker_launches':0,'real_queue_writes':0,
        'sources':[reference(guard.__file__),reference(__file__)]})
    print(receipt)

if __name__=='__main__':
    main()
