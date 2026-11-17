"""Passive five-stage audit and SymPy case evidence; no live policy changes."""
from pathlib import Path
import json
from proworksim.software_organization_design_v210 import action_chain
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v210/offline-audit-r1'
rows=json.loads((R/'artifacts/software-benchmark-v209/final-report-r1/episodes.json').read_text());out=[];sympy=[]
for x in rows:
 p=Path(x['episode_dir']);world=json.loads((p/'final-world.json').read_text());result=json.loads((p/'result.json').read_text());prefix=Path(result['checkpoint_parent']).parent;pw=json.loads((prefix/'final-world.json').read_text());start=max(e['sequence'] for e in pw['software_events'])
 candidate=x['lifecycle']['candidate'];chain=action_chain(candidate,world['software_events'],presented=x['intervention_in_first_request'],after_sequence=start)
 out.append({'slot':x['slot'],'instance_id':x['instance_id'],'stage':x['stage'],'condition':x['condition'],'chain':chain,'code':x['code'],'delivery':x['delivery'],'source_world':str(p/'final-world.json'),'scope':'world event provenance; no inferred diagnosis truth'})
 if x['instance_id']=='sympy__sympy-14531':
  sympy.append({'condition':x['condition'],'code':x['code'],'delivery':x['delivery'],'tokens':x['logical_usage_including_prefix']['total_tokens'],'prefix_world':str(prefix/'final-world.json'),'prefix_events':pw['software_events'],'timeline':[e for e in world['software_events'] if e['sequence']>start and e['kind'] in ('work_message','transfer_offered','transfer_accepted','task_returned','claim','test','patch_fixed','organization_v141:candidate_reviewed','submit')],'discovery_novelty_not_inferred':True})
(O/'action-chains.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(O/'sympy-case.json').write_text(json.dumps(sympy,ensure_ascii=False,indent=2)+'\n')
print([{'stage':x['stage'],'condition':x['condition'],'initiated':bool(x['chain']['committed_initiation']),'changed':x['chain']['organization_changed'],'strict_return':bool(x['chain']['legal_return_offer_accept'])} for x in out])
