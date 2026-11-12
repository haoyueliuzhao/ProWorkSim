"""Seal manually chosen prefix facts; never reads treatment outputs or scores."""
import sys,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from proworksim.software_context_graph_check_v196 import at,recover_field
from proworksim.software_context_graph_v196 import obj
BASE=ROOT/'artifacts/software-benchmark-v201';RUN=ROOT/'runs/software-benchmark-v201/source-prefix-r1'

def seal(point,decision,items):
    dest=BASE/'annotations-r1'/f'{point}.json'
    if dest.exists():raise ValueError('No revising a sealed prefix annotation')
    packet=read(RUN/point/'review-packet.json.gz');sources=packet['source_messages'];rows=[]
    for n,item in enumerate(items,1):
        matches=[s for s in sources.values() if s['message_index']==item['message_index']]
        if not matches:raise ValueError('No source at requested stable index')
        # The exact message variant actually offered at this decision is preferred.
        frame=read(RUN/point/'common-frame.json.gz')
        visible=[s for s in matches if s['message'] in frame['messages']]
        s=(visible or matches)[-1];channel=item.get('channel','body');pointer=item['pointer'];m=s['message']
        if channel=='body':value=at(obj(m.get('content')),pointer)
        elif channel=='message':value=at(m,pointer)
        else:value=at(obj(m['tool_calls'][item.get('call_index',0)]['function']['arguments']),pointer)
        origin={'source_id':s['id'],'message_index':s['message_index'],'message_sha256':s['message_sha256'],'channel':channel,'pointer':pointer}
        if channel=='arguments':origin['call_index']=item.get('call_index',0)
        if 'needle' in item:
            begin=value.index(item['needle'])
            if item.get('lines'):
                begin=value.rfind('\n',0,begin)+1;end=begin
                for _ in range(item['lines']):
                    pos=value.find('\n',end);end=len(value) if pos<0 else pos+1
            else:end=begin+len(item['needle'])
            origin['span']=[begin,end];value=value[begin:end]
        recover_field({'origin':origin,'value':value},sources)
        body=obj(m.get('content'));result=body.get('result',{});result=result if isinstance(result,dict) else {}
        version=result.get('source_reference') or body.get('observation',{}).get('workspace_reference')
        rows.append({'id':f'{point}-R{n:02d}','value':value,'origins':[origin],
            'factuality':'literal_source_verified','provenance':'captured_request_and_hash_verified','source_version':version,
            'version_validity':'current' if version and version==packet['current_version'] else 'historical' if version else 'unknown',
            'relevance':item['label'],'necessity':'primary_AI_required_for_stated_decision' if item['label']=='necessary' else 'not_claimed',
            'rationale':item['reason'],'complementarity':item.get('complements',[]),'redundancy':item.get('redundancy','not_fully_adjudicated'),
            'recoverability':'to_be_measured_from_each_view_not_inferred_from_storage'})
    save(dest,{'point':point,'decision':decision,'review_mode':'primary_AI_prefix_review; no human or independent gold claim',
        'source_packet':ref(RUN/point/'review-packet.json.gz'),'reference_facts':rows,'method_views_seen':False,'future_response_or_score_seen':False})
    print(point,len(rows),'references sealed')

def main():
    spec=read(Path(sys.argv[1]))
    for p in spec:seal(p['point'],p['decision'],p['items'])
if __name__=='__main__':main()
