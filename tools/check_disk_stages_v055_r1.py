"""Small host-publication fixtures; no real clone, model, grader or deletion."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from proworksim import software_benchmark_disk_stages_v055_r1 as d
from proworksim import software_benchmark_preparation_priority_v055_r1 as priority
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.storage import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    args.output=args.output.resolve()
    args.output.parent.mkdir(parents=True,exist_ok=False)
    fixture=args.output.parent/'fixture';fixture.mkdir()
    G=1024**3;clone=3*G+10*8192;source_sha='a'*64;instance='fixture__only-1';checks=[]
    raw_estimate={'peak_bytes':2*clone+8*G,'regular_file_bytes':3*G,'entry_count':10,'rootfs_manifest':{'sha256':source_sha}}
    with patch.object(d.original,'generation_estimate',return_value=raw_estimate):
        assert d.generation_estimate(instance,{}, {},arm='REF')['peak_bytes']==clone+8*G
        assert d.generation_estimate(instance,{}, {},arm='MATCH')['peak_bytes']==clone+8*G
        assert d.generation_estimate(instance,{}, {},arm='PROJECT')['peak_bytes']==2*clone+8*G
        assert d.generation_estimate(instance,{}, {})['peak_bytes']==2*clone+8*G
    checks.append('native_one_requested_clone_project_two_and_unknown_arm_conservative_two')
    def publish(directory,*,cloned=None,mapping=None):
        directory.mkdir(parents=True,exist_ok=True)
        value={'version':'v054-native-rootfs-v1','instance_id':instance,'prepared_root':str(directory/'rootfs'),
            'numeric_ownership_equivalence_admitted':True,'regular_file_bytes':3*G,'entries':[{}]*10}
        if cloned:value['cloned_from_manifest_sha256']=cloned
        if mapping:value['baseline_mapping']=mapping
        raw=json.dumps(value).encode();(directory/'rootfs-manifest.json').write_bytes(raw)
        pub={'rootfs_manifest':str(directory/'rootfs-manifest.json'),'rootfs_manifest_sha256':digest(raw)}
        (directory/'public-environment.json').write_text(json.dumps(pub))
        return digest(raw)
    episode=fixture/'episode';actor=episode/'actor';publish(actor,cloned=source_sha)
    proof=d._publication(actor,instance,{},source_sha=source_sha)
    assert proof['clone_bytes']==clone
    for wrong in ('b'*64,):
        try:d._publication(actor,instance,{},source_sha=wrong)
        except ValueError:pass
        else:raise AssertionError('Wrong source SHA accepted')
    try:d._publication(actor,'another__task-2',{},source_sha=source_sha)
    except ValueError:pass
    else:raise AssertionError('Wrong task accepted')
    checks.append('full_manifest_hash_task_template_and_target_binding_required')
    row={'slot':{'instance_id':instance,'arm':'REF','slot_id':'fixture'},'generation':{'directory':str(fixture)}}
    with patch.object(d.original,'generation_estimate',return_value=raw_estimate):
        active=d._active_generation(row,{}, {},family='v055');assert active['peak_bytes']==8*G
        row['slot']['arm']='PROJECT';active=d._active_generation(row,{}, {},family='v055')
        assert active['peak_bytes']==clone+8*G and active['remaining_future_clones']==1
        row['generation']['directory']=str(fixture/'not-created')
        fallback=d._active_generation(row,{}, {},family='v055');assert fallback['peak_bytes']==2*clone+8*G
    checks.append('materialized_main_releases_only_main_growth_project_future_test_clone_retained')
    checks.append('missing_publication_keeps_unmaterialized_full_arm_reservation')
    cache_dir=fixture/'cache';mapping={'sha256':'c'*64,'path':'fixture-only','bytes':1}
    request={'request':{'baseline_mapping':mapping},'reference':{'fixture':True},'cache_directory':cache_dir}
    with patch.object(d,'_preparation_request',return_value=request):
        assert d._active_preparation(instance,{}, {})['peak_bytes']==128*G
        cache_sha=publish(cache_dir,mapping=mapping)
        assert d._active_preparation(instance,{}, {})['peak_bytes']==clone+8*G
        publish(cache_dir/'initialization/clone',cloned=cache_sha)
        assert d._active_preparation(instance,{}, {})['peak_bytes']==8*G
        (cache_dir/'public-environment.json').write_text('{}')
        assert d._active_preparation(instance,{}, {})['peak_bytes']==128*G
    checks.append('cold_128_prepared_clone_plus_8_initialized_8_invalid_publication_falls_back_128')
    assert d.admission(108*G,0,8*G,kind='generation')['admitted']
    assert not d.admission(108*G-1,0,8*G,kind='generation')['admitted']
    assert d.admission(256*G,0,128*G,kind='preparation')['admitted']
    assert not priority.priority_admission(d.admission(263*G,0,8*G,kind='generation'),{'priority_reserve_required':True})['admitted']
    assert priority.priority_admission(d.admission(264*G,0,8*G,kind='generation'),{'priority_reserve_required':True})['admitted']
    checks.append('original_100_128_floors_and_cold_priority_256_preserved')
    new={'rows':[{'generation':{'status':'running'},'slot':{}}],'preparation':{'preparing':{'worker':{'status':'running'}}}}
    old={'rows':[{'generation':{'status':'intent'},'slot':{}}]}
    with patch.object(d,'_active_generation',side_effect=lambda row,state,cache,family:{'peak_bytes':8*G,'family':family}), \
         patch.object(d,'_active_preparation',return_value={'peak_bytes':8*G}):
        snapshot=d.shared_disk_snapshot(v055_state=new,v054_state=old,cache={})
    assert snapshot['active_peak_reserved_bytes']==24*G and snapshot['metadata_error'] is None
    assert snapshot['v054_generations'][0]['family']=='v054' and snapshot['v055_generations'][0]['family']=='v055'
    checks.append('same_shared_snapshot_accounts_both_hosts_and_active_preparation')
    print(write_new(args.output,{'version':'v055-disk-stage-cpu-control-r1','passed':True,'checks':checks,
        'source':reference(d.__file__),'control':reference(__file__),'model_calls':0,'real_clones':0,
        'real_queue_writes':0,'existing_payload_deletions':0,'full_live_tree_walks':0}))

if __name__=='__main__':main()
