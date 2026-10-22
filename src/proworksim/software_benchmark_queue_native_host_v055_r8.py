"""Future all-arm r4 financial client with unchanged r7 disk/volume scheduling."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import time

from . import software_benchmark_queue_native_host_v055_r7 as previous
from . import software_benchmark_queue_native_host_v055_r2 as builder
from . import software_benchmark_queue_v055 as original
from . import software_benchmark_budget_runtime_v055_r4 as runtime
from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_queue_v055 import ROOT,load,now

VERSION='v055-all-arm-financial-policy-r4-volume-host-r8'


@contextmanager
def builder_routes(activation_ref,activation):
    materialize,direct=builder.materialize_config,builder.direct_environment_command
    def materialize_all(plan,template,slot,output):
        config=materialize(plan,template,slot,output)
        if slot['arm']!='PROJECT':return config
        value=load(config)
        value.update(solver_activation=activation_ref,runtime_revision=activation['runtime_revision'],
            frozen_sources=[*value['frozen_sources'],*activation['files'],activation_ref])
        # The old builder's PROJECT branch does not add native activation; this
        # separate immutable config extends only that branch's runtime binding.
        return write_new(Path(output).parent/'budget-project-config-r4.json',value)
    def route(command):
        command=list(map(str,command))
        if command[1:3]==['-m','proworksim.software_benchmark_runner_v055']:
            command=[command[0],str(checked(activation['generation_entrypoint'])),*command[3:]]
        return direct(command)
    builder.materialize_config, builder.direct_environment_command=materialize_all,route
    try:yield
    finally:builder.materialize_config,builder.direct_environment_command=materialize,direct


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self,revision_ref):
        self.revision_ref,self.revision=revision_ref,load(revision_ref)
        self.predecessor=load(self.revision['predecessor_revision'])
        if (self.revision.get('version')!=VERSION or self.predecessor.get('version')!=previous.VERSION
                or self.revision['original_plan']!=self.predecessor['original_plan']
                or self.revision['volume_manifest']!=self.predecessor['volume_manifest']
                or self.revision['cross_volume_qualification']!=self.predecessor['cross_volume_qualification']
                or self.revision['disk_policy']!=previous.volumes.POLICY
                or self.revision['disk_volume_policy']!=previous.volumes.VOLUME_POLICY
                or self.revision['budget_policy_sha256']!=runtime.policy_sha256()
                or self.revision['unused_ready_backlog_limit']!=8):
            raise ValueError('Financial host must retain the original experiment and qualified volume policy')
        for item in self.revision['files']:checked(item)
        previous.check_qualification(self.revision['cross_volume_qualification'])
        previous.volumes.configure(self.revision['volume_manifest'])
        self.activation=self.activation_ref=None;self._manifest_costs={}
        self._generation_disk_closed=self._preparation_disk_closed=False
        self._priority_demand=None;self._candidate_arm=None;self._target_volume='primary'
        # Private coordinator-process binding, before the old constructor creates
        # its ledger. Existing workers and on-disk source identities are untouched.
        self._old_queue_ledger=original.BudgetLedger
        original.BudgetLedger=runtime.new_api.BudgetLedger
        original.Coordinator.__init__(self,self.revision['original_plan'])
        self.load_activation()
        self._builder_context=builder_routes(self.activation_ref,self.activation)
        self._builder_context.__enter__()
        history=self.state.setdefault('host_revision_history',[])
        if not history or history[-1]['revision']!=revision_ref:
            history.append({'revision':revision_ref,'adopted_utc':now(),
                'existing_worker_jobs_unchanged':True,'entered_slots_replayed':0})
        self.state['active_host_revision']=revision_ref
        self.state['MATCH_dispatch_hold']=False
        self.state['financial_policy_runtime']={'activation':self.activation_ref,
            'policy_sha256':runtime.policy_sha256(),'all_arms_and_condenser_new_client':True}
        self.save()

    def load_activation(self):
        ref=self.revision['activation']
        if self.activation_ref==ref:return
        if self.activation_ref is not None:raise ValueError('Adopted financial activation cannot change')
        activation=runtime.validate_activation(ref)
        if (activation['original_plan']!=self.plan_ref
                or activation['previous_native_activation']!=self.predecessor['activation']):
            raise ValueError('Financial activation changed the original plan or native reasoning implementation')
        frozen={item['path']:item for item in self.plan['frozen_sources']}
        for item in activation['files']:
            if item['path'] in frozen and item!=frozen[item['path']]:
                raise ValueError('Financial activation cannot rewrite a previously frozen file')
        self.activation,self.activation_ref=activation,ref
        self.state['native_solver_activation']=ref
        self.state['activated_solver_arms']=sorted(runtime.ARMS)
        self.state['all_arm_budget_activation']=ref
        self.save()

    def launch(self,row,record,*,kind,request=None):
        sentinel=object();saved=record.get('runtime_revision',sentinel)
        project=kind=='generation' and row['slot']['arm']=='PROJECT'
        if project:record['runtime_revision']=self.activation_ref
        try:return super().launch(row,record,kind=kind,request=request)
        finally:
            if project and record['status']=='pending':
                if saved is sentinel:record.pop('runtime_revision',None)
                else:record['runtime_revision']=saved

    def close_bindings(self):
        self._builder_context.__exit__(None,None,None)
        original.BudgetLedger=self._old_queue_ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    p=commands.add_parser('freeze');p.add_argument('--predecessor',required=True,type=Path)
    p.add_argument('--activation',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--previous-controller',required=True)
    p=commands.add_parser('run');p.add_argument('--revision',required=True,type=Path);p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.operation=='freeze':
        oldref=reference(args.predecessor);old=load(oldref);activation_ref=reference(args.activation)
        activation=runtime.validate_activation(activation_ref)
        if (old['version']!=previous.VERSION or activation['original_plan']!=old['original_plan']
                or activation['previous_native_activation']!=old['activation']):
            raise ValueError('Require r7 predecessor and matching all-arm activation')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        print(json.dumps(write_new(args.output,{'version':VERSION,'created_utc':now(),
            'predecessor_revision':oldref,'original_plan':old['original_plan'],'activation':activation_ref,
            'disk_policy':old['disk_policy'],'disk_volume_policy':old['disk_volume_policy'],
            'volume_manifest':old['volume_manifest'],'cross_volume_qualification':old['cross_volume_qualification'],
            'budget_policy_sha256':runtime.policy_sha256(),'unused_ready_backlog_limit':8,
            'previous_controller_unit':args.previous_controller,
            'files':[reference(__file__),reference(ROOT/'tools/run_deepseek_queue_native_host_v055_r8.py'),
                     *activation['files'],*old['files']],
            'scientific_request_payloads_unchanged':True,'original_3000_slots_unchanged':True,
            'budget_cap_cny':2000,'existing_workers_adopted':True,'model_calls':0,'automatic_model_replay':False})))
        return
    ref=reference(args.revision)
    if ref['sha256']!=args.sha256:raise ValueError('Financial host revision SHA mismatch')
    coordinator=NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():time.sleep(5)
    finally:
        coordinator.close_bindings();coordinator.lease.close()


if __name__=='__main__':main()
