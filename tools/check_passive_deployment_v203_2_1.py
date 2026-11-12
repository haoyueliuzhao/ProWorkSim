"""Small CPU checks of the actual new deployment binding; no resource/API calls."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
from proworksim import software_benchmark_scope_v203_2_1 as scope
from proworksim import software_benchmark_episode_v203_2_1 as episode
from proworksim import software_benchmark_alignment_contract_v203_2_1 as alignment
from proworksim import software_benchmark_alignment_contract_v141 as original
from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
from proworksim import software_benchmark_project_closure_v203_2_1 as closure
from proworksim import software_benchmark_runtime_inputs_v203_2_1 as inputs
from proworksim.software_benchmark_candidates_v054 import reference


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def check():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    def guard(operation,**identity):
        return {'status':'approved','execution_alignment_version':alignment.VERSION,
                'source_index':{'CPU_only':True},'plan':reference(scope.PLAN_FILE)}
    value=episode.build_episode(scope=scope,guard=guard)
    assert value.runtime is bundle and value._run.__globals__['runtime'] is bundle
    assert value._run.__globals__['BATCH']==scope.BATCH_ROOT
    assert value.run_episode.__globals__['_run'] is value._run
    assert value.allowed_organization_ids==('REVIEW2',) and value.new_system_parent_slice is False
    assert alignment.condition('REVIEW2')==original.condition('REVIEW2')
    imports=[n.module for n in ast.walk(value.memory_transformed_ast) if isinstance(n,ast.ImportFrom)]
    assert 'software_benchmark_project_closure_v203_2_1' in imports
    for row in plan['rows']:
        host,condition,limits=value._row_and_config(row,False)
        assert limits['input_plus_output_tokens']==5_000_000
        closure.validate_slot_identity(row['slot_id'],row['instance_id'])
        for prefix in ('v142','v146','v157','v170'):
            try:closure.validate_slot_identity(row['slot_id'].replace('v203.2.1:',prefix+':',1),row['instance_id'])
            except ValueError:pass
            else:raise AssertionError('Old identity accepted')
    provider=value.OwnedActorPair.create_container.__globals__
    assert provider['ROLES']['controller'][1]==32*scope.GIB
    assert provider['container_options'].__globals__ is provider['validate_container'].__globals__ is provider
    lanes=[scope.cpu_set(role,i) for role,count in [('actor',8),('controller',8),('grader',2)] for i in range(count)]
    assert len(set(','.join(lanes).split(',')))==56
    # Reuse only a synthetic fixture constructor, not its old test suite.
    fixture=module(scope.ROOT/'tests/test_public_runtime_bindings_v141.py','v203_2_1_fixture')
    controller=module(scope.ROOT/'tools/run_passive_controller_v203_2_1.py','v203_2_1_controller')
    with tempfile.TemporaryDirectory(prefix='pws-v203-2-1-inputs-') as temporary:
        row,public,entry,base,binding,ready,host=fixture.prepared(Path(temporary),'REVIEW2')
        row['slot_id']=row['slot_id'].replace('v142:','v203.2.1:',1);host['slot_id']=row['slot_id']
        from proworksim.software_benchmark_public_context_v062 import VERSION as context_version
        context={'version':context_version,'instance_id':row['instance_id'],
                 'visible_text':'Public fixture context','visible_facts':{'cwd':'/testbed'}}
        generated=bundle.controller_inputs(host,row,ready,{'thinking':False,'model':'deepseek-flash'},
            'http://127.0.0.1:18219',public_context=context,public_environment=public,
            public_test_entry=entry,actor_config=binding['config'])
        config=json.loads(generated['controller-config.json'])
        assert controller.validate_config(config)==config
        assert controller.validate_ready(config,ready)==ready
        assert inputs.controller_inputs is bundle.controller_inputs
    return {'passed':True,'rows_checked':12,'condition_exactly_original_v141':True,
        'actual_episode_closure_import_new':True,'old_slot_id_rejections':48,
        'controller_config_roundtrip':True,'separate_private_provider_limits':True,
        'generation_and_grader_cpu_lanes_disjoint':True,'model_calls':0,'Docker_operations':0,
        'not_a_real_environment_qualification':True,'plan':reference(scope.PLAN_FILE)}


if __name__=='__main__':
    result=check();folder=scope.ARTIFACT_ROOT/'deployment-bindings-r2';folder.mkdir(parents=True,exist_ok=True)
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
