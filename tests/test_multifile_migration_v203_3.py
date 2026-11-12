"""20 local managed-Harness controls; no models, containers or benchmark tasks."""
import copy,hashlib,itertools,json,os,subprocess,sys
import pytest
from proworksim import software_role_baseline_world_v141 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest,json_bytes
from proworksim.software_dual_graph_v203 import identity
from proworksim.software_multifile_transfer_v203_3 import MultiFileTransfer
M1,M2='member_001','member_002'

class Fixture:
    def __init__(self,folder):
        self.folder=folder;source=folder/'source';source.mkdir();self.receipts=[];self.test_calls=0;self.observer=None
        for path,text in {'sample.py':'value = 1\n','helper.py':'OFFSET = 0\n','test_sample.py':'def test_value():\n    from sample import value\n    assert value == 2\n'}.items():(source/path).write_text(text)
        tid='fixture__multifile-2033';manifest=capture_repository(source,folder/'snapshot',task_id=tid,problem_statement='CPU control: fix two public modules',source_identity={'instance_id':tid,'repo':'fixture/multifile','base_commit':'a'*40,'dataset_revision':'b'*40})
        argv=[sys.executable,'-m','pytest','-q','test_sample.py'];entry={'version':'v064-repository-public-test-entry-r1','instance_id':tid,'argv':argv,'cwd':'/testbed','timeout_seconds':20,'hidden_material_used':False}
        def test(*,files,entry_metadata,request):
            self.test_calls+=1;run=folder/f'public-test-{self.test_calls}';run.mkdir()
            for path in ['sample.py','helper.py','test_sample.py']:(run/path).write_text(files[path])
            proc=subprocess.run(argv,cwd=run,capture_output=True,text=True,timeout=20,env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
            passed=proc.returncode==0;counts={'collected':1,'passed':int(passed),'failed':int(not passed),'errors':0,'skipped':0,'xfailed':0,'xpassed':0,'tests_run':1}
            return {'passed':passed,'execution':{'executed':True,'input_tree_sha256':request['tree_sha256'],'actor_id':request['actor_id'],'organization_id':'REVIEW2','managed_request_sha256':digest(json_bytes(request)),
                'argv':argv,'public_test_selection':request['public_test_selection'],'public_test_selection_revision':'v110-public-test-selection-r1','validation_status':'verified' if passed else 'failed','counts':counts,
                'test_evidence':{'source':'actual local CPU pytest','returncode':proc.returncode}},'groups':{'public_repository_tests':{'passed':passed,'executed':True,'status':'passed' if passed else 'failed','output':proc.stdout[-2000:],'tests':[{'test_id':'test_sample.py::test_value','passed':passed}]}},'repository_collection_errors':[]}
        self.prepared=world.prepare_case(manifest,folder/'prepared',organization_id='REVIEW2',public_test_callback=test,deadline=DispatchDeadline(soft_seconds=3600,hard_seconds=3900),public_test_entry=entry)
        self.world=self.prepared.world;self.ports={m:HarnessPort(world.SoftwareCollaborationPort(self.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in [M1,M2]}
        for port in self.ports.values():port.tools()
        self.sequence=itertools.count()
        self.ok(M1,'create_task',task_id='repair',description='Two-module repair');self.ok(M1,'claim_task',task_id='repair',reason='Accept task')
        self.ok(M1,'create_task',task_id='other',description='Separate responsibility');self.ok(M1,'claim_task',task_id='other',reason='Keep original ownership')
        self.ok(M1,'write_file',path='sample.py',text='from helper import OFFSET\nvalue = OFFSET + 1\n');self.ok(M1,'write_file',path='helper.py',text='OFFSET = 1\n')
    def call(self,actor,tool,**args):
        raw=self.ports[actor].call(tool,request_key=f'm2033-{next(self.sequence)}',association={},**args)
        r={'actor':actor,'tool':tool,'arguments':args,'ok':raw['ok'],'result':raw.get('result',{}),'source':{'response_sha256':identity(raw),'action_id':raw.get('action_id')},'full_response':raw}
        self.receipts.append(copy.deepcopy(r))
        if self.observer:self.observer.observe_world_receipt(r)
        return r
    def ok(self,actor,tool,**args):
        r=self.call(actor,tool,**args);assert r['ok'],r;return r
    def publish(self):
        self.patch=self.ok(M1,'fix_patch',task_ids=['repair'],message='Two-module fixed candidate')['result'];return self.patch
    def package(self):
        self.publish();facts=[]
        for path in ['sample.py','helper.py']:
            r=self.ok(M1,'read_file',path=path,patch_id=self.patch['patch_id'])['result'];value=r['text']
            facts.append({'fact_id':path,'path':path,'value':value,'value_sha256':hashlib.sha256(value.encode()).hexdigest(),'start_character':0,'end_character':len(value),'source_reference':self.patch['source_reference'],'access':'published_artifact'})
        p={'task_id':'repair','task_revision':1,'old_owner':M1,'new_owner':M2,'project_region':['sample.py','helper.py'],'code_version':self.patch['source_reference'],'artifacts':[self.patch['patch_id']],
            'test_evidence':[],'required_facts':facts,'unresolved_issues':['Recipient must independently test'],'provenance':[{'fixed_patch':self.patch['patch_id']}],'permissions':['original fixed publication']}
        self.payload=p;self.observer=MultiFileTransfer(p);return p
    def transfer(self):
        if self.observer is None:self.package()
        offer=self.ok(M1,'offer_transfer',task_id='repair',to_member=M2,reason='Explicit CPU transfer');self.offer=offer['result']['offer_id'];self.observer.advance('AUTHORIZED',offer)
        accepted=self.ok(M2,'accept_transfer',offer_id=self.offer);self.observer.advance('ACCEPTED',accepted)
    def receive_package(self):
        sent=self.ok(M1,'send_message',recipient=M2,task_id='repair',body=json.dumps(self.payload));self.sent=sent['result']['message_sequence']
        restored=self.ok(M2,'read_work_event',sequence=self.sent);self.observer.acknowledge_package(restored)
    def read_all(self):
        for fact in self.payload['required_facts']:
            # Each required fact names its own immutable source artifact/version.
            patch_id=next(k for k,v in self.world._software()['patches'].items() if v['source_reference']==fact['source_reference'])
            last=self.ok(M2,'read_file',path=fact['path'],patch_id=patch_id);self.observer.read_fact(last)
        self.observer.advance('CONTEXT_TRANSFERRED',last)
    def adopt_all(self):
        for pid in self.payload['artifacts']:
            last=self.ok(M2,'integrate_patch',patch_id=pid);self.observer.record_adoption(last)
        self.observer.advance('RESUMED',last)
    def archive(self,name):
        path=os.environ.get('PWS_MIGRATION_EVIDENCE_DIR')
        if path:
            from pathlib import Path
            out=Path(path);out.mkdir(parents=True,exist_ok=True)
            (out/f'{name}.json').write_text(json.dumps({'case':name,'receipts':self.receipts,'pytest_runs':self.test_calls,'state':self.observer.state if self.observer else None,
                'task_owners':{t:r['owner'] for t,r in self.world._software()['tasks'].items()},'model_calls':0},ensure_ascii=False,indent=2)+'\n')

SCENARIOS=['multifile_success','untransferred_task','unpublished','published_read_only','preview_only','missing_file','paged_source','wrong_version','stale_offer','declined_offer',
    'duplicate_accept','competing_offer','wrong_recipient','private_event','old_test_after_edit','revision_after_accept','recover_read_failure','two_artifacts','tampered_receipt','version_mix']

@pytest.mark.parametrize('name',SCENARIOS)
def test_managed_migration_matrix(tmp_path,name):
    f=Fixture(tmp_path)
    try:
        if name=='unpublished':
            r=f.call(M2,'read_file',path='sample.py',patch_id='not-published');assert not r['ok'];return
        if name=='published_read_only':
            patch=f.publish();r=f.ok(M2,'read_file',path='sample.py',patch_id=patch['patch_id']);assert r['result']['source_reference']==patch['source_reference'];assert f.world._software()['tasks']['repair']['owner']==M1;return
        f.package()
        if name in {'stale_offer','declined_offer','competing_offer','wrong_recipient'}:
            offer=f.ok(M1,'offer_transfer',task_id='repair',to_member=M2,reason='Control')['result']['offer_id']
            if name=='stale_offer':f.ok(M1,'revise_task',task_id='repair',description='Changed requirement',expected_revision=1,reason='new revision')
            if name=='declined_offer':f.ok(M2,'decline_transfer',offer_id=offer,reason='Cannot take ownership')
            if name=='competing_offer':assert not f.call(M1,'offer_transfer',task_id='repair',to_member=M2,reason='Conflicting second request')['ok']
            else:assert not f.call(M1 if name=='wrong_recipient' else M2,'accept_transfer',offer_id=offer)['ok']
            assert f.world._software()['tasks']['repair']['owner']==M1;return
        if name=='two_artifacts':
            f.ok(M1,'create_file',path='config.txt',text='mode=public\n');p2=f.ok(M1,'fix_patch',task_ids=['repair'],message='Second explicit fixed artifact')['result']
            r=f.ok(M1,'read_file',path='config.txt',patch_id=p2['patch_id'])['result'];value=r['text'];f.payload['artifacts'].append(p2['patch_id'])
            f.payload['required_facts'].append({'fact_id':'config','path':'config.txt','value':value,'value_sha256':hashlib.sha256(value.encode()).hexdigest(),'start_character':0,'end_character':len(value),'source_reference':p2['source_reference'],'access':'published_artifact'})
            f.observer=MultiFileTransfer(f.payload)
        f.transfer()
        if name=='duplicate_accept':assert not f.call(M2,'accept_transfer',offer_id=f.offer)['ok'];assert f.world._software()['tasks']['repair']['owner']==M2;return
        if name=='untransferred_task':assert f.world._software()['tasks']['other']['owner']==M1;return
        if name=='private_event':
            f.ok(M1,'create_file',path='private.py',text='private_marker=9\n');event=f.world.state['software_events'][-1]
            assert not f.call(M2,'read_work_event',sequence=event['sequence'])['ok'];return
        if name=='preview_only':
            read=f.ok(M2,'read_file',path='sample.py',patch_id=f.patch['patch_id'])
            with pytest.raises(ValueError):f.observer.read_fact(read)
            return
        f.receive_package()
        if name=='revision_after_accept':
            f.ok(M2,'revise_task',task_id='repair',description='Scope changed after acceptance',expected_revision=1,reason='Explicit new scope')
            with pytest.raises(ValueError):f.read_all()
            assert f.observer.package_stale;return
        if name in {'wrong_version','version_mix','recover_read_failure'}:
            wrong=f.ok(M2,'read_file',path='sample.py')
            with pytest.raises(ValueError):f.observer.read_fact(wrong)
            assert not f.observer.received
            if name!='recover_read_failure':return
        if name=='missing_file':
            first=f.ok(M2,'read_file',path='sample.py',patch_id=f.patch['patch_id']);f.observer.read_fact(first)
            with pytest.raises(ValueError):f.observer.advance('CONTEXT_TRANSFERRED',first)
            return
        if name=='tampered_receipt':
            read=f.ok(M2,'read_file',path='sample.py',patch_id=f.patch['patch_id']);f.observer.read_fact(read);before=copy.deepcopy(f.observer.received)
            bad=copy.deepcopy(read);bad['result']['text']='tampered'
            with pytest.raises(ValueError):f.observer.read_fact(bad)
            assert f.observer.received==before;return
        if name=='paged_source':
            first=f.ok(M2,'read_file',path='sample.py',patch_id=f.patch['patch_id'],max_lines=1);f.observer.read_fact(first);assert 'sample.py' not in f.observer.received
            second=f.ok(M2,'read_file',path='sample.py',patch_id=f.patch['patch_id'],cursor=first['result']['next_cursor'],max_lines=1);f.observer.read_fact(second)
            last=f.ok(M2,'read_file',path='helper.py',patch_id=f.patch['patch_id']);f.observer.read_fact(last);f.observer.advance('CONTEXT_TRANSFERRED',last)
        else:f.read_all()
        f.adopt_all();passed=f.ok(M2,'run_tests');assert passed['result']['passed']
        if name=='old_test_after_edit':
            f.ok(M2,'write_file',path='helper.py',text='OFFSET = 2\n')
            with pytest.raises(ValueError):f.observer.advance('VERIFIED',passed)
            failed=f.ok(M2,'run_tests');assert not failed['result']['passed']
            with pytest.raises(ValueError):f.observer.advance('VERIFIED',failed)
            f.ok(M2,'write_file',path='helper.py',text='OFFSET = 1\n');passed=f.ok(M2,'run_tests');assert passed['result']['passed']
        f.observer.advance('VERIFIED',passed);assert f.observer.verification_current
        assert f.world._software()['patches'][f.patch['patch_id']]['author']==M1 and not f.world._software()['deliveries']
    finally:f.archive(name)

def test_same_request_id_accept_is_idempotent(tmp_path):
    f=Fixture(tmp_path);f.transfer()
    interaction=f.world.state['interactions'][-1];key=interaction['request_key'];offer_id=f.offer
    before=copy.deepcopy(f.world.state['software_events']);owner=f.world._software()['tasks']['repair']['owner']
    again=f.ports[M2].call('accept_transfer',request_key=key,association={},offer_id=offer_id)
    assert again['ok'] and f.world._software()['tasks']['repair']['owner']==owner==M2
    assert f.world.state['software_events']==before
    f.archive('same_request_id_idempotence')
