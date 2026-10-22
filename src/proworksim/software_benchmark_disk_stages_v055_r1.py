"""Reserve remaining disk growth after verified host clone publications.

Completed allocations already reduce actual free space. No live filesystem tree
is walked, no payload is deleted, and absent/invalid publication evidence never
earns a stage discount. This module keeps the original shared lock and floors.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import stat

from . import software_benchmark_queue_native_host_v055_r4 as original
from .software_benchmark_queue_v055 import ROOT, now, load
from .storage import digest

VERSION='v055-disk-remaining-growth-stages-r1'
POLICY=original.POLICY
disk_dispatch_lock=original.disk_dispatch_lock
admission=original.admission
STAGE_POLICY={
    'version':VERSION,'native_requested_clone_count':1,'project_requested_clone_count':2,
    'workspace_margin_bytes':POLICY['generation_workspace_margin_bytes'],
    'main_clone_discount_requires_host_publication_sha256':True,
    'project_future_test_clone_always_reserved':True,
    'cold_preparation_reservation_bytes':POLICY['cold_preparation_reservation_bytes'],
    'prepared_cache_requires_exact_baseline_mapping':True,
    'prepared_cache_future_initialization_clones':1,
    'unknown_or_invalid_stage_evidence_retains_full_reservation':True,
    'generation_floor_bytes':POLICY['generation_floor_bytes'],
    'preparation_floor_bytes':POLICY['preparation_floor_bytes'],
    'full_active_tree_walks':False,'actor_or_scientific_configuration_changed':False}


def generation_estimate(instance_id,v055_state,cache,*,arm=None):
    # The old Qwen caller has no selected-arm argument. Its fresh launches remain
    # conservatively at two clones; active rows always carry their actual arm.
    base=dict(original.generation_estimate(instance_id,v055_state,cache))
    clones=1 if arm in ('REF','MATCH') else 2
    clone=base['regular_file_bytes']+base['entry_count']*POLICY['entry_overhead_bytes']
    base.update(peak_bytes=clones*clone+POLICY['generation_workspace_margin_bytes'],
                clone_bytes=clone,requested_clones=clones,arm=arm,stage_policy=VERSION)
    return base


def _identity(path,maximum):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size>maximum:
        raise ValueError('Host stage evidence must be bounded regular metadata')
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)


def _publication(actor_directory,instance_id,cache,*,source_sha=None,mapping=None):
    """A publication is written only after the original synchronous copy/extract."""
    directory=Path(actor_directory)
    if directory.resolve()!=directory or not directory.is_relative_to(ROOT/'runs'):
        raise ValueError('Clone evidence escaped its expected host directory')
    public=directory/'public-environment.json';manifest_path=directory/'rootfs-manifest.json'
    public_id=_identity(public,1024**2);manifest_id=_identity(manifest_path,64*1024**2)
    key='disk-stage:'+str(public)
    cached=cache.get(key)
    binding={'source_sha':source_sha,'mapping':mapping,'instance_id':instance_id}
    if cached and cached['public_identity']==public_id and cached['manifest_identity']==manifest_id and cached['binding']==binding:
        return cached['proof']
    public_raw=public.read_bytes();pub=json.loads(public_raw)
    if pub.get('rootfs_manifest')!=str(manifest_path):
        raise ValueError('Published rootfs manifest points to another clone')
    raw=manifest_path.read_bytes();sha=digest(raw)
    if pub.get('rootfs_manifest_sha256')!=sha:
        raise ValueError('Clone publication is incomplete or its manifest SHA changed')
    value=json.loads(raw)
    if (value.get('version')!='v054-native-rootfs-v1' or value.get('instance_id')!=instance_id
            or value.get('prepared_root')!=str(directory/'rootfs')
            or value.get('numeric_ownership_equivalence_admitted') is not True
            or (source_sha is not None and value.get('cloned_from_manifest_sha256')!=source_sha)
            or (mapping is not None and value.get('baseline_mapping')!=mapping)):
        raise ValueError('Published task, target, template, or ownership evidence differs')
    size,entries=value.get('regular_file_bytes'),value.get('entries')
    if type(size) is not int or size<0 or not isinstance(entries,list):
        raise ValueError('Published template lacks size metadata')
    if _identity(public,1024**2)!=public_id or _identity(manifest_path,64*1024**2)!=manifest_id:
        raise ValueError('Host publication changed while observed')
    proof={'public_environment':{'path':str(public),'sha256':digest(public_raw),'bytes':len(public_raw)},
           'manifest':{'path':str(manifest_path),'sha256':sha,'bytes':len(raw)},
           'instance_id':instance_id,'prepared_root':value['prepared_root'],
           'clone_bytes':size+len(entries)*POLICY['entry_overhead_bytes'],
           'cloned_from_manifest_sha256':value.get('cloned_from_manifest_sha256'),
           'actual_allocated_bytes_not_estimated_or_subtracted':True}
    cache[key]={'public_identity':public_id,'manifest_identity':manifest_id,'binding':binding,'proof':proof}
    return proof


def _active_generation(row,state,cache,*,family):
    slot=row['slot'];record=row['generation'];instance=slot['instance_id'];arm=slot['arm']
    base={'slot_id':slot['slot_id'],'instance_id':instance,'arm':arm,'family':family}
    try:
        estimate=generation_estimate(instance,state,cache,arm=arm)
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {**base,'peak_bytes':POLICY['unknown_generation_reservation_bytes'],
                'stage':'unknown_template_full_fallback','observation_error':type(error).__name__}
    remaining=estimate['requested_clones'];proof=None;reason=None
    try:
        episode=Path(record['episode_output']) if family=='v054' else Path(record['directory'])/'episode'
        allowed=ROOT/('runs/software-benchmark-v054' if family=='v054' else 'runs/software-benchmark-v055')
        if episode.resolve()!=episode or not episode.is_relative_to(allowed):
            raise ValueError('Activity output is outside its exact experiment root')
        proof=_publication(episode/'actor',instance,cache,source_sha=estimate['rootfs_manifest']['sha256'])
        remaining-=1
    except (OSError,ValueError,KeyError,TypeError) as error:
        reason=type(error).__name__
    return {**base,'peak_bytes':remaining*estimate['clone_bytes']+POLICY['generation_workspace_margin_bytes'],
            'stage':'main_clone_materialized' if proof else 'main_clone_not_yet_proven',
            'remaining_future_clones':remaining,'clone_bytes':estimate['clone_bytes'],
            'workspace_margin_bytes':POLICY['generation_workspace_margin_bytes'],
            'phase_proof':proof,'observation_error':reason,
            'previous_full_two_clone_peak_bytes':2*estimate['clone_bytes']+POLICY['generation_workspace_margin_bytes']}


def _preparation_request(instance,record,cache):
    worker=record['worker'];job_ref=worker['job'];key='disk-stage-request:'+job_ref['sha256']
    if key in cache:return cache[key]
    job=load(job_ref);argv=job['argv'];directory=Path(worker['directory'])
    path=Path(argv[argv.index('--request')+1]);sha=argv[argv.index('--sha256')+1]
    if path!=directory/'request.json' or not directory.is_relative_to(ROOT/'runs/software-benchmark-v055/queue-r1/workers'):
        raise ValueError('Preparation request escaped the frozen worker intent')
    raw=path.read_bytes()
    if digest(raw)!=sha:raise ValueError('Preparation request SHA differs from frozen intent')
    request=json.loads(raw)
    if request['instance_id']!=instance or job['instance_id']!=instance:
        raise ValueError('Preparation intent belongs to another task')
    cache_root=ROOT/'runs/software-benchmark-v054/native-lazy-cache'
    if request['cache_root']!=str(cache_root):raise ValueError('Preparation cache changed')
    result={'request':request,'reference':{'path':str(path),'sha256':sha,'bytes':len(raw)},
            'cache_directory':cache_root/instance/request['baseline_mapping']['sha256'][:16]}
    cache[key]=result
    return result


def _active_preparation(instance,record,cache):
    row={'instance_id':instance,'peak_bytes':POLICY['cold_preparation_reservation_bytes'],
         'stage':'cold_export_or_unproven_preparation','phase_proof':None}
    try:
        intent=_preparation_request(instance,record,cache);directory=intent['cache_directory']
        prepared=_publication(directory,instance,cache,mapping=intent['request']['baseline_mapping'])
        row.update(peak_bytes=prepared['clone_bytes']+POLICY['generation_workspace_margin_bytes'],
                   stage='cache_materialized_initialization_clone_remaining',phase_proof=prepared,
                   request=intent['reference'],remaining_future_clones=1)
        try:
            initialized=_publication(directory/'initialization/clone',instance,cache,
                                     source_sha=prepared['manifest']['sha256'])
            row.update(peak_bytes=POLICY['generation_workspace_margin_bytes'],
                       stage='initialization_clone_materialized',initialization_phase_proof=initialized,
                       remaining_future_clones=0)
        except (OSError,ValueError,KeyError,TypeError) as error:
            row['initialization_observation_error']=type(error).__name__
    except (OSError,ValueError,KeyError,TypeError) as error:
        row['observation_error']=type(error).__name__
    return row


def shared_disk_snapshot(*,v055_state=None,v054_state=None,cache=None):
    """Same lock protocol; shared current free minus only future admitted growth."""
    cache={} if cache is None else cache
    generations=[];preparations=[];legacy=[];error=None
    try:
        if v055_state is None:v055_state=json.loads((ROOT/'runs/software-benchmark-v055/queue-r1/state.json').read_bytes())
        if v054_state is None:v054_state=json.loads((ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
        for state,target,family in ((v055_state,generations,'v055'),(v054_state,legacy,'v054')):
            for row in state['rows']:
                if row['generation']['status'] in ('intent','running'):
                    target.append(_active_generation(row,v055_state,cache,family=family))
        for name,record in v055_state['preparation'].items():
            if record.get('worker',{}).get('status')=='running':
                preparations.append(_active_preparation(name,record,cache))
    except (OSError,ValueError,KeyError,TypeError) as caught:
        error={'type':type(caught).__name__,'message':str(caught)}
    rows=[*generations,*preparations,*legacy]
    return {'observed_utc':now(),'policy':POLICY,'stage_policy':STAGE_POLICY,'free_bytes':shutil.disk_usage(ROOT).free,
            'active_peak_reserved_bytes':sum(row['peak_bytes'] for row in rows),
            'v055_generations':generations,'v055_preparations':preparations,
            'v054_generations':legacy,'metadata_error':error,
            'original_full_reservation_bytes_for_same_active_jobs':
                sum(row.get('previous_full_two_clone_peak_bytes',row['peak_bytes']) for row in [*generations,*legacy])
                +len(preparations)*POLICY['cold_preparation_reservation_bytes'],
            'already_materialized_growth_not_reserved_again':True}
