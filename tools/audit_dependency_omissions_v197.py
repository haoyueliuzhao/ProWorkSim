"""Explain independently marked essential events missed by frozen selectors."""
import json,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/software-benchmark-v197'
def read(p):return json.loads(p.read_bytes())
def main():
    mapping=read(BASE/'private-map-r1/manifest.json')['points'];result=read(BASE/'annotated-results-r1/summary.json');rows=[]
    for p in mapping:
        labels=read(BASE/'adjudicator-r1'/f'{p["point"]}.json')['labels']
        brief=read(ROOT/'runs/software-benchmark-v197/blind-material-r1'/p['point']/'brief.json')
        catalog={e['id']:e for e in brief['historical_candidates']}
        for label in labels:
            if label['label']!='essential':continue
            e=catalog[label['event']];row={'point':p['point'],'instance_id':p['instance_id'],'event':e['id'],'kind':e['kind'],
                'paths':e['paths'],'version':e['version_status'],'reason':label['reason'],'source_messages':label['source_messages']}
            for condition in ['G1','G2','G3','G4','D_no_path','D_task_roots_G2']:
                r=next(r for r in result['rows'] if r['point']==p['point'] and r['condition']==condition and r['budget']==4096)
                row[condition]=e['id'] in r['selected']
                if condition=='G2' and not row[condition]:
                    eid=next(k for k,v in p['event_map'].items() if v==e['id'])
                    proof=json.loads(gzip.decompress(Path(r['proof']['path']).read_bytes()))
                    row['G2_exclusion']=next((x['reason'] for x in proof['omitted_events'] if x['event']==eid),'not_in_ranked_path_candidates')
                    row['G2_focus']=proof['query']['roots']
            rows.append(row)
    target=BASE/'essential-case-audit-r1/rows.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print('essential events',len(rows),'G2 missing',sum(not r['G2'] for r in rows))
if __name__=='__main__':main()
