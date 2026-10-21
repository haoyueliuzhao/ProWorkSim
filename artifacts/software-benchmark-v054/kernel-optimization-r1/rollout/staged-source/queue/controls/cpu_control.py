"""Narrow CPU-only controls; no live queue mutation, model, GPU or service."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
path = Path('/tmp/v054-kernel-queue-r1/src/proworksim/software_benchmark_kernel_queue_v054.py')
spec = importlib.util.spec_from_file_location('proworksim.software_benchmark_kernel_queue_v054', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
old_ref = {'path': '/original-bindings', 'sha256': 'old', 'bytes': 1}
new_ref = {'path': '/new-bindings', 'sha256': 'new', 'bytes': 2}
activation_ref = {'path': '/activation', 'sha256': 'activation', 'bytes': 3}
oldbindings = {key: {'same': key} for key in m.COMMON}
oldbindings.update(conditions={arm: {'condition': arm} for arm in ('REF','MATCH','PROJECT')},
                   resident_pool_policy={'pool': 'old'}, frozen_files=[])
newbindings = {**oldbindings, 'resident_pool_policy': {'pool': 'new'}}

def resident(gpu, key):
    return {'declaration': {'gpu_index': gpu, 'gpu_uuid': str(gpu), 'mode': 'REF' if gpu == 7 else 'MATCH_PROJECT',
                           'session_protocol': 'mp-interleave-v1'},
            'registration': {'registration': key}, 'declaration_reference': {'declaration': key},
            'session_capacity': 1 if gpu == 7 else 2, 'active_claims': [], 'resident_id': key}

pool = {str(gpu): resident(gpu, str(gpu)) for gpu in (3,6,7)}
assert set(m.filtered_old_pool({'available': pool})) == {'3','7'}
report = {'old_gpu6_filtered_gpu3_ref7_preserved': True}

with tempfile.TemporaryDirectory(prefix='v054-router-control-') as temporary:
    temp = Path(temporary)
    c = object.__new__(m.KernelCoordinator)
    c.root, c.bindings_ref, c.bindings = temp, old_ref, oldbindings
    c.router_policy = {'new_source_root': '/new/source', 'old_registration': {'old_registration': True}}
    c.activation = {'new_bindings': new_ref, 'qualified_registration': {'registration': 'kernel6'}}
    c.activation_ref = activation_ref
    c._context = None
    c.plan = {'maximum_active_generation_episodes': 8}
    active = {'slot': {'slot_id': 'old-active', 'slot_index': 1, 'instance_id':'old', 'arm': 'PROJECT'},
              'generation': {'status':'running', 'physical_gpu':3, 'resident_id':'3', 'claimed': True,
                             'job': {'original':'untouched'}, 'attempts':[]}, 'scores':{},'delivery':{}}
    nextrow = {'slot': {'slot_id':'next','slot_index':2,'instance_id':'next','arm':'MATCH'},
               'generation': {'status':'pending','attempts':[]},'scores':{},'delivery':{}}
    c.state = {'status':'running', 'bindings': old_ref, 'rows':[active, nextrow]}
    c.public_entries = {'next': {'baseline_mapping':{}}}
    saved, launches = [], []
    c.save = lambda: saved.append(copy.deepcopy(c.state))
    c.system = SimpleNamespace(launch=lambda unit, job: (launches.append(m.base.load_ref(job)) or
                               SimpleNamespace(returncode=0,stdout='',stderr='')))
    before = copy.deepcopy(active)
    original_load = m.base.load_ref
    def load(ref):
        if ref == new_ref:
            return newbindings
        if ref == {'old_registration':True}:
            return {'resident_id':'6'}
        return original_load(ref)
    newpool = {'available':{'kernel6':resident(6,'kernel6')}, 'healthy':{'kernel6':resident(6,'kernel6')},'deferred':[]}
    def bridge(policy, command, request):
        if command == 'healthy':
            return newpool
        assert command == 'prepare'
        p = Path(request['root'])
        return {'config':m.write_new(p/'config.json', {'slot':request['slot']}),
                'service':m.write_new(p/'service.json', {'test':True})}
    with patch.object(m.base,'load_ref',side_effect=load), patch.object(m,'bridge',side_effect=bridge), \
         patch.object(m.base,'claim_path',side_effect=lambda slot:temp/'claims'/slot/'claim.json'), \
         patch('proworksim.software_benchmark_deferred_pool_v054.healthy_residents',
               return_value={'available':{'6':pool['6']},'healthy':{'3':pool['3'],'6':pool['6']},'deferred':[]}), \
         patch('proworksim.software_benchmark_prewarm_v054.prewarm_health',return_value={'status':'ready'}), \
         patch('proworksim.software_benchmark_prewarm_v054.preparation_state',return_value={'status':'qualified'}):
        c.dispatch_generation()
    assert active == before
    assert nextrow['original_execution_bindings'] == new_ref
    assert nextrow['kernel_runtime_revision'] == activation_ref
    assert len(launches)==1 and launches[0]['bindings']==new_ref
    assert launches[0]['argv'][:2] == ['/usr/bin/env','PYTHONPATH=/new/source/src:/new/source']
    assert launches[0]['argv'][3] == '/new/source/tools/run_benchmark_episode_v054.py'
    assert c.bindings_ref == old_ref and c.state['bindings'] == old_ref
    assert all(s['bindings'] == old_ref for s in saved)
    report.update(new_row_and_job_bind_new_revision=True, new_child_argv_uses_isolated_source=True,
                  original_active_worker_unchanged=True, original_queue_binding_preserved_at_every_save=True)
    # Original terminal marker and full 1500 inventory remain compatible with
    # the deployed deferred-scoring watcher.
    c.exception_root = temp/'exceptions'
    c.exception_root.mkdir()
    c.policy_ref = {'original_deferred':'policy'}
    c.state['rows'] = [{'generation':{'status':'closed'},'scores':{'code':{'status':'official_report'}}} for _ in range(1500)]
    marker = c.finish_primary()
    value = original_load(marker)
    assert value['bindings'] == old_ref and value['overlay_policy'] == c.policy_ref
    assert value['planned_slots']==1500 and value['version']=='v054-deferred-primary-completion-v1'
    assert m.fault.primary_terminal(c.state['rows'])
    report['original_1500_primary_marker_preserved'] = True
    broken = {'version':m.ACTIVATION_VERSION,'original_bindings':new_ref}
    bad = m.write_new(temp/'bad-activation.json',broken)
    policy={'original_bindings':old_ref}
    try:
        m.validate_activation(policy,bad)
    except ValueError:
        report['wrong_activation_identity_rejected']=True
    else:
        raise AssertionError('Invalid activation accepted')

print(json.dumps({'status':'passed', 'controls':report, 'model_calls':0,'services_modified':False},indent=2))
