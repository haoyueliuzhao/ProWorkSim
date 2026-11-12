"""Two-member local CPU control through the original managed HarnessPort.

No model or benchmark task is run. The existing tiny fixture runs actual pytest
in ordinary user subprocesses; no Docker, network, GPU or host configuration.
"""
import copy,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_role_baseline_world_v141 import prepare,M1,M2
from proworksim.software_responsibility_transfer_v203 import TransferEvidence
from proworksim.software_dual_graph_v203 import CrossGraph,CompleteSourceReplay,identity
from proworksim.storage import digest,json_bytes
from inventory_multimember_v203 import ROOT,ref,save

OUT=ROOT/'artifacts/software-benchmark-v203/harness-migration-r2'
RUN=ROOT/'runs/software-benchmark-v203/harness-migration-r2'
def main():
    save(OUT/'protocol.json',{'source':ref(Path(__file__)),'fixture':ref(ROOT/'tests/test_role_baseline_world_v141.py'),'policy':ref(ROOT/'src/proworksim/software_responsibility_transfer_v203.py'),
        'members':2,'organization':'REVIEW2','new_model_API':0,'benchmark_tasks':0,'Docker':0,'resource_scope':'ordinary user local fixture; two tiny actual pytest calls',
        'gate':'original Harness ownership, exact published source, explicit adopt and same-version public test; no synthetic acceptance'})
    prepared,ports,invoke,test_calls=prepare(RUN,'REVIEW2');events=[];projection=CrossGraph('cpu-harness',[M1,M2]);world=prepared.world
    _,_,baseline=world._bundle(M1,baseline=True);capture=CompleteSourceReplay(baseline,[M1,M2]);assertions=[]
    def call(actor,tool,**args):
        response=invoke(actor,tool,**args);e={'id':'cpu:'+str(len(events)),'step':len(events),'actor':actor,'action':tool,'arguments':args,'ok':response['ok'],
            'result':response.get('result',{}),'source':{'action_id':response.get('action_id'),'command_id':response.get('command_id'),'response_sha256':identity(response)}}
        events.append({**e,'response':response});projection.observe(e);record=capture.observe(e)
        if record and record['status']=='complete_verified':
            _,_,actual=world._bundle(actor);assert digest(json_bytes(actual['files']))==record['files_sha256']
        return {'actor':actor,'tool':tool,'arguments':args,'ok':response['ok'],'result':response.get('result',{}),'source':e['source'],'full_response':response}
    def accept(actor,tool,**args):
        result=call(actor,tool,**args);assert result['ok'],result;return result
    accept(M1,'create_task',task_id='repair',description='Change the public sample value and transfer explicit responsibility')
    accept(M1,'claim_task',task_id='repair',reason='Original developer accepts')
    accept(M1,'write_file',path='sample.py',text='value = 2\n')
    author_test=accept(M1,'run_tests');assert author_test['result']['passed']
    patch_receipt=accept(M1,'fix_patch',task_ids=['repair'],message='Exact version for transfer');patch=patch_receipt['result']
    # Later private work is intentionally absent from the fixed migration package.
    private_marker='v203-private-note-must-not-transfer'
    note=accept(M1,'create_file',path='private_v203.py',text=private_marker+' = 42\n')
    package={'task_id':'repair','task_revision':1,'old_owner':M1,'new_owner':M2,'project_region':['sample.py'],'code_version':patch['source_reference'],
        'artifacts':[patch['patch_id']],'test_evidence':[{'report_id':author_test['result']['report_id'],'source_reference':author_test['result']['source_reference']}],
        'required_facts':[{'path':'sample.py','value':'value = 2','access':'published_artifact','source_reference':patch['source_reference']}],
        'unresolved_issues':['Recipient must adopt and independently test; no automatic final delivery'],
        'provenance':[patch_receipt['source']],'permissions':[{'kind':'original_fixed_patch_publication','patch_id':patch['patch_id'],'recipient':M2}]}
    transfer=TransferEvidence(package);offer=accept(M1,'offer_transfer',task_id='repair',to_member=M2,reason='CPU control of source-bound ownership transfer')
    transfer.advance('AUTHORIZED',offer);assert world._software()['tasks']['repair']['owner']==M1
    received=accept(M2,'accept_transfer',offer_id=offer['result']['offer_id']);transfer.advance('ACCEPTED',received)
    assert world._software()['tasks']['repair']['owner']==M2
    sent=accept(M1,'send_message',recipient=M2,task_id='repair',body=json.dumps(package,ensure_ascii=False))
    observation=ports[M2].observe();assert private_marker not in json.dumps(observation,ensure_ascii=False)
    preview=next(m for m in observation['messages'] if m['sequence']==sent['result']['message_sequence'])
    restored=accept(M2,'read_work_event',sequence=sent['result']['message_sequence']);transfer.acknowledge_package(restored)
    assert json.loads(restored['result']['body'])==package
    readback=accept(M2,'read_file',path='sample.py',patch_id=patch['patch_id']);transfer.advance('CONTEXT_TRANSFERRED',readback)
    local=accept(M2,'read_file',path='sample.py');assert local['result']['text']=='value = 1\n'
    adopted=accept(M2,'integrate_patch',patch_id=patch['patch_id']);transfer.advance('RESUMED',adopted)
    assert not any(x['actor']==M2 and x['action']=='run_tests' for x in events)
    verified=accept(M2,'run_tests');transfer.advance('VERIFIED',verified)
    assert world._software()['patches'][patch['patch_id']]['author']==M1
    assert world._software()['deliveries']==[]
    assertions.extend(['offer_does_not_move_owner','accept_changes_actual_harness_owner','package_delivered_to_recipient_observation','original_source_read_authorized',
        'private_workspace_unchanged_until_adoption','original_author_preserved','old_author_test_not_inherited','resumed_exact_version_actually_tested','no_automatic_delivery','preview_not_assumed_complete','full_package_restored_by_authorized_read'])
    # Stale owner/revision and duplicate acceptance are rejected by existing code.
    duplicate=call(M2,'accept_transfer',offer_id=offer['result']['offer_id']);assert duplicate['ok'] is False
    accept(M1,'create_task',task_id='stale',description='Stale offer control');accept(M1,'claim_task',task_id='stale',reason='Original owner')
    stale=accept(M1,'offer_transfer',task_id='stale',to_member=M2,reason='Before revision')
    accept(M1,'revise_task',task_id='stale',description='New revision',expected_revision=1,reason='Invalidate prior offer')
    denied=call(M2,'accept_transfer',offer_id=stale['result']['offer_id']);assert denied['ok'] is False and world._software()['tasks']['stale']['owner']==M1
    assertions.extend(['duplicate_accept_rejected','stale_revision_accept_rejected'])
    save(OUT/'receipts.json',events);save(OUT/'transfer-package.json',package);save(OUT/'transfer-state-history.json',transfer.history)
    save(OUT/'summary.json',{'passed':True,'assertions':assertions,'assertion_count':len(assertions),'actual_managed_actions':len(events),'actual_pytest_runs':len(test_calls),
        'actual_harness_owner_transfers':1,'transfer_state':transfer.state,'private_unpublished_file_created':note['ok'],'default_preview_equal_full_package':preview.get('body')==json.dumps(package,ensure_ascii=False),
        'projector_snapshots':len(projection.snapshots),'source_capture':[{k:v for k,v in r.items() if k!='documents'} for r in capture.records],
        'source_tree_matches_original_harness':True,'new_model_calls':0,'real_benchmark_tasks':0,'model_presented_or_understood_package':False,
        'verified_means_only_current_cpu_fixture_public_test_not_final_delivery':True})
    print('CPU managed migration completed:',len(events),'actions;',len(test_calls),'actual pytest runs')
if __name__=='__main__':main()
