"""Read-only view that keeps supplementary grading distinct from failed runs."""
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('original_role_snapshot',ROOT/'tools/summarize_role_context_pilot_v203_2_3.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def snapshot():
    original=old.snapshot();folder=ROOT/'artifacts/software-benchmark-v203-2-3/terminal-repair-r5'
    path=folder/'progress.json';supp=json.loads(path.read_text()) if path.exists() else {}
    groups={g:{'planned_tasks':4,'supplemental_scored':0,'supplemental_passed':0,'supplemental_unknown':0} for g in ('K0','K1','K2')}
    for r in supp.get('records',[]):
        g=groups[r['slot_id'].split(':')[2]]
        if r['status']=='scored':g['supplemental_scored']+=1;g['supplemental_passed']+=r['resolved'] is True
        else:g['supplemental_unknown']+=1
    return {'original_generation_phase':(original.get('progress') or {}).get('phase'),
        'original_generation_statuses':(original.get('progress') or {}).get('prepared_statuses'),
        'supplemental_phase':supp.get('phase','not_started'),'supplemental_planned':11,
        'supplemental_finished':len(supp.get('records',[])),'groups':groups,
        'cumulative_API_cost_upper_CNY':original['cumulative_cost_upper_CNY'],
        'cumulative_API_cap_CNY':130,'new_model_calls_allowed':False,
        'remaining_task_not_started':'pallets__flask-5014 / K1',
        'normal_context_effect_comparison_valid':False,'supplemental_records':supp.get('records',[])}

if __name__=='__main__':print(json.dumps(snapshot(),ensure_ascii=False,indent=2))
