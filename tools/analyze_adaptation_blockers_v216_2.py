"""Read only saved public observations and receipts; no API or scorer access."""
import json,collections
from pathlib import Path
from proworksim.software_organization_world_v216_2 import compact_observation
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v216/target-repair6-r1';out=R/'artifacts/software-benchmark-v216/targeted-closure-r1/blockers.json'
rows=[]
for ep in sorted(root.glob('r2-task-*/*')):
 if ep.name not in ('KEEP','ADAPT'):continue
 calls=[];obs=[]
 for p in sorted((ep/'runtime/public-capture').glob('*.jsonl')):
  for line in p.open():
   d=json.loads(line)
   if d['kind']=='tool_call':calls.append({'actor':p.stem,**d['payload']})
   elif d['kind']=='public_observation':obs.append(d['payload'])
 rejected=[{'actor':c['actor'],'tool':c['action'],'arguments':c['arguments'],'error':c['response']['error']} for c in calls if c['response'].get('ok')is False]
 drift=[{'actor':c['actor'],'tool':c['action'],'arguments':c['arguments'],'receipt':c['response']['result']} for c in calls if ep.name=='KEEP' and c['action'] in ('offer_joint_arrangement','accept_joint_arrangement','assign_work','accept_transfer','change_dependency') and c['response'].get('ok')is True]
 compact=[compact_observation(o) for o in obs]
 size=lambda xs:sum(len(json.dumps(x,ensure_ascii=False).encode()) for x in xs)
 costs=json.loads((ep/'cost-endpoints.json').read_text());d=json.loads((ep/'dynamic-final.json').read_text())
 rows.append({'task':ep.parent.name,'condition':ep.name,'logical_tokens':costs['logical_total_tokens'],'tool_calls':len(calls),'rejections':rejected,'KEEP_successful_structural_changes':drift,'delivery_gaps':d['delivery_gaps']['packages'],'observations':len(obs),'original_default_bytes':size(obs),'deduplicated_default_bytes':size(compact),'measurement':'Payload UTF-8 bytes only, NOT provider tokens, not future end-to-end savings'})
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'version':'v216.2-readonly-blocker-audit','rows':rows},ensure_ascii=False,indent=2)+'\n')
for r in rows:print(r['task'],r['condition'],'logical_tokens',r['logical_tokens'],'rejections',len(r['rejections']),'KEEP_changes',len(r['KEEP_successful_structural_changes']),'observation_bytes_reduction',round(1-r['deduplicated_default_bytes']/r['original_default_bytes'],3))
