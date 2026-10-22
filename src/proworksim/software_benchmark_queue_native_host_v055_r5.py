"""One shared template producer serves consumers with different progress rates.

Only future host admission changes. Solver r3, all slots, cash accounting,
existing worker jobs, scoring, and the shared disk lock remain unchanged.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from . import software_benchmark_queue_native_host_v055_r4 as previous
from . import software_benchmark_queue_native_host_v055_r3 as backlog
from . import software_benchmark_queue_v055 as original
from . import software_benchmark_preparation_priority_v055_r1 as priority
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_queue_v055 import ROOT, load, now

VERSION = 'v055-native-r3-solver-shared-preparation-host-r5'


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self, revision_ref):
        self.revision_ref, self.revision = revision_ref, load(revision_ref)
        predecessor = load(self.revision['predecessor_revision'])
        if (self.revision.get('version') != VERSION or predecessor.get('version') != previous.VERSION
                or self.revision['original_plan'] != predecessor['original_plan']
                or self.revision['activation'] != predecessor['activation']
                or self.revision['disk_policy'] != previous.POLICY
                or self.revision['unused_ready_backlog_limit'] != 8):
            raise ValueError('Shared preparation host must retain the qualified solver and original plan')
        for item in self.revision['files']:
            checked(item)
        self.activation = self.activation_ref = None
        self._manifest_costs = {}
        self._generation_disk_closed = self._preparation_disk_closed = False
        self._priority_demand = None
        original.Coordinator.__init__(self, self.revision['original_plan'])
        self.load_activation()
        history = self.state.setdefault('host_revision_history', [])
        if not history or history[-1]['revision'] != revision_ref:
            history.append({'revision':revision_ref,'adopted_utc':now(),
                'existing_worker_jobs_unchanged':True,'entered_slots_replayed':0})
        self.state['active_host_revision'] = revision_ref
        self.state['MATCH_dispatch_hold'] = False
        self.save()

    def disk_snapshot(self):
        # launch callers already hold the common cross-host flock.
        self._priority_demand = None
        try:
            old = json.loads((ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
            snapshot = previous.shared_disk_snapshot(v055_state=self.state,v054_state=old,cache=self._manifest_costs)
            self._priority_demand = priority.preparation_demand(old,self.state)
            self.state['shared_preparation_demand'] = self._priority_demand
            snapshot['preparation_priority'] = self._priority_demand
            return snapshot
        except (OSError,ValueError,KeyError,TypeError) as error:
            snapshot = previous.shared_disk_snapshot(v055_state=self.state,cache=self._manifest_costs)
            snapshot['metadata_error'] = {'type':type(error).__name__,'message':str(error)}
            return snapshot

    def disk_admitted(self, instance_id, *, kind):
        gate = super().disk_admitted(instance_id,kind=kind)
        if self._priority_demand is None:
            gate.update(admitted=False,priority_observation_missing=True)
        else:
            gate = priority.priority_admission(gate,self._priority_demand)
        self.state['last_disk_dispatch_admission'] = gate
        return gate

    def launch_preparation(self, instance_id):
        if self._preparation_disk_closed:
            return
        with previous.disk_dispatch_lock():
            gate = self.disk_admitted(instance_id,kind='preparation')
            demand = self._priority_demand
            normal = backlog.prewarm_backlog(self.state)
            self.state['prewarm_backlog'] = normal
            urgent = demand is not None and instance_id in demand['selected_task_ids']
            if not normal['admit_new_preparation'] and not urgent:
                return
            if not gate['admitted']:
                self._preparation_disk_closed = True
                return
            self.state['preparation'][instance_id]['disk_reservation'] = {
                'host_revision':self.revision_ref,**gate,'consumer_inventory_supplement':urgent}
            # Reuse the exact frozen worker builder, limits, initializer and durable intent.
            # Only the aggregate unused-ready guard is supplemented for these selected tasks.
            original.Coordinator.launch_preparation(self,instance_id)
            self.state['prewarm_backlog'] = backlog.prewarm_backlog(self.state)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    p=commands.add_parser('freeze')
    p.add_argument('--predecessor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--previous-controller',required=True)
    p=commands.add_parser('run')
    p.add_argument('--revision',type=Path,required=True)
    p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.operation=='freeze':
        oldref=reference(args.predecessor); old=load(oldref)
        if old['version']!=previous.VERSION:
            raise ValueError('Require the exact preceding r4 host')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        print(json.dumps(write_new(args.output,{'version':VERSION,'created_utc':now(),
            'predecessor_revision':oldref,'original_plan':old['original_plan'],'activation':old['activation'],
            'disk_policy':previous.POLICY,'unused_ready_backlog_limit':8,
            'preparation_priority_version':priority.VERSION,'previous_controller_unit':args.previous_controller,
            'files':[reference(__file__),reference(ROOT/'tools/run_deepseek_queue_native_host_v055_r5.py'),
                     reference(priority.__file__),*old['files']],
            'scientific_configuration_unchanged':True,'existing_workers_adopted':True,
            'model_calls':0,'automatic_model_replay':False})))
        return
    ref=reference(args.revision)
    if ref['sha256']!=args.sha256:
        raise ValueError('Shared preparation host revision hash mismatch')
    coordinator=NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.lease.close()


if __name__=='__main__':
    main()
