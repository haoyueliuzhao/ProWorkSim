"""Controlled fixtures and source-only normalization of opened historical inputs."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from proworksim.software_syntax_facts_v202 import document,SourceAssembler,sha
from proworksim.software_context_graph_v196 import obj

def ref_version(actor,n):return {'object_id':'workspace-'+actor,'version_id':'v'+str(n)}
def event(n,kind,actor,data,*,source_ids=None,source_kind='synthetic_control'):
    return {'event_id':f'{source_kind}:{n}','kind':kind,'actor':actor,'source_ids':source_ids or [f'control-source:{n}'],'source_kind':source_kind,'data':copy.deepcopy(data)}

def syntax_cases():
    specs=[
        ('multiline_bool','flag = (\n    left in names\n    or right in names\n)\n','flag = (\n    left in names\n    or right in names\n)'),
        ('nested_bool','ready = (a and (b or not c))\n','ready = (a and (b or not c))'),
        ('call','value = build(\n    first,\n    nested(second, third),\n)\n','value = build(\n    first,\n    nested(second, third),\n)'),
        ('if_expression','value = (\n    yes if check else no\n)\n','value = (\n    yes if check else no\n)'),
        ('annotated','value: list[str] = [\n    "a", "b"\n]\n','value: list[str] = [\n    "a", "b"\n]'),
        ('forward_reference','value: "FutureType" = factory()\n','value: "FutureType" = factory()'),
        ('augmented','total += (\n    first + second\n)\n','total += (\n    first + second\n)'),
        ('named_expression','if (item := get_item()) is not None:\n    use(item)\n','item := get_item()'),
        ('chained','first = second = (\n    a + b\n)\n','first = second = (\n    a + b\n)'),
        ('list_comprehension','items = [\n    x * 2 for x in source if x > 0\n]\n','items = [\n    x * 2 for x in source if x > 0\n]'),
        ('dict_comprehension','items = {\n    k: f(k) for k in keys\n}\n','items = {\n    k: f(k) for k in keys\n}'),
        ('lambda','mapper = lambda x: (\n    x + 1\n)\n','mapper = lambda x: (\n    x + 1\n)'),
        ('decorator','@register(\n    "kind", flag=True\n)\ndef handler(x):\n    return x\n','@register(\n    "kind", flag=True\n)'),
        ('unicode','变量 = (\n    "数值" + other\n)\n','变量 = (\n    "数值" + other\n)'),
        ('crlf','value = (\r\n    first + second\r\n)\r\n','value = (\r\n    first + second\r\n)'),
        ('continuation','value = first + \\\n    second\n','value = first + \\\n    second'),
        ('comment','value = (\n    first  # ) is in a comment\n    + second\n)\n','value = (\n    first  # ) is in a comment\n    + second\n)'),
        ('quoted_bracket','value = (\n    ")" + "("\n)\n','value = (\n    ")" + "("\n)'),
        ('multiline_string','text = """alpha\n    significant indentation\nend"""\n','text = """alpha\n    significant indentation\nend"""'),
        ('semicolon','a = 1; b = (\n    2 + 3\n)\n','b = (\n    2 + 3\n)'),
        ('nested_scope','class A:\n    def method(self):\n        value = (\n            self.x or self.y\n        )\n        return value\n','value = (\n            self.x or self.y\n        )'),
        ('async','async def f():\n    value = await (\n        fetch()\n    )\n    return value\n','value = await (\n        fetch()\n    )'),
        ('set_comprehension','items = {\n    x for x in data if x\n}\n','items = {\n    x for x in data if x\n}'),
        ('generator','items = (\n    f(x) for x in data\n)\n','items = (\n    f(x) for x in data\n)'),
    ]
    cases=[]
    for name,text,target in specs:
        a=text.encode().index(target.encode());cases.append({'id':name,'document':document(text,scope=['synthetic-syntax','member_001'],path='case.py',version=ref_version('member_001',1),source_id=name),
            'expected_span':[a,a+len(target.encode())],'expected_value':target,'expected_complete':True})
    for name,text in [('truncated_assignment','x = (\n    a or'),('missing_middle','x = (\n    a +\n    ???\n)\n'),('truncated_json','{"ok": true, "result": {"text": "x = ('),
        ('fragment','    flag = (\n        a or b\n    )\n'),('unknown_prefix','    + rhs\n'),('unclosed_string','value = """not closed\n')]:
        cases.append({'id':name,'document':document(text,scope=['synthetic-syntax','member_001'],path='fragment.py',version=ref_version('member_001',1),source_id=name,complete=False),
            'expected_span':None,'expected_value':None,'expected_complete':False})
    return cases

def synthetic_stream():
    events=[];n=0;scope='controlled-project';a='member_001';b='member_002'
    def add(kind,actor,data):
        nonlocal n;n+=1;events.append(event(n,kind,actor,data));return events[-1]
    for actor in [a,b]:add('issue',actor,{'version':ref_version(actor,1),'description':'controlled two-member module update'})
    texts={'pkg/core.py':'def compute(x):\n    return x + 1\n',
        'pkg/client.py':'from pkg.core import compute\ndef run(x):\n    return compute(x)\n',
        'tests/test_client.py':'from pkg.client import run\ndef test_run():\n    assert run(1) == 2\n'}
    for path,text in texts.items():add('file_observed',a,{'document':document(text,scope=[scope,a],path=path,version=ref_version(a,1),source_id='initial:'+path)})
    add('task',a,{'id':'TA','description':'change core interface','targets':['pkg/core.py'],'owner':a,'status':'open','requires_tools':['replace_file','run_tests']})
    add('task',b,{'id':'TB','description':'adapt client','targets':['pkg/client.py'],'owner':b,'status':'open','requires_tools':['replace_file','run_tests']})
    add('task',b,{'id':'TC','description':'validate client','targets':['tests/test_client.py'],'owner':b,'status':'open','requires_tools':['run_tests']})
    add('task_dependency',a,{'upstream':'TA','downstream':'TB'})
    add('task_dependency',a,{'upstream':'TA','downstream':'TC'})
    add('test',a,{'report_id':'run1','version':ref_version(a,1),'executed':True,'passed':True,'counts':{'passed':1,'failed':0},'selector':['tests/test_client.py']})
    add('file_written',a,{'document':document('def compute(x, delta):\n    return x + delta\n',scope=[scope,a],path='pkg/core.py',version=ref_version(a,2),source_id='write:interface')})
    add('test',a,{'report_id':'run2','version':ref_version(a,2),'executed':True,'passed':False,'counts':{'passed':0,'failed':1},'selector':['tests/test_client.py'],'failure_text':'TypeError: missing delta'})
    add('file_written',a,{'document':document('from pkg.core import compute\ndef run(x):\n    return compute(x, 1)\n',scope=[scope,a],path='pkg/client.py',version=ref_version(a,3),source_id='write:caller')})
    add('test',a,{'report_id':'run3','version':ref_version(a,3),'executed':True,'passed':True,'counts':{'passed':1,'failed':0},'selector':['tests/test_client.py']})
    add('artifact',a,{'artifact_id':'patch1','version':ref_version(a,3),'paths':['pkg/client.py'],'content_identity':'controlled_fixed_patch'})
    add('share_artifact',a,{'artifact_key':a+'\0patch1','recipient':b})
    add('adopt_artifact',b,{'artifact_key':a+'\0patch1','version':ref_version(b,2),'paths':['pkg/client.py']})
    add('file_observed',b,{'document':document('from pkg.core import compute\ndef run(x):\n    return compute(x, 1)\n',scope=[scope,b],path='pkg/client.py',version=ref_version(b,2),source_id='recipient:read_after_merge')})
    add('delivery',a,{'delivery_id':'delivery1','version':ref_version(a,3),'artifact_id':'patch1'})
    add('file_renamed',a,{'old_path':'pkg/core.py','new_path':'pkg/engine.py','version':ref_version(a,4)})
    add('file_deleted',a,{'path':'pkg/client.py','version':ref_version(a,5)})
    add('file_written',a,{'document':document('def broken(:\n',scope=[scope,a],path='pkg/engine.py',version=ref_version(a,6),source_id='malformed:write')})
    add('file_written',a,{'document':document('def compute(x, delta=1):\n    return x + delta\n',scope=[scope,a],path='pkg/engine.py',version=ref_version(a,7),source_id='repair:write')})
    return {'scope':scope,'repo':'controlled/example','commit':'a'*40,'members':[a,b],'events':events,
        'impact_oracles':{events[11]['event_id']:[a+'\0pkg/core.py',a+'\0pkg/client.py',a+'\0tests/test_client.py']}}

def historical_stream(point):
    g=read(point['graph']['path']);scope=point['slot_id'];actor='member_001';sources=sorted(g['sources'].values(),key=lambda s:(s['first_seen_step'],s['message_index'],s['id']))
    actions={};seen=set();events=[];assembler=SourceAssembler();known={};selectors={};documents=[];malformed=[]
    def add(source,kind,data):
        events.append(event(source['id']+':'+kind,kind,actor,data,source_ids=[source['id']],source_kind='historical_wire'))
    initialized=False
    for source in sources:
        m=source['message'];body=obj(m.get('content'));index=source['message_index']
        for call in m.get('tool_calls',[]):actions[call['id']]=call
        if m.get('role')=='user' and body.get('observation') and not body.get('_v117_same_input_static_fields'):
            if ('state',index) in seen:continue
            seen.add(('state',index));o=body['observation'];v=o.get('workspace_reference')
            if not v:continue
            if not initialized:add(source,'issue',{'version':v,'description':o.get('root_goal',{}).get('description','')});initialized=True
            else:add(source,'version',{'version':v})
        if m.get('role')!='tool' or ('tool',index) in seen:continue
        seen.add(('tool',index));call=actions.get(m.get('tool_call_id'))
        if not call:continue
        name=call['function']['name'];args=obj(call['function'].get('arguments'));r=body.get('result',{});r=r if isinstance(r,dict) else {};v=r.get('source_reference')
        if not body:
            malformed.append(source['id']);add(source,'unknown_observation',{'reason':'malformed_legacy_tool_JSON','text_sha256':source['message_sha256']});continue
        if body.get('ok') is not True:add(source,'rejected_operation',{'tool':name,'error':body.get('error')});continue
        if name=='read_file' and v and isinstance(r.get('text'),str) and r.get('path'):
            path=r['path'];span=[r.get(k) for k in ['start_character','end_character','total_characters']]
            if all(type(x)is int for x in span):doc=assembler.add(scope=[scope,actor],path=path,version=v,start=span[0],end=span[1],total=span[2],text=r['text'],source_id=source['id'],message_sha256=source['message_sha256'])
            else:doc=document(r['text'],scope=[scope,actor],path=path,version=v,source_id=source['id'],complete=False,evidence=[{'message_sha256':source['message_sha256'],'extent_unknown':True}])
            documents.append(doc);known[(path,sha(v))]=doc;add(source,'file_observed',{'document':doc})
        elif name in {'write_file','create_file'} and v and isinstance(args.get('text'),str):
            doc=document(args['text'],scope=[scope,actor],path=args['path'],version=v,source_id=source['id'],complete=True,
                evidence=[{'kind':'complete_write_argument_plus_successful_receipt','tool_call_id':call['id'],'receipt_message_sha256':source['message_sha256']}])
            documents.append(doc);known[(args['path'],sha(v))]=doc;add(source,'file_written',{'document':doc})
        elif name in {'replace_file','delete_file','rename_file','integrate_patch'} and v:
            # No full postimage is guessed from partial source or a three-way merge.
            paths=r.get('paths') or r.get('changed_paths') or ([args['path']] if args.get('path') else [])
            if name=='delete_file' and args.get('path'):add(source,'file_deleted',{'path':args['path'],'version':v})
            else:add(source,'file_unknown',{'paths':paths,'version':v,'reason':'successful_receipt_without_complete_postimage'})
        elif name in {'run_tests','read_test_result'} and r.get('report_id') and v:
            rid=r['report_id']
            if name=='run_tests':selectors[rid]=args.get('selection')
            text=r.get('page',{}).get('text','')
            add(source,'test',{'report_id':rid,'version':v,'executed':r.get('executed') is True,'passed':r.get('passed'),'counts':r.get('counts'),
                'selector':selectors.get(rid),'failure_text':text[:512] if r.get('passed') is False and isinstance(text,str) else None})
        elif name=='fix_patch' and v and r.get('patch_id'):add(source,'artifact',{'artifact_id':r['patch_id'],'version':v,'paths':r.get('paths',[])})
        elif name=='submit_integration' and v and r.get('delivery_id'):add(source,'delivery',{'delivery_id':r['delivery_id'],'version':v,'artifact_id':r.get('patch_id')})
    return {'scope':scope,'repo':point['repo'],'commit':point['base_commit'],'members':[actor],'events':events,'documents':documents,'malformed_sources':malformed,'source_point':point['point']}
