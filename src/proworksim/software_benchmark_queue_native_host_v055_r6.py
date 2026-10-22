"""Phase-aware shared disk admission; scientific solver r3 and prep priority retained."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from . import software_benchmark_queue_native_host_v055_r5 as previous
from . import software_benchmark_disk_stages_v055_r1 as disk
from . import software_benchmark_preparation_priority_v055_r1 as priority
from . import software_benchmark_queue_v055 as original
from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_queue_v055 import ROOT,load,now

VERSION='v055-native-r3-solver-disk-stage-host-r6'


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self,revision_ref):
        self.revision_ref,self.revision=revision_ref,load(revision_ref)
        predecessor=load(self.revision['predecessor_revision'])
        if (self.revision.get('version')!=VERSION or predecessor.get('version')!=previous.VERSION
                or self.revision['original_plan']!=predecessor['original_plan']
                or self.revision['activation']!=predecessor['activation']
                or self.revision['disk_policy']!=disk.POLICY
                or self.revision['disk_stage_policy']!=disk.STAGE_POLICY
                or self.revision['unused_ready_backlog_limit']!=8):
            raise ValueError('Stage host must retain the previous scientific plan and solver')
        for item in self.revision['files']:checked(item)
        self.activation=self.activation_ref=None
        self._manifest_costs={}
        self._generation_disk_closed=self._preparation_disk_closed=False
        self._priority_demand=None;self._candidate_arm=None
        original.Coordinator.__init__(self,self.revision['original_plan'])
        self.load_activation()
        history=self.state.setdefault('host_revision_history',[])
        if not history or history[-1]['revision']!=revision_ref:
            history.append({'revision':revision_ref,'adopted_utc':now(),
                'existing_worker_jobs_unchanged':True,'entered_slots_replayed':0})
        self.state['active_host_revision']=revision_ref
        self.state['MATCH_dispatch_hold']=False
        self.save()

    def template_reservation(self,instance_id):
        return disk.generation_estimate(instance_id,self.state,self._manifest_costs,arm=self._candidate_arm)

    def launch(self,row,record,*,kind,request=None):
        saved=self._candidate_arm
        self._candidate_arm=row['slot']['arm'] if kind=='generation' else None
        try:return super().launch(row,record,kind=kind,request=request)
        finally:self._candidate_arm=saved

    def disk_snapshot(self):
        self._priority_demand=None
        try:
            old=json.loads((ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
            snapshot=disk.shared_disk_snapshot(v055_state=self.state,v054_state=old,cache=self._manifest_costs)
            self._priority_demand=priority.preparation_demand(old,self.state)
            self.state['shared_preparation_demand']=self._priority_demand
            snapshot['preparation_priority']=self._priority_demand
            return snapshot
        except (OSError,ValueError,KeyError,TypeError) as error:
            snapshot=disk.shared_disk_snapshot(v055_state=self.state,cache=self._manifest_costs)
            snapshot['metadata_error']={'type':type(error).__name__,'message':str(error)}
            return snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    p=commands.add_parser('freeze');p.add_argument('--predecessor',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--previous-controller',required=True)
    p=commands.add_parser('run');p.add_argument('--revision',required=True,type=Path);p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.operation=='freeze':
        oldref=reference(args.predecessor);old=load(oldref)
        if old['version']!=previous.VERSION:raise ValueError('Require the sealed r5 predecessor')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        print(json.dumps(write_new(args.output,{'version':VERSION,'created_utc':now(),
            'predecessor_revision':oldref,'original_plan':old['original_plan'],'activation':old['activation'],
            'disk_policy':disk.POLICY,'disk_stage_policy':disk.STAGE_POLICY,'unused_ready_backlog_limit':8,
            'previous_controller_unit':args.previous_controller,
            'files':[reference(__file__),reference(ROOT/'tools/run_deepseek_queue_native_host_v055_r6.py'),
                     reference(disk.__file__),*old['files']],
            'scientific_configuration_unchanged':True,'existing_workers_adopted':True,
            'model_calls':0,'automatic_model_replay':False})))
        return
    ref=reference(args.revision)
    if ref['sha256']!=args.sha256:raise ValueError('Stage host revision SHA mismatch')
    coordinator=NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():time.sleep(5)
    finally:coordinator.lease.close()


if __name__=='__main__':main()
