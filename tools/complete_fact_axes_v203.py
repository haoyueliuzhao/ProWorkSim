"""Four completeness axes over verified observer-side full-file postimages."""
import gzip,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inventory_multimember_v203 import ROOT,read,save,ref
from proworksim.software_dual_graph_v203 import completeness
from proworksim.software_syntax_facts_v202 import SyntaxFacts,document
OUT=ROOT/'artifacts/software-benchmark-v203/completeness-axes-r1'
def main():
    save(OUT/'protocol.json',{'source':ref(Path(__file__)),'mapper':ref(ROOT/'src/proworksim/software_dual_graph_v203.py'),
        'sources':'source-audit-r1 verified captured postimages only; no terminal/future workspace','observer_only':True,'new_model_inputs':0})
    engine=SyntaxFacts();rows=[];totals={'documents':0,'facts':0,'span_complete':0,'statement_complete':0,'scope_complete':0,'file_complete':0,'source_violations':0};start=time.process_time()
    for p in sorted((ROOT/'runs/software-benchmark-v203/source-audit-r1').glob('*-events.json.gz')):
        payload=json.loads(gzip.decompress(p.read_bytes()));entries=[]
        for capture in payload['source_capture']:
            if capture['status']!='complete_verified':continue
            for d in capture['documents']:
                if not d['path'].endswith('.py'):continue
                doc=document(d['text'],scope=[p.stem,capture['actor']],path=d['path'],version=d['version'],source_id=capture['event_id'],complete=True,evidence=[capture['source']])
                result=engine.extract(doc,'A2');totals['documents']+=1
                for f in result['facts']:
                    axes=completeness(f);f['completeness_axes']=axes;totals['facts']+=1
                    for k in ['span_complete','statement_complete','scope_complete','file_complete']:totals[k]+=axes[k]
                    totals['source_violations']+=doc['text'].encode()[f['start_byte']:f['end_byte']].decode()!=f['value']
                entries.append({'event_id':capture['event_id'],'actor':capture['actor'],'path':d['path'],'facts':result['facts'],'diagnostics':result['diagnostics'],'observer_only':True})
        dst=ROOT/'runs/software-benchmark-v203/completeness-axes-r1'/p.name;dst.parent.mkdir(parents=True,exist_ok=True)
        with dst.open('xb') as f:f.write(gzip.compress(json.dumps(entries,ensure_ascii=False).encode(),mtime=0))
        rows.append({'source':ref(p),'result':ref(dst),'document_occurrences':len(entries),'fact_occurrences':sum(len(e['facts']) for e in entries)})
    save(OUT/'summary.json',{'totals':totals,'CPU_seconds':time.process_time()-start,'rows':rows,'all_documents_observer_only':True,
        'actual_agent_fact_uses':0,'semantic_necessity_proven':False,'scope_complete_is_source_extent_not_runtime_dependency_completeness':True})
    print(json.dumps(totals))
if __name__=='__main__':main()
