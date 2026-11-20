"""Zero-API, actor-private historical replay. No invented Agent-maintained arm."""
import json,copy
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_project_relations_v217 import Projection,identity
from proworksim.software_organization_demand_v223 import inspect_state
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v223/historical-replay-r1'
SOURCES=['v216/mechanism6-r1/task-00','v217/confirmation-resume-r1/task-24','v222/paired4-r1/task-00']
def main():
 OUT.mkdir(parents=True,exist_ok=False);rows=[]
 for source in SOURCES:
  folder=R/('runs/software-benchmark-'+source)/'PREFIX';path=folder/'final-world.json';state=json.loads((folder/'decision-state.json').read_text());world=json.loads(path.read_text())
  events=[e for e in world['software_events'] if e['actor_id']=='member_001'];del world
  p=Projection();frozen=None;changed=0;last=None;claims=0;checks=[]
  for i,e in enumerate(events):
   p.apply(e);current=p.snapshot({},[]);rebuilt=Projection()
   for earlier in events[:i+1]:rebuilt.apply(earlier)
   assert current==rebuilt.snapshot({},[])
   p.apply(e);assert current==p.snapshot({},[])
   # Fixed initial event snapshot, not hindsight work-state reconstruction.
   if frozen is None and current['relations']:frozen=copy.deepcopy(current)
   if last!=current['graph_id']:changed+=1
   last=current['graph_id'];checks.append({'sequence':e['sequence'],'hash':last,'relations':len(current['relations'])})
  final=p.snapshot({},[]);frozen=frozen or final
  row={'source':source,'world_reference':reference(path),'decision_reference':reference(folder/'decision-state.json'),'events':len(events),'all_incremental_equal_full_replay':True,'duplicate_event_idempotence':True,'state_changes':changed,'static_relations':len(frozen['relations']),'event_driven_relations':len(final['relations']),'static_missing_final_ids':len({r['id'] for r in final['relations']}-{r['id'] for r in frozen['relations']}),'historical_test_relations':sum(r['kind']=='test_version' and r['validity']=='historical_version' for r in final['relations']),'member_claims_stay_unverified':sum(r['fact_status']=='member_claim' for r in final['relations']),'final_state_assessment':inspect_state(state),'no_retroactive_demand_times_assigned':True,'privacy_scope':'member_001 own events only; peer-private or visibility-ambiguous records excluded','Agent_maintained':{'status':'not_run_offline','reason':'No historical Graph Agent output exists; new interpretations require the separately budgeted v223 call'},'semantic_precision_recall':'unknown_no_independent_gold'}
  name=source.split('/')[0];(OUT/(name+'-event-checks.json')).write_bytes(json_bytes(checks));rows.append(row)
 (OUT/'summary.json').write_bytes(json_bytes({'passed':True,'model_calls':0,'world_mutations':0,'rows':rows,'claim':'state reconstruction and idempotence only, not mismatch accuracy or online benefit'}));print(json.dumps([{k:r[k] for k in ('source','events','static_relations','event_driven_relations','historical_test_relations')} for r in rows]))
if __name__=='__main__':main()
