"""Two scripted SDK opportunities and exact checkpoint export, zero provider API."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
from proworksim.software_branch_checkpoint_v203_3_1 import capture_live_runtime,manifest,require_live_resume
from proworksim import software_role_baseline_runtime_v203_2_1 as runtime
from proworksim.storage import digest,json_bytes

ROOT=Path(__file__).resolve().parents[1]

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1')
    spec=importlib.util.spec_from_file_location('fixture_v141',ROOT/'tools/check_role_baseline_sdk_v141.py')
    f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
    prepared,deadline,_=f.fixture(out/'case','REVIEW2');calls=[]
    def post(route,payload):
        if route in {'/tokenize','/tokenize-prefix'}:
            return {'prompt_tokens':256,'request_sha256':digest(json_bytes(payload['wire'])),
                'method':'scripted checkpoint control','count_only_not_dispatchable':route.endswith('prefix')}
        assert route=='/chat/completions' and len(calls)<2
        calls.append(payload);member=payload['member_id']
        return {'id':f'checkpoint-{len(calls)}','model':'deepseek-flash','object':'chat.completion','created':0,
            'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':f'read-{member}','type':'function','function':{'name':'read_file','arguments':json.dumps({'path':'sample.py'})}}]}}],
            'usage':{'prompt_tokens':256,'completion_tokens':25,'total_tokens':281,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':256}}
    owner=runtime.build_team_owner(post,organization_id='REVIEW2',slot_id='v203.3.1:checkpoint:control',
        condition_id='checkpoint_control',folder=out/'model-ledger',deadline=deadline,
        identity={'policy_version':'zero-API-scripted-control'},observation_token_counter=lambda s:len(s.split()),
        observation_tokenizer_id='control-word-counter-not-provider')
    rt,_,_=runtime.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message='Read the public sample once; checkpoint control only.')
    try:
        for _ in range(2):
            rt.sync_members();result=rt.step()
            assert result.get('status') not in {'environment_error','model_service_error','execution_integrity_error'},result
        receipt=capture_live_runtime(prepared,rt,out/'checkpoint')
        assert len(calls)==2 and set(p['member_id'] for p in calls)=={'member_001','member_002'}
        actual=manifest(out/'checkpoint');actual.pop('manifest.json')
        assert actual==receipt['files']
        rejected=False
        try:require_live_resume(json.loads((out/'checkpoint/live-state.json').read_text()))
        except ValueError:rejected=True
        assert rejected
        summary={'passed':True,'scripted_requests':2,'provider_API_calls':0,
            'member_private_SDK_snapshots':2,'copied_files_verified':len(actual),
            'checkpoint_identity':receipt['identity'],'SDK_continuation_qualified':False,
            'incomplete_resume_correctly_rejected':True,'remaining_gap':'new request namespaces, clocks and SDK rehydration need paired continuation validation'}
        (out/'summary.json').write_bytes(json_bytes(summary));print(json.dumps(summary))
    finally:runtime.close_runtime(rt)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);run(p.parse_args().output.resolve())
