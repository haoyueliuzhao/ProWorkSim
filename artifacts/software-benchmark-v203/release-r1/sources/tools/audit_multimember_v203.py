"""Trace selected historical task/patch/test ownership to source receipts and inputs."""
from __future__ import annotations
import collections,copy,gzip,json,sys,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inventory_multimember_v203 import ROOT,read,ref,save,sha
from proworksim.software_dual_graph_v203 import CrossGraph,CompleteSourceReplay,identity
from proworksim.software_syntax_facts_v202 import IncrementalSyntax

OUT=ROOT/'artifacts/software-benchmark-v203/source-audit-r1'
RUN=ROOT/'runs/software-benchmark-v203/source-audit-r1'
def savegz(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(gzip.compress(json.dumps(d,ensure_ascii=False).encode(),mtime=0))
def obj(text):
    try:return json.loads(text) if isinstance(text,str) else {}
    except (ValueError,TypeError):return {}
def actual_inputs(folder,controller):
    path=folder/'model-ledger/ledger.json';ledger=read(path);errors=[];presentations={};requests=[];tokens=collections.Counter()
    for call in ledger['calls']:
        request=call.get('request')
        if not request:continue
        parts=Path(request['path']).parts;p=folder/'model-ledger'/parts[-2]/parts[-1];member=parts[-2];actual=ref(p)
        if actual['sha256']!=request['sha256'] or actual['bytes']!=request['bytes']:errors.append(['request_hash',str(p)]);continue
        payload=read(p);w={'request_id':call.get('request_id'),'member':member,'request':actual,'usage':call.get('usage'),'usage_id':call.get('usage_id')}
        requests.append(w);usage=call.get('usage')
        if usage:
            if usage['prompt_tokens']+usage['completion_tokens']!=usage['total_tokens']:errors.append(['usage_arithmetic',w['request_id']])
            tokens.update(input_tokens=usage['prompt_tokens'],output_tokens=usage['completion_tokens'],total_tokens=usage['total_tokens'])
        if call.get('usage_id')!='agent':continue
        for mi,m in enumerate(payload.get('request',{}).get('messages',[])):
            if m.get('role')!='user':continue
            o=obj(m.get('content')).get('observation',{})
            if not isinstance(o,dict):continue
            if o.get('actor_id') and o['actor_id']!=member:errors.append(['foreign_actor_input',w['request_id']]);continue
            for kind in ['messages','handoffs']:
                for event in o.get(kind,[]):
                    if not isinstance(event,dict) or event.get('recipient')!=member:continue
                    key=(member,event.get('sequence'))
                    presentations.setdefault(key,{**w,'message_index':mi,'kind':kind,'event':event,'observed_logical_time':o.get('logical_time')})
    if tokens['total_tokens']!=ledger['known_actual_tokens']:errors.append(['usage_total_mismatch',tokens['total_tokens'],ledger['known_actual_tokens']])
    return {'ledger':ref(path),'requests':requests,'tokens':dict(tokens),'errors':errors},presentations

def audit_one(row):
    started=time.perf_counter();p=Path(row['controller']['path']);actual=ref(p)
    if actual!=row['controller']:raise ValueError('Inventory source changed')
    controller=read(p);outcomes=controller['managed_boundary']['outcomes'];scope=row['slot_id'];members=controller['fixed_members'];events=[]
    for i,o in enumerate(outcomes):
        dec=o.get('decision',{});r=o.get('response',{})
        if not dec.get('action') or not o.get('action_performed'):continue
        events.append({'id':f'{row["slot_index"]}:{i}','step':i,'logical_time':r.get('logical_time'),'actor':o['worker_id'],'action':dec['action'],
            'arguments':dec.get('arguments',{}),'ok':r.get('ok') is True,'result':r.get('result',{}) if isinstance(r.get('result'),dict) else {},'error':r.get('error'),
            'source':{'file':actual,'pointer':f'/managed_boundary/outcomes/{i}','record_sha256':identity(o),'command_id':r.get('command_id')}})
    graph=CrossGraph(scope,members);baseline=p.parent/'project-baseline-snapshot.json';capture=CompleteSourceReplay(read(baseline),members);errors=[];comparisons=[];syntax=IncrementalSyntax()
    for event in events:
        try:graph.observe(event)
        except Exception as e:errors.append({'event_id':event['id'],'projection_error':repr(e)})
        record=capture.observe(event)
        if record and record['status']=='complete_verified':
            for doc in record['documents']:
                if not doc['path'].endswith('.py'):continue
                t,cost=syntax.parse((event['actor'],doc['path']),doc['text']);fresh=syntax.engine.parser.parse(doc['text'].encode())
                comparisons.append({'event_id':event['id'],'path':doc['path'],'source_hash':doc['source_hash'],'current_tree_equals_fresh':str(t.root_node)==str(fresh.root_node),
                    'full_parse_has_error':fresh.root_node.has_error,'used_old_tree_edit':not cost['cache_hit'] and cost['edit_range'] is not None and syntax.incremental_parses>sum(c['used_old_tree_edit'] for c in comparisons),**cost})
    wire,presentations=actual_inputs(p.parent,controller);errors.extend(wire['errors']);chains=[]
    for e in events:
        if not e['ok'] or e['action']!='handoff_patch':continue
        r=e['result'];patch=graph.patches.get(r['patch_id']);recipient=r['recipient'];sequence=r['handoff_sequence'];shown=presentations.get((recipient,sequence))
        retrievals=[x for x in events if x['step']>e['step'] and x['actor']==recipient and x['ok'] and x['action']=='read_file' and x['arguments'].get('patch_id')==r['patch_id'] and x['result'].get('source_reference')==patch['source_reference']]
        adopts=[x for x in events if x['step']>e['step'] and x['actor']==recipient and x['ok'] and x['action']=='integrate_patch' and x['arguments'].get('patch_id')==r['patch_id']]
        validations=[x for adoption in adopts for x in events if x['step']>adoption['step'] and x['actor']==recipient and x['ok'] and x['action']=='run_tests' and x['result'].get('executed') is True and x['result'].get('source_reference')==adoption['result']['source_reference']]
        if shown and (shown['event'].get('patch_id')!=r['patch_id'] or shown['event'].get('source_reference')!=patch['source_reference']):errors.append(['presentation_identity_mismatch',e['id']])
        chains.append({'handoff':e['id'],'patch_id':r['patch_id'],'author':patch['author'],'recipient':recipient,'source_version':patch['source_reference'],
            'harness_delivered':True,'presented_in_captured_model_request':bool(shown),'presentation_witness':shown,'explicit_source_reads':[x['id'] for x in retrievals],
            'actual_adoptions':[x['id'] for x in adopts],'adopted_version_test_runs':[x['id'] for x in validations],
            'adopted_version_public_test_passed':any(x['result']['passed'] is True for x in validations),'understanding_not_measured':True})
    for i,snap in enumerate(graph.snapshots):
        expected={t:trow['owner'] for t,trow in snap['tasks'].items() if trow.get('owner')}
        represented={x['target']:x['source'] for x in snap['edges'] if x['kind']=='owns'}
        if expected!=represented:errors.append(['ownership_projection',i])
    summary={'slot_index':row['slot_index'],'instance_id':row['instance_id'],'group':row['organization_id'],'members':members,'controller':actual,'baseline':ref(baseline),
        'events':len(events),'snapshots':len(graph.snapshots),'edge_types':dict(collections.Counter(e['kind'] for e in graph.edges)),'actual_transfer_accepts':sum(e['ok'] and e['action']=='accept_transfer' for e in events),
        'explicit_dependency_receipts':sum(e['ok'] and e['action']=='declare_dependency' for e in events),'source_capture':dict(collections.Counter(r['status'] for r in capture.records)),
        'captured_complete_file_occurrences':sum(len(r['documents']) for r in capture.records),'unknown_capture_reasons':dict(collections.Counter(r.get('reason') for r in capture.records if r['status']=='unknown')),
        'consecutive_source_parse_checks':len(comparisons),'actual_old_tree_edits':syntax.incremental_parses,'incremental_parse_mismatches':sum(not c['current_tree_equals_fresh'] for c in comparisons),
        'historical_model_requests_verified':len(wire['requests']),'historical_tokens':wire['tokens'],'handoff_chains':chains,'errors':errors,'wall_seconds':time.perf_counter()-started}
    savegz(RUN/f'{row["slot_index"]}-events.json.gz',{'events':events,'edges':graph.edges,'snapshots':graph.snapshots,'source_capture':capture.records,'parser_checks':comparisons,'wire_audit':wire})
    save(OUT/f'task-{row["slot_index"]}.json',summary);return summary

def main():
    selection=read(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/selection.json')
    save(OUT/'protocol.json',{'selection':ref(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/selection.json'),
        'sources':[ref(Path(__file__)),ref(ROOT/'src/proworksim/software_dual_graph_v203.py')],
        'source_capture':'initial observer snapshot + prior accepted exact edits, require original whole-tree receipt hash; no future final tree used',
        'new_inputs_to_agents':0,'new_API_calls':0,'new_scoring':0,'no_counterfactual_task_results':True})
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('fork')) as pool:rows=list(pool.map(audit_one,selection))
    result={'tasks':len(rows),'groups':dict(collections.Counter(r['group'] for r in rows)),'events':sum(r['events'] for r in rows),
        'source_capture':dict(sum((collections.Counter(r['source_capture']) for r in rows),collections.Counter())),
        'captured_complete_file_occurrences':sum(r['captured_complete_file_occurrences'] for r in rows),'historical_requests_verified':sum(r['historical_model_requests_verified'] for r in rows),
        'historical_tokens':dict(sum((collections.Counter(r['historical_tokens']) for r in rows),collections.Counter())),
        'actual_old_tree_edits':sum(r['actual_old_tree_edits'] for r in rows),'consecutive_source_parse_checks':sum(r['consecutive_source_parse_checks'] for r in rows),
        'incremental_parse_mismatches':sum(r['incremental_parse_mismatches'] for r in rows),'errors':[{'slot_index':r['slot_index'],'errors':r['errors']} for r in rows if r['errors']],
        'actual_transfer_accepts':sum(r['actual_transfer_accepts'] for r in rows),'explicit_dependency_receipts':sum(r['explicit_dependency_receipts'] for r in rows),
        'edge_types':dict(sum((collections.Counter(r['edge_types']) for r in rows),collections.Counter()))}
    chains=[c for r in rows for c in r['handoff_chains']];result['handoff_chain_counts']={'handoffs':len(chains),'presented':sum(c['presented_in_captured_model_request'] for c in chains),
        'explicit_source_read':sum(bool(c['explicit_source_reads']) for c in chains),'adopted_after_handoff':sum(bool(c['actual_adoptions']) for c in chains),
        'tested_adopted_version':sum(bool(c['adopted_version_test_runs']) for c in chains),'passed_public_tests_on_adopted_version':sum(c['adopted_version_public_test_passed'] for c in chains)}
    result.update(new_API_calls=0,new_model_tokens=0,G0_source_audit_pass=not result['errors'],G1_observed_mapping_pass=not result['errors'],real_reassignment_effect_verified=False)
    save(OUT/'summary.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
