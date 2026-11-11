"""Independent JSON-level checks; does not import the graph builder/selector.

This is a separate verification implementation, not an external human review
or an independent semantic gold-standard annotation.
"""
from __future__ import annotations
import ast
import hashlib
import json
import textwrap


def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def parsed(value):
    try:x=json.loads(value)
    except (TypeError,ValueError):return {}
    return x if isinstance(x,dict) else {}


def at(value,path):
    for part in path.strip('/').split('/') if path else []:
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def recover_field(field,sources):
    origin=field['origin'];m=sources[origin['source_id']]['message'];channel=origin['channel']
    if channel=='body':value=at(parsed(m.get('content')),origin['pointer'])
    elif channel=='arguments':value=at(parsed(m['tool_calls'][origin['call_index']]['function']['arguments']),origin['pointer'])
    elif channel=='message':value=at(m,origin['pointer'])
    else:raise AssertionError('Unsupported provenance channel')
    if 'span' in origin:
        a,b=origin['span'];assert isinstance(value,str) and 0<=a<=b<=len(value)
        value=value[a:b]
    assert value==field['value'],'Selected field is not the exact observed source value'
    return value


def syntax_texts(source):
    message=source['message'];texts=[]
    if message.get('role')=='tool':
        r=parsed(message.get('content')).get('result',{})
        if isinstance(r,dict) and isinstance(r.get('text'),str):texts.append((r.get('path'),r['text']))
    for call in message.get('tool_calls',[]):
        args=parsed(call['function'].get('arguments'))
        if isinstance(args.get('text'),str):texts.append((args.get('path'),args['text']))
    results=[]
    for path,text in texts:
        try:tree=ast.parse(textwrap.dedent(text))
        except (SyntaxError,ValueError):continue
        results.append((path,text,tree))
    return results


def verify_graph(graph,*,episode,member,step,witnesses):
    assert graph['scope']==[episode,member] and graph['step']==step
    nodes,edges,sources=graph['nodes'],graph['edges'],graph['sources']
    checked_fields=0;action_map={};current_evidence=[];initial_reads=[]
    for sid,source in sources.items():
        assert source['id']==sid and source['scope']==[episode,member]
        assert source['first_seen_step']<=step and sha(source['message'])==source['message_sha256']
        assert (source['message_index'],source['message_sha256']) in witnesses,'Source was not actually visible before this decision'
        for call in source['message'].get('tool_calls',[]):action_map[call['id']]=(source,call)
    for source in sorted(sources.values(),key=lambda s:s['message_index']):
        message=source['message'];body=parsed(message.get('content'));result=body.get('result',{})
        result=result if isinstance(result,dict) else {};reference=result.get('source_reference')
        observation=body.get('observation',{})
        if isinstance(observation,dict) and isinstance(observation.get('workspace_reference'),dict):
            current_evidence.append((source['message_index'],observation['workspace_reference']))
        action=action_map.get(message.get('tool_call_id'))
        if action and body.get('ok') is True:
            name=action[1]['function']['name'];args=parsed(action[1]['function'].get('arguments'))
            if name in {'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'} and reference:
                current_evidence.append((source['message_index'],reference))
            if name=='read_file' and not args.get('patch_id') and reference:initial_reads.append((source['message_index'],reference))
    expected=(max(current_evidence,key=lambda r:r[0])[1] if current_evidence else min(initial_reads,key=lambda r:r[0])[1] if initial_reads else None)
    if expected is not None:
        assert nodes[graph['current_version']]['attrs']['source_reference']=={k:expected[k] for k in ('object_id','version_id')},'Current version was reverted by historical evidence'
    elif graph['current_version'] is not None:raise AssertionError('Unobserved current code version')
    runs={}
    for nid,n in nodes.items():
        assert n['id']==nid and n['scope']==[episode,member] and n['first_seen_step']<=step
        assert n['sources'] and all(s in sources for s in n['sources'])
        if n['type']=='TestRun':
            report=n['attrs']['report_id'];assert report not in runs,'One execution became several test nodes';runs[report]=nid
            for sid in n['sources']:
                m=sources[sid]['message'];body=parsed(m.get('content'));r=body.get('result',{})
                assert body.get('ok') is True and r.get('report_id')==report
                assert action_map[m['tool_call_id']][1]['function']['name'] in {'run_tests','read_test_result'}
            if n['attrs'].get('run_id'):
                assert any(parsed(sources[s]['message'].get('content')).get('result',{}).get('report_event',{}).get('operation_id')==n['attrs']['run_id'] for s in n['sources'])
    facts_by_proof={}
    for eid,e in edges.items():
        assert e['id']==eid and e['source'] in nodes and e['target'] in nodes
        assert e['first_seen_step']<=step and e['sources'] and all(s in sources for s in e['sources'])
        assert e['status'] in {'Confirmed','Inferred'}
        if e['status']=='Inferred':continue
        assert e['type']!='depends_on','Unverified dependency was promoted to fact'
        a,b=nodes[e['source']],nodes[e['target']]
        proof=e['proof'];facts_by_proof[proof]=facts_by_proof.get(proof,0)+1
        if proof=='static_syntax':
            found=False
            for sid in e['sources']:
                for path,text,tree in syntax_texts(sources[sid]):
                    if path!=a['attrs'].get('path'):continue
                    if e['type']=='contains':
                        found |= any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==b['attrs'].get('symbol') and n.lineno==b['attrs'].get('source_line') for n in ast.walk(tree))
                    elif e['type']=='imports':
                        imports=[]
                        for n in ast.walk(tree):
                            if isinstance(n,ast.Import):imports += [v.name for v in n.names]
                            if isinstance(n,ast.ImportFrom):imports.append('.'*n.level+(n.module or ''))
                        found |= b['attrs'].get('module') in imports
                    elif e['type']=='calls':
                        for n in ast.walk(tree):
                            if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name!=a['attrs'].get('symbol') or n.lineno!=a['attrs'].get('source_line'):continue
                            stack=list(n.body)
                            while stack:
                                child=stack.pop()
                                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):continue
                                stack.extend(ast.iter_child_nodes(child))
                                if isinstance(child,ast.Call) and ast.unparse(child.func)==b['attrs'].get('symbol'):found=True
            assert found,'Static edge lacks the stated visible syntax'
        elif e['type']=='validates':
            assert a['type']=='TestRun' and b['type']=='Version'
            assert e['attrs']['scope']=='selected_public_tests_only' and e['attrs']['attempt_not_full_correctness'] is True
            assert any(parsed(sources[s]['message'].get('content')).get('result',{}).get('executed') is True and
                parsed(sources[s]['message'].get('content'))['result'].get('source_reference')==b['attrs']['source_reference'] for s in e['sources'])
        elif e['type']=='modifies':
            assert a['type']=='Action' and b['type']=='Code'
            assert any(sources[s]['message'].get('tool_call_id')==a['attrs']['tool_call_id'] and parsed(sources[s]['message'].get('content')).get('ok') is True for s in e['sources'])
        elif e['type']=='supersedes':
            assert a['type']=='Version' and b['type']=='Version' and proof=='observed_version_transition'
            assert e['attrs']['old_tests_do_not_validate_new_version'] is True
        elif e['type']=='derived_from':assert a['type']=='Artifact' and b['type']=='Version'
        elif e['type']=='tests':assert a['type']=='TestRun' and e['attrs']['semantics']=='reported_or_selected_location_not_runtime_coverage'
        else:assert proof in {'observed_source','same_evidence_read','report_binding','successful_tool'}
    for event in graph['events'].values():
        assert event['first_seen_step']<=step and event['node'] in nodes
        for field in event['fields']:
            recover_field(field,sources);checked_fields+=1
    return {'sources':len(sources),'nodes':len(nodes),'edges':len(edges),'test_runs':len(runs),
        'fact_fields_verified':checked_fields,'confirmed_proofs':facts_by_proof,
        'future_or_foreign_sources':0,'independent_checker_not_external_human_review':True}


def verify_view(raw,view,proof,graph,store,*,count,indices):
    assert raw.get('tools')==view.get('tools') and len(raw['messages'])==len(view['messages'])
    tools=[i for i,m in enumerate(raw['messages']) if m.get('role')=='tool']
    cutoff=tools[-5] if len(tools)>5 else 0
    if cutoff:assert raw['messages'][cutoff:]==view['messages'][cutoff:]
    assert raw['messages'][:2]==view['messages'][:2]
    for a,b in zip(raw['messages'],view['messages']):
        assert (a.get('role'),a.get('tool_call_id'),a.get('tool_calls'))==(b.get('role'),b.get('tool_call_id'),b.get('tool_calls'))
        if a.get('role') in {'assistant','system'}:assert a==b
    masked_indices={m['index'] for m in proof['masked']}
    for i,(a,b) in enumerate(zip(raw['messages'],view['messages'])):
        if i not in masked_indices:assert a==b,'Unselected message was changed'
    ids=[x['event_id'] for x in proof['selected']];assert len(ids)==len(set(ids))
    assert len(ids)<=8 and proof['added_content_tokens_local_estimate']<=4096
    amount=0;fields=0
    for selected in proof['selected']:
        text=view['messages'][selected['anchor']]['content'];amount+=count(text)
        assert count(text)<=768
        card=selected['card'];assert card['text_is_not_new_validation'] is True
        assert json.loads(text.split('\n',1)[1])==card,'Proof differs from actual presented card'
        assert len(card['facts'])==len(selected['selected_fields'])
        path=selected['rank_reason'].get('dependency_path',[])
        assert len(path)<=2
        for eid in path:
            edge=graph['edges'][eid]
            assert edge['attrs'].get('version') in (None,graph['current_version']),'Stale dependency used for current query'
        for fact,field in zip(card['facts'],selected['selected_fields']):
            assert fact['value']==recover_field(field,graph['sources']);fields+=1
        if selected['card']['version_status']=='current_observed_version':
            assert selected['card']['source_version']==graph['nodes'][graph['current_version']]['attrs']['source_reference']
        for reference in card['originals']:
            entry=store.entries[reference]
            assert [entry['slot_id'],entry['member_id']]==graph['scope']
            assert hashlib.sha256(entry['text'].encode()).hexdigest()==entry['text_sha256']
            assert any(s['message_index']==entry['message_index'] and s['message'].get('content')==entry['text'] for s in graph['sources'].values())
    assert amount==proof['added_content_tokens_local_estimate']
    for marker in proof['masked']:
        original=raw['messages'][marker['index']]['content'];entry=store.entries[marker['reference']]
        assert entry['text']==original and entry['message_index']==indices[marker['index']]
    return {'checked_selected_fields':fields,'duplicate_L1_entities':0,'permission_errors':0,
        'preserved_recent_window_and_actions':True,'exact_originals_available':True}
