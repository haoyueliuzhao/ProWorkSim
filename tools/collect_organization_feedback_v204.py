"""Build paired utility evidence from closed healthy generation and exact grader receipts.
No data from old contaminated trials is eligible. Never consumes confirmation outcomes.
"""
import argparse,json
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.software_organization_cn_v204 import CANDIDATES
from proworksim.storage import json_bytes
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=json.loads(a.manifest.read_text())
if m['stage']!='development' or m['window'] not in (1,2):raise ValueError('Only fresh development data')
blocks=[]
for b in m['blocks']:
 if set(b['branches'])!=set(CANDIDATES):raise ValueError('Complete three-candidate block required')
 results={}
 for candidate,refs in b['branches'].items():
  gen=json.loads(checked(refs['generation']).read_text());folder=Path(refs['generation']['path']).parent
  if gen['status']!='closed' or not gen['slot'].startswith('v204:') or gen['arm']!=candidate:raise ValueError('Old/failed/misassigned trajectory')
  if (Path(m['ledger']).parent/'batch-pause.json').exists():raise ValueError('Systemically paused trajectory cannot update')
  boundary=json.loads((folder/'boundary.json').read_text());world=json.loads((folder/'final-world.json').read_text())
  # Any original engine or callback transport failure disqualifies, irrespective of outer closed label.
  if boundary['execution_integrity_failure'] is not None:raise ValueError('Integrity fault')
  for line in (folder/'runtime/experience.jsonl').open():
   if '"kind": "tool_call"' not in line and '"kind":"tool_call"' not in line:continue
   event=json.loads(line);error=event.get('payload',{}).get('response',{}).get('error',{})
   if error.get('type') in ('FatalTransport','ManagedTransferError'):raise ValueError('Contaminated public feedback')
  pair=read_episode_candidates(json.loads((folder/'candidate-lock.json').read_text()));legal=pair['last_legal_delivery'] is not None
  code=json.loads(checked(refs['code_score']).read_text())
  if code['status']!='official_report' or code['candidate_tree_sha256']!=json.loads(checked(pair['lock']['terminal_code']).read_text())['tree_sha256']:raise ValueError('Unknown or wrong code endpoint')
  if legal:
   score=json.loads(checked(refs['delivery_score']).read_text());target=json.loads(checked(pair['lock']['last_legal_delivery']).read_text())['tree_sha256']
   if score['status']!='official_report' or score['candidate_tree_sha256']!=target:raise ValueError('Exact submitted version must be scored')
  else:score=code
  used=boundary['team_budget']['model']['charged_tokens'] if 'charged_tokens' in boundary['team_budget']['model'] else sum(v['actual_tokens'] for v in boundary['team_budget']['model']['records'].values())
  results[candidate]={'environment_healthy':True,'official_code_pass':score['resolved'],'terminal_code_pass':code['resolved'],'legal_delivery':legal,
   'score_same_delivery_version':legal,'full_team_tokens':used,'generation_receipt':refs['generation'],'official_score_receipt':refs.get('delivery_score',refs['code_score']),
   'usage_receipt':reference(folder/'boundary.json')}
 blocks.append({'state_id':b['state_id'],'stage':'development','results':results})
with a.output.open('xb') as f:f.write(json_bytes({'evidence_kind':'actual_official_scored_healthy_blocks','window':m['window'],'blocks':blocks}))
