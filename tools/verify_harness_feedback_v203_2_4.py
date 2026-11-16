"""Verify actual post-test wire feedback, not send success or observer inference."""
import argparse,hashlib,json,sqlite3,importlib.util,io,os,time
from pathlib import Path

def verify(folder):
    journal=folder/'sdk/model-ledger/passive-observer/events.sqlite'
    tests=[];requests=[]
    with sqlite3.connect(journal.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for seq,raw,sha in db.execute("SELECT sequence,record_json,record_sha256 FROM observations WHERE json_extract(record_json,'$.kind') IN ('RECEIPT','MODEL_REQUEST') ORDER BY sequence"):
            row=json.loads(raw);p=row['payload']
            if row['kind']=='MODEL_REQUEST':requests.append((seq,p,sha))
            elif p['tool']=='run_tests':
                assert p['response']['ok'] is True,p['response'].get('error')
                tests.append((seq,p,sha))
    checked=[]
    for seq,p,sha in tests:
        result=p['response']['result'];match=None
        for req_seq,req,req_sha in requests:
            if req_seq<=seq or req['member_id']!=p['actor'] or req['usage_id']!='agent':continue
            for message in req['wire']['messages']:
                if message.get('role')!='tool' or not isinstance(message.get('content'),str):continue
                try:body=json.loads(message['content'])
                except ValueError:continue
                feedback=body.get('result',{})
                if feedback.get('report_id')!=result['report_id']:continue
                for key in ('counts','passed','body_sha256','source_reference'):
                    assert feedback[key]==result[key],key
                match={'request_sequence':req_seq,'request_record_sha256':req_sha,
                    'request_id':req['request_id'],'member_id':req['member_id']};break
            if match:break
        assert match is not None,(p['actor'],result['report_id'])
        checked.append({'test_sequence':seq,'test_record_sha256':sha,'report_id':result['report_id'],
            'counts':result['counts'],'passed':result['passed'],'subsequent_actual_input':match})
    assert len(checked)>=4
    report={'passed':True,'F3_verified_from_actual_wire':True,'tests':checked,'API_calls':0,
        'full_raw_report_for_paged_read_not_all_in_default_input':True,
        'provider_responses_scripted_not_autonomous_decision_quality':True}
    (folder/'feedback-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'tests':len(checked)}))

def permanent_failure_replay(folder):
    """Only replay the retained ERROR frame in a fresh CPU protocol object.

    No container, test, world action or provider request is replayed.
    """
    root=Path(__file__).resolve().parents[1]
    path=root/'tools/run_role_context_controller_v203_2_3_r5.py'
    spec=importlib.util.spec_from_file_location('r5_guard_replay',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    frames=folder/'actor/production-rpc'
    source=sorted(frames.glob('*-response.json'))[-1]
    error=json.loads(source.read_text());assert error['type']=='error'
    request=json.loads(source.with_name(source.name.replace('-response','-request')).read_text())
    readfd,writefd=os.pipe()
    os.write(writefd,(json.dumps(error)+'\n').encode());os.close(writefd)
    reader=os.fdopen(readfd,'rb',buffering=0)
    ready=json.loads((folder/'actor/ready.json').read_text())
    rpc=mod.ManagedRPC(ready,reader=reader,writer=io.StringIO(),
        directory=folder/'error-frame-only-replay',hard_at=time.monotonic()+30)
    rpc.sequence=error['id']-1
    refused=prevented=False
    try:
        try:rpc.exchange({k:v for k,v in request.items() if k!='id'},'observation')
        except (RuntimeError,ValueError):refused=rpc.failed
        try:mod.guard_actor_transfer(rpc)
        except RuntimeError:prevented=True
    finally:reader.close()
    assert refused and prevented
    report={'F6':True,'original_container_error_frame':str(source),
        'original_frame_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'actual_production_RPC_failed_state':refused,'guard_blocks_next_opportunity':prevented,
        'world_actions_replayed':0,'new_provider_calls':0,'Docker_operations':0,
        'reason':'Original integration reached its intended terminal refusal; diagnostic catch omitted the ValueError subclass. Only the error-frame handler is replayed.'}
    (folder/'permanent-failure-frame-verification.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--error-frame',action='store_true');args=p.parse_args()
    verify(args.folder)
    if args.error_frame:permanent_failure_replay(args.folder)
