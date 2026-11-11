import json,gzip,sys
from pathlib import Path
BASE=Path('/data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v197/blind-material-r1')
OUT=Path(__file__).parent

def show(point):
 b=json.loads((BASE/point/'brief.json').read_text())
 n=int(point[1:]);old={}
 if n>1:
  prev=json.loads((BASE/f'P{n-1:03}'/'brief.json').read_text())
  if prev['issue']==b['issue']:old={tuple(e['source_message_indices']):e for e in prev['historical_candidates']}
 print('POINT',point,'ISSUE',b['issue'] if not old else b['issue'].split('\n')[0], 'VERSION',b['current_version'])
 for e in b['historical_candidates']:
  if tuple(e['source_message_indices']) in old:print('OLD',e['id'],e['kind'],e['source_message_indices'],e['version_status'])
  else: print('CANDIDATE',json.dumps(e,ensure_ascii=False))
 for item in b['common_recent_window']:
  n=item['message_index'];m=item['message']
  if 'observation_state' in m:
   if item==b['common_recent_window'][-1]:
    s=m['observation_state'];print('STATE',n,json.dumps({k:s.get(k) for k in ['workspace_reference','current_version_test_coverage','delivery_status']},ensure_ascii=False))
  elif m['role']=='tool':
   try:r=json.loads(m['content'])
   except Exception:print('MSG',n,m);continue
   if not r.get('ok'):print('ERROR',n,r);continue
   r=r.get('result',r)
   if isinstance(r,dict) and 'report_id' in r:
    print('TEST',n,json.dumps({k:r.get(k) for k in ['report_id','source_reference','executed','passed','validation_status','counts']},ensure_ascii=False));print('PAGE',r.get('page',{}).get('text',''))
   elif isinstance(r,dict) and 'text' in r: print('SOURCE',n,r.get('path','diff'),r.get('source_reference'),r['text'])
   else:print('MSG',n,json.dumps(r,ensure_ascii=False))
  else: print('ACTION',n,json.dumps(m,ensure_ascii=False))

def save(d):
 assert d['point'] in [f'P{i:03}' for i in range(1,49)]
 d={'reviewer':'A','review_type':'AI_blind','must_keep_failure_events':[],'missing_evidence':[],'coverage':{'cross_file':False,'failure_and_change':False,'version_change':False},'confidence':'high',**d}
 b=json.loads((BASE/d['point']/'brief.json').read_text())
 events={e['id']:e for e in b['historical_candidates']}
 d['labels']=[{'event':x[0],'label':x[1],'reason':x[2],'source_messages':x[3] if len(x)>3 else events[x[0]]['source_message_indices']} if isinstance(x,list) else x for x in d['labels']]
 assert {x['event'] for x in d['labels']}==set(events)
 with (OUT/(d['point']+'.json')).open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
 print('SEALED',d['point'])
if __name__=='__main__':
 if sys.argv[1]=='show':show(sys.argv[2])
 elif sys.argv[1]=='save':save(json.load(sys.stdin))
