"""Read-only real-trace audit. No rescoring, model calls or original mutations."""
import json,datetime
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_organization_world_v223_1 import World
from proworksim.software_project_relations_v223_1 import allowed_event
from proworksim.software_mapping_checkpoint_v224_1 import assess,test_cases
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v224-1/review-r1';RUN=R/'runs/software-benchmark-v224/development4-r1'
def main():
 O.mkdir(parents=True,exist_ok=False);rows=[]
 for i in range(4):
  p=RUN/f'task-{i:02d}/PREFIX';path=p/'final-world.json';world=World.__new__(World);world.state=json.loads(path.read_text());events=world.state['software_events'];visible=[v for e in events if (v:=allowed_event(world,e,'member_001')) is not None];state=json.loads((p/'decision-state.json').read_text());gate=assess(state,visible,terminal=bool(world.protocol()['terminal']))
  tests=[{'sequence':e['sequence'],'actor':e['actor_id'],'source_reference':e.get('source_reference'),'counts':e.get('public_execution',{}).get('execution',{}).get('counts'),'visible_to_001':any(v['sequence']==e['sequence'] for v in visible),'positive_cases':test_cases(e)['qualifying']} for e in events if e['kind']=='test']
  row={'index':i,'source':reference(path),'original_decision':reference(p/'decision-state.json'),'split_count':sum(e['kind'].endswith(':work_split') for e in events),'leaf_tasks':{k:{f:w.get(f) for f in ('owner','authors','children','scope')} for k,w in state['graph']['work'].items() if not w.get('children')},'tests':tests,'revised_gate_on_final_snapshot_only':gate,'not_a_retroactive_admission':True}
  rows.append(row)
 f=json.loads((RUN/'finished.json').read_text());out={'version':'v224.1-real-trace-audit-r1','rows':rows,'source_finished':reference(RUN/'finished.json'),'execution_closed':True,'scientific_comparison_achieved':False,'actual_policy_updates':f['policy_updates'],'actual_panels':f['completed_panels'],'API_calls':0,'old_records_modified':False,'cash':f['cash']}
 (O/'audit.json').write_bytes(json_bytes(out));print(json.dumps({'tasks':len(rows),'splits':[x['split_count'] for x in rows],'scientific_comparison_achieved':False,'API_calls':0}))
if __name__=='__main__':main()
