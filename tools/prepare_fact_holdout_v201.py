"""Open only frozen task identities' source prefixes. No outputs or scores."""
import sys,copy,json,sqlite3,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from proworksim.software_history_source_v201 import WireIdentity,verify_request_capture
from proworksim.software_context_graph_v196 import ObservedWorkGraph
from proworksim.software_context_graph_check_v196 import verify_graph
from proworksim.software_context_compression_v175 import CONTEXT_READ_TOOL,digest
from proworksim.software_global_evidence_v198 import enrich,query_text
from proworksim.software_fact_context_v199 import FactInventory
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
import run_fact_context_v199 as counts
BASE=ROOT/'artifacts/software-benchmark-v201';RUN=ROOT/'runs/software-benchmark-v201/source-prefix-r1'
HISTORY=ROOT/'runs/software-benchmark-v142/role-pilot40-r1'

def main():
    if (BASE/'source-admission-r1/summary.json').exists():raise ValueError('Preserve first admission')
    plan=read(BASE/'protocol-r1/plan.json');old=read(HISTORY/'deployment-v143/execution-plan.json');counts.initialize()
    db=sqlite3.connect((HISTORY/'ledgers/pilot.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    tasks=[];points=[]
    for number,task in enumerate(plan['tasks'],1):
        candidates=[r for r in old['rows'] if r['instance_id']==task['instance_id'] and r['group_id']=='S1']
        if not candidates:tasks.append({**task,'admission':'missing_original_S1_identity'});continue
        row=min(candidates,key=lambda r:r['slot_index']);folder=HISTORY/'episodes'/str(row['slot_index'])/'controller-output/model-ledger/member_001'
        ledger=read(folder/'ledger.json');calls=sorted([c for c in ledger['calls'] if c['usage_id']=='agent'],key=lambda c:c['attempt'])
        ids=WireIdentity();g=ObservedWorkGraph(row['slot_id'],'member_001');chosen=[];receipts=[];errors=[];first=False;second=False
        for index,call in enumerate(calls,1):
            if first and second:break
            path=folder/f"request-{call['attempt']:04d}.json"
            try:
                provider=db.execute('SELECT status,request_sha256,slot_id,usage_id FROM requests WHERE request_id=?',(call['request_id'],)).fetchone()
                if provider is None:raise ValueError('No exact provider request identity')
                wire=verify_request_capture(path,call,dict(provider),expected_slot=row['slot_id']);indices=ids.assign(wire,call['request_id'])
                g.ingest(wire,step=index-1,source_indices=indices)
                receipts.append({'request_id':call['request_id'],'decision_index':index,'client_capture':ref(path),'provider_request_sha256':provider['request_sha256'],'status':provider['status']})
                tool_count=sum(m.get('role')=='tool' for m in wire['messages']);select=None
                if not first and index>=12 and tool_count>=12:first=True;select='first_after12_prior_tools'
                if not second and index>=24:second=True;select='decision24' if not select else select+'+decision24'
                if not select:continue
                point=f'H{number:02d}-{len(chosen)+1}';target=RUN/point;snapshot=g.snapshot()
                checked=verify_graph(snapshot,episode=row['slot_id'],member='member_001',step=index-1,witnesses={(w['derived_index'],w['message_sha256']) for w in ids.witnesses})
                # Common read-only recall schema is a counterfactual solving interface,
                # not a fabricated historical message or claimed original tool.
                frame=copy.deepcopy(wire)
                added=not any(t['function']['name']=='context_read' for t in frame.get('tools',[]))
                if added:frame.setdefault('tools',[]).append(copy.deepcopy(CONTEXT_READ_TOOL))
                enriched=copy.deepcopy(g);enrich(enriched,frame,indices)
                st=SourceLabeledHistoryReader(point,row['slot_id'],'member_001');_,masked,cut=baseline(frame,st,counts.count,indices)
                inv=FactInventory(enriched,frame,indices,masked,cut)
                rec={**task,'point':point,'slot_id':row['slot_id'],'slot_index':row['slot_index'],'decision_index':index,
                    'request_id':call['request_id'],'choice_rule':select,'tool_observations_in_current_input':tool_count,
                    'wire':save(target/'wire.json.gz',wire),'frame':save(target/'common-frame.json.gz',frame),'indices':indices,
                    'graph':save(target/'graph.json.gz',enriched.snapshot()),'inventory':save(target/'fact-inventory.json.gz',inv.snapshot()),
                    'graph_checks':checked,'common_readonly_recall_schema_added':added,'source_receipts':save(target/'prefix-receipts.json',receipts),
                    'source_witnesses':save(target/'source-witnesses.json.gz',ids.witnesses),'static_projection_links':save(target/'static-links.json.gz',ids.static_links)}
                points.append(rec);chosen.append(point)
                recent=frame['messages'][cut:] if cut else frame['messages']
                save(target/'review-packet.json.gz',{'point':point,'task_query':query_text(frame,enriched),'current_version':enriched.nodes[enriched.current_version]['attrs']['source_reference'] if enriched.current_version else None,
                    'recent_window':recent,'candidate_groups':inv.pool,'facts':inv.facts,'source_messages':enriched.sources,
                    'instructions':'Primary AI development reference only; cite exact spans; no selector views, future responses or terminal outcomes. Need not call any old fact necessary when current context suffices.'})
            except Exception as e:errors.append({'decision_index':index,'error':repr(e)});break
        tasks.append({**task,'slot_id':row['slot_id'],'slot_index':row['slot_index'],'points':chosen,'checked_agent_inputs':len(receipts),
            'errors':errors,'admission':'qualified' if chosen and not errors else 'source_failure' if errors else 'no_frozen_point_available'})
        print(task['instance_id'],len(chosen),'points',errors,flush=True)
    db.close();save(BASE/'source-admission-r1/summary.json',{'version':'v201-real-input-prefix-admission-r1','tasks':tasks,'points':points,
        'planned_tasks':12,'qualified_tasks':sum(t['admission']=='qualified' for t in tasks),'actual_points':len(points),
        'model_outputs_or_terminal_scores_read':False,'source_index_semantics':'derived stable identities from actual wire tool call IDs and registered original observation hashes; not original SDK history indices',
        'common_counterfactual_recall_tool':'same read-only context_read schema added to A/B/C if legacy source lacks it; all texts remain actual wire source',
        'new_API_calls':0,'new_Docker_GPU':0})
if __name__=='__main__':main()
