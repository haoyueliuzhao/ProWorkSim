"""Place only future DeepSeek generation workers on a qualified secondary volume.

The original queue state, lock, cash ledger, scoring and preparation stay on the
primary volume. Existing workers are adopted by their recorded absolute paths.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from . import software_benchmark_queue_native_host_v055_r6 as previous
from . import software_benchmark_queue_native_host_v055_r4 as base_disk_host
from . import software_benchmark_disk_volumes_v055_r1 as volumes
from . import software_benchmark_preparation_priority_v055_r1 as priority
from . import software_benchmark_queue_v055 as original
from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_queue_v055 import ROOT,load,now
from .storage import digest

VERSION='v055-native-r3-solver-secondary-generation-host-r7'


def check_qualification(ref):
    value=load(ref)
    zero_model=(value.get('model_calls')==0 or
        (value.get('version')=='v055-data1-single-native-host-control-r1'
         and value.get('real_API_calls')==0 and value.get('formal_3000_claims')==0
         and value.get('official_grader_calls')==0))
    if (not (value.get('passed') is True or value.get('admitted') is True) or not zero_model
            or value.get('bind')!=str(volumes.SECONDARY_ROOT)
            or value.get('existing_data_moved') is not False
            or value.get('primary_device')==value.get('secondary_device')):
        raise ValueError('Secondary generation requires explicit zero-model qualified placement')
    return value


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self,revision_ref):
        self.revision_ref,self.revision=revision_ref,load(revision_ref)
        predecessor=load(self.revision['predecessor_revision'])
        if (self.revision.get('version')!=VERSION or predecessor.get('version')!=previous.VERSION
                or self.revision['original_plan']!=predecessor['original_plan']
                or self.revision['activation']!=predecessor['activation']
                or self.revision['disk_policy']!=volumes.POLICY
                or self.revision['disk_volume_policy']!=volumes.VOLUME_POLICY
                or self.revision['unused_ready_backlog_limit']!=8):
            raise ValueError('Secondary host must retain the qualified scientific configuration')
        for item in self.revision['files']:checked(item)
        check_qualification(self.revision['cross_volume_qualification'])
        volumes.configure(self.revision['volume_manifest'])
        self.activation=self.activation_ref=None
        self._manifest_costs={}
        self._generation_disk_closed=self._preparation_disk_closed=False
        self._priority_demand=None;self._candidate_arm=None
        self._target_volume='primary'
        original.Coordinator.__init__(self,self.revision['original_plan'])
        self.load_activation()
        history=self.state.setdefault('host_revision_history',[])
        if not history or history[-1]['revision']!=revision_ref:
            history.append({'revision':revision_ref,'adopted_utc':now(),
                'existing_worker_jobs_unchanged':True,'entered_slots_replayed':0})
        self.state['active_host_revision']=revision_ref
        self.state['MATCH_dispatch_hold']=False
        self.state['future_generation_volume']={'name':'secondary','root':str(volumes.SECONDARY_ROOT),
            'manifest':self.revision['volume_manifest'],'queue_state_and_ledger_remain_primary':True}
        self.save()

    def disk_snapshot(self):
        self._priority_demand=None
        try:
            old=json.loads((ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
            snapshot=volumes.shared_disk_snapshot(v055_state=self.state,v054_state=old,
                cache=self._manifest_costs,target_volume=self._target_volume)
            self._priority_demand=priority.preparation_demand(old,self.state)
            self.state['shared_preparation_demand']=self._priority_demand
            snapshot['preparation_priority']=self._priority_demand
            return snapshot
        except (OSError,ValueError,KeyError,TypeError) as error:
            snapshot=volumes.shared_disk_snapshot(v055_state=self.state,cache=self._manifest_costs,
                target_volume=self._target_volume)
            snapshot['metadata_error']={'type':type(error).__name__,'message':str(error)}
            return snapshot

    def disk_admitted(self,instance_id,*,kind):
        # Use the original floor arithmetic and current per-volume snapshot.
        # The r5 cold-prep 256GiB priority belongs only to the primary device.
        gate=base_disk_host.NativeHostCoordinator.disk_admitted(self,instance_id,kind=kind)
        gate['target_volume']=self._target_volume
        if self._priority_demand is None:
            gate.update(admitted=False,priority_observation_missing=True)
        elif self._target_volume=='primary':
            gate=priority.priority_admission(gate,self._priority_demand)
        else:
            gate.update(preparation_priority=self._priority_demand,
                        primary_preparation_priority_not_charged_to_secondary=True)
        self.state['last_disk_dispatch_admission']=gate
        return gate

    def launch(self,row,record,*,kind,request=None):
        if kind!='generation':
            return super().launch(row,record,kind=kind,request=request)
        if record['status']!='pending':
            raise ValueError('Secondary placement cannot replay an entered generation')
        # A moved launch root must not evade an old durable/pre-intent directory.
        suffix=digest((row['slot']['slot_id']+'-generation').encode())[:24]
        previous_directory=self.root/'workers'/('generation-'+suffix)
        if previous_directory.exists():
            self.defer(row,record,'preexisting_primary_generation_directory_requires_explicit_recovery')
            self.save()
            return
        saved_root,saved_target=self.root,self._target_volume
        self.root=volumes.SECONDARY_ROOT
        self._target_volume='secondary'
        try:
            # Parent is unchanged: same slot/config/solver/systemd builder and
            # same cross-host disk lock through durable intent and worker launch.
            return super().launch(row,record,kind=kind,request=request)
        finally:
            self.root,self._target_volume=saved_root,saved_target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    p=commands.add_parser('freeze')
    p.add_argument('--predecessor',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--volumes',required=True,type=Path);p.add_argument('--qualification',required=True,type=Path)
    p.add_argument('--previous-controller',required=True)
    p=commands.add_parser('run');p.add_argument('--revision',required=True,type=Path);p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.operation=='freeze':
        oldref=reference(args.predecessor);old=load(oldref)
        if old['version']!=previous.VERSION:raise ValueError('Require sealed r6 predecessor')
        manifest=reference(args.volumes);qualification=reference(args.qualification)
        check_qualification(qualification);volumes.configure(manifest)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        print(json.dumps(write_new(args.output,{'version':VERSION,'created_utc':now(),
            'predecessor_revision':oldref,'original_plan':old['original_plan'],'activation':old['activation'],
            'disk_policy':volumes.POLICY,'disk_volume_policy':volumes.VOLUME_POLICY,
            'volume_manifest':manifest,'cross_volume_qualification':qualification,
            'unused_ready_backlog_limit':8,'previous_controller_unit':args.previous_controller,
            'future_generation_root':str(volumes.SECONDARY_ROOT),
            'files':[reference(__file__),reference(ROOT/'tools/run_deepseek_queue_native_host_v055_r7.py'),
                     reference(volumes.__file__),*old['files']],
            'existing_worker_directories_moved':False,'scientific_configuration_unchanged':True,
            'existing_workers_adopted':True,'model_calls':0,'automatic_model_replay':False})))
        return
    ref=reference(args.revision)
    if ref['sha256']!=args.sha256:raise ValueError('Secondary host revision SHA mismatch')
    coordinator=NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():time.sleep(5)
    finally:coordinator.lease.close()


if __name__=='__main__':main()
