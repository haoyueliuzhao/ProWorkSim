"""Actual allocator->volume->container options and validator regression controls."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_scope_v203_2_1_r2 as scope
from proworksim import software_benchmark_scope_v203_2_1 as prior
from proworksim import software_benchmark_episode_v203_2_1_r2 as episode
from proworksim import software_benchmark_alignment_contract_v203_2_1 as alignment
from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def guard(*args,**kwargs):
 return {'status':'approved','execution_alignment_version':alignment.VERSION,
         'source_index':{'CPU_fixture':True},'plan':reference(scope.PLAN_FILE)}


def test_exact_twelve_logical_attempts_same_cash_and_private_episode_binding():
 new=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)));old=scope.load(reference(prior.PLAN_FILE))
 assert [r['slot_index'] for r in new['rows']]==list(range(2032200,2032212))
 for actual,previous in zip(new['rows'],old['rows'],strict=True):
  assert {k:v for k,v in actual.items() if k not in {'configuration','slot_index'}}=={k:v for k,v in previous.items() if k not in {'configuration','slot_index'}}
  a,b=scope.load(actual['configuration']),scope.load(previous['configuration'])
  assert {k:v for k,v in a.items() if k not in {'version','slot_index'}}=={k:v for k,v in b.items() if k not in {'version','slot_index'}}
 assert scope.LEDGER_FILE==prior.LEDGER_FILE and scope.BUDGET_BASELINE_FILE==prior.BUDGET_BASELINE_FILE
 assert new['resource_role_counts']['control']==4
 value=episode.build_episode(scope=scope,guard=guard)
 assert value._run.__globals__['BATCH']==scope.BATCH_ROOT
 assert value._run.__globals__['runtime'] is bundle
 assert value.wait_capacity.__globals__['capacity'] is value.capacity
 assert value.capacity()['disk_floor_with_two_actor_reservations']==128*scope.GIB
 for row in new['rows']:value._row_and_config(row,False)
 imports=[n.module for n in ast.walk(value.memory_transformed_ast) if isinstance(n,ast.ImportFrom)]
 assert 'software_benchmark_project_closure_v203_2_1' in imports


def test_actual_allocator_named_volume_reaches_both_real_container_builders(tmp_path):
 plan=scope.load(reference(scope.PLAN_FILE));row=plan['rows'][0];index=row['slot_index']
 fixture=write_new(tmp_path/'plan.json',{'resources':{f'{role}-{index}':plan['resources'][f'{role}-{index}'] for role in ('actor','controller','volume')}})
 auth=write_new(tmp_path/'authorization.json',{'CPU_fixture':True})
 policy=scope.dispatch_view(guard);ns=policy.claim_resource.__globals__
 assert ns['BATCH_ROOT']==scope.BATCH_ROOT
 # Exercise the actual allocator body in an isolated temporary ownership tree;
 # no formal resource identity, Docker socket or live authority is consumed.
 ns.update(BATCH_ROOT=tmp_path,AUTHORIZATION_FILE=Path(auth['path']),
  require_v066_allowed=lambda *a,**k:{'plan':fixture},_budget=lambda *a,**k:{'CPU_fixture':True})
 actor_ref=policy.claim_resource(f'actor-{index}');volume_ref=policy.claim_resource(f'volume-{index}');controller_ref=policy.claim_resource(f'controller-{index}')
 claims={name:scope.load(ref) for name,ref in [('actor',actor_ref),('volume',volume_ref),('controller',controller_ref)]}
 assert all(c['docker_name'].startswith('pws-v066-') for c in claims.values())
 assert len({c['docker_name'] for c in claims.values()})==3
 value=episode.build_episode(scope=scope,guard=guard);provider=value.OwnedActorPair.create_container.__globals__
 assert provider['container_options'].__globals__ is provider['validate_container'].__globals__ is provider
 volume_name=claims['volume']['docker_name'];vo=provider['volume_options'](volume_ref,claims['volume'])
 volume=SimpleNamespace(attrs={'Name':vo['name'],'Driver':vo['driver'],'Options':vo['driver_opts'],'Labels':vo['labels']},reload=lambda:None)
 provider['validate_volume'](volume,volume_ref,claims['volume'])
 for role,ref in [('actor',actor_ref),('controller',controller_ref)]:
  options=provider['container_options'](role,ref,claims[role],volume_name,['/opt/pws-runtime/bin/python'],cpuset=scope.cpu_set(role,0))
  assert options['network_mode']=='none' and options['cap_add']==[] and options['cap_drop']==['ALL']
  assert options['mounts'][0]['Type']=='volume' and options['mounts'][0]['ReadOnly']==(role=='controller')
  assert options['mem_limit']==(16 if role=='actor' else 32)*scope.GIB
  attrs={'Image':options['image'],'Name':options['name'],
   'Config':{'Labels':options['labels'],'User':options['user'],'Tty':options['tty']},
   'HostConfig':{key:options[name] for key,name in {'NetworkMode':'network_mode','Privileged':'privileged','IpcMode':'ipc_mode',
    'CapDrop':'cap_drop','CapAdd':'cap_add','Memory':'mem_limit','MemorySwap':'memswap_limit','NanoCpus':'nano_cpus',
    'PidsLimit':'pids_limit','SecurityOpt':'security_opt'}.items()},
   'Mounts':[{'Type':'volume','Name':volume_name,'Destination':'/testbed','RW':role=='actor'}]}
  provider['validate_container'](SimpleNamespace(attrs=attrs,reload=lambda:None),role,ref,claims[role],volume_name)
  with pytest.raises(ValueError,match='explicitly owned Docker named volume'):
   provider['container_options'](role,ref,claims[role],'pws-v203-2-1-old-failing-prefix',['/opt/pws-runtime/bin/python'])
