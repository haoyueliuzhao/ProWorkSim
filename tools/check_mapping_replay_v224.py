"""Check actual saved zero/positive public test states; no API or new execution."""
import json
from pathlib import Path
from proworksim.software_mapping_gate_v224 import assess
from proworksim.software_project_relations_v223_1 import allowed_event
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];A=R/'artifacts/software-benchmark-v224/preparation-r1'
rows=[]
for i,expected in ((2,True),(3,False)):
 folder=R/f'runs/software-benchmark-v223-1/paired4-r1/task-{i:02d}/PREFIX';s=json.loads((folder/'decision-state.json').read_text());path=folder/'final-world.json';world=json.loads(path.read_text());events=[e for e in world['software_events'] if e['actor_id']=='member_001'];result=assess(s,events);assert result['eligible'] is expected
 rows.append({'source':reference(path),'decision':reference(folder/'decision-state.json'),'expected_eligible':expected,'actual':result,'only_own_events_used':True})
(A/'gate-replay.json').write_bytes(json_bytes({'passed':True,'rows':rows,'API_calls':0,'repository_tests':0,'old_records_modified':False}));print(json.dumps({'passed':True,'real_positive_case_state':True,'old_zero_collected_state_rejected':True}))
