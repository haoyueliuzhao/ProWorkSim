"""Zero-worker routing controls for the independently qualified secondary mount."""
import argparse
from pathlib import Path
from unittest.mock import patch
from proworksim import software_benchmark_queue_native_host_v055_r7 as h
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.storage import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--volumes',required=True,type=Path);parser.add_argument('--qualification',required=True,type=Path)
    args=parser.parse_args();args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=False)
    registration=h.volumes.configure(reference(args.volumes));qualification=h.check_qualification(reference(args.qualification))
    assert qualification['secondary_device']==registration['identity']['secondary']['device']
    checks=[];co=h.NativeHostCoordinator.__new__(h.NativeHostCoordinator)
    co.root=args.output.parent/'primary-queue';co.root.mkdir();co._target_volume='primary'
    co.state_path=co.root/'state.json';original_root=co.root;original_state_path=co.state_path
    row={'slot':{'slot_id':'routing-control-only','arm':'MATCH'},'generation':{'status':'pending'}}
    observations=[]
    def launch(self,row,record,*,kind,request=None):
        observations.append({'root':str(self.root),'target':self._target_volume,'kind':kind,'state_path':str(self.state_path)})
    with patch.object(h.previous.NativeHostCoordinator,'launch',launch):
        co.launch(row,row['generation'],kind='generation')
        assert co.root==original_root and co._target_volume=='primary' and co.state_path==original_state_path
        co.launch(row,{},kind='score',request={'fixture':True})
    assert observations[0]['root']==str(h.volumes.SECONDARY_ROOT) and observations[0]['target']=='secondary'
    assert observations[1]['root']==str(original_root) and observations[1]['target']=='primary'
    checks.append('only_future_generation_root_secondary_score_and_state_path_primary')
    with patch.object(h.previous.NativeHostCoordinator,'launch',side_effect=RuntimeError('fixture')):
        try:co.launch(row,row['generation'],kind='generation')
        except RuntimeError:pass
    assert co.root==original_root and co._target_volume=='primary'
    checks.append('routing_context_restored_even_if_launch_raises')
    G=1024**3;co.state={};co._priority_demand={'priority_reserve_required':True}
    base={'kind':'generation','admitted':True,'minimum_remaining_bytes':100*G,
          'estimated_unreserved_bytes_after_launch':200*G}
    with patch.object(h.base_disk_host.NativeHostCoordinator,'disk_admitted',return_value=base):
        co._target_volume='secondary';secondary=co.disk_admitted('fixture',kind='generation')
        assert secondary['admitted'] and secondary['minimum_remaining_bytes']==100*G
    with patch.object(h.base_disk_host.NativeHostCoordinator,'disk_admitted',return_value=dict(base)):
        co._target_volume='primary';primary=co.disk_admitted('fixture',kind='generation')
        assert not primary['admitted'] and primary['minimum_remaining_bytes']==256*G
    checks.append('secondary_100GiB_floor_separate_from_primary_prewarm_256GiB_priority')
    row['generation']['status']='running'
    try:co.launch(row,row['generation'],kind='generation')
    except ValueError:pass
    else:raise AssertionError('Entered generation replay accepted')
    row['generation']['status']='pending';suffix=digest((row['slot']['slot_id']+'-generation').encode())[:24]
    (co.root/'workers'/('generation-'+suffix)).mkdir(parents=True)
    co.state={'exceptions':[]};co.save=lambda:None
    with patch.object(h.previous.NativeHostCoordinator,'launch',side_effect=AssertionError('old intent must not relaunch')):
        co.launch(row,row['generation'],kind='generation')
    assert row['generation']['status']=='technical_unknown' and len(co.state['exceptions'])==1
    checks.append('entered_slots_and_preexisting_primary_directory_never_replayed_on_new_volume')
    assert h.NativeHostCoordinator.tick is h.previous.NativeHostCoordinator.tick
    checks.append('original_CPU_RAM_budget_API_tick_and_collection_unchanged')
    print(write_new(args.output,{'version':'v055-secondary-generation-routing-cpu-control-r7','passed':True,
        'checks':checks,'sources':[reference(h.__file__),reference(h.volumes.__file__),reference(__file__)],
        'volume_registration':reference(args.volumes),'cross_volume_qualification':reference(args.qualification),
        'registered_device_check_passed':True,'model_calls':0,'worker_launches':0,'real_queue_writes':0,
        'existing_payloads_moved':0}))

if __name__=='__main__':main()
