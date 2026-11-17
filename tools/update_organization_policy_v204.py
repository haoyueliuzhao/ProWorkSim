"""Version an update from audited complete real blocks, or deploy frozen q via a draw."""
import argparse,json,hashlib
from pathlib import Path
from proworksim.software_organization_cn_v204 import update,select,CANDIDATES
p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
e=json.loads(a.evidence.read_text());old=json.loads(a.previous.read_text()) if a.previous else None
if e.get('evidence_kind')!='actual_official_scored_healthy_blocks':raise ValueError('No synthetic or contaminated feedback may update deployment')
if e.get('window')!=(2 if old else 1):raise ValueError('Exactly two chronological fresh windows')
q=old['q_after'] if old else {z:1/3 for z in CANDIDATES};r={z:1/3 for z in CANDIDATES}
for b in e['blocks']:
 for result in b['results'].values():
  for key in ('generation_receipt','official_score_receipt','usage_receipt'):
   ref=result[key];raw=Path(ref['path']).read_bytes()
   if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Changed result source')
# Verify supplied scalar labels against their bound real receipts, not just hashes.
for b in e['blocks']:
 for result in b['results'].values():
  gen=json.loads(Path(result['generation_receipt']['path']).read_text())
  score=json.loads(Path(result['official_score_receipt']['path']).read_text())
  usage=json.loads(Path(result['usage_receipt']['path']).read_text())
  if gen['status']!='closed' or not gen['slot'].startswith('v204:') or score['status']!='official_report' or score['resolved']!=result['official_code_pass']:raise ValueError('Effect labels not bound to actual outcomes')
  if usage['team_budget']['model']['charged_tokens']!=result['full_team_tokens']:raise ValueError('Full usage differs')
value=update(q,r,e['blocks'],round_index=e['window'],previous_state_ids=old['all_seen_state_ids'] if old else ())
value['all_seen_state_ids']=(old['all_seen_state_ids'] if old else [])+value['fresh_state_ids'];value['actual_evidence_source']=str(a.evidence.resolve())
value['update_evidence_sha256']=hashlib.sha256(a.evidence.read_bytes()).hexdigest()
with a.output.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)
