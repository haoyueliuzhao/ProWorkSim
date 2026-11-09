"""Reconcile all three independent probe revisions without best-of selection."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sqlite3

from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v179/recovery-results-r1'
DIRS={'v177':'recovery-probe-r1','v178':'recovery-probe-clarified-r1','v179':'recovery-reader-validation-r1'}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    ledger=ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;requests=[dict(r) for r in db.execute('SELECT * FROM requests')]
    groups={};all_rows=[];models=Counter();fingerprints=Counter()
    for version,directory in DIRS.items():
        run=ROOT/'runs'/('software-benchmark-'+version)/directory
        summary=json.loads((run/'summary.json').read_bytes());plan=json.loads((run/'plan.json').read_bytes())
        local=[r for r in requests if r['job_id'].startswith(version+':')]
        if any(r['status']!='settled' for r in local):raise ValueError('Keep unresolved charges visible')
        spec=importlib.util.spec_from_file_location('parse_'+version,ROOT/'tools'/('run_context_probe_'+version+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        usage=Counter();format_repairs=0;settled_by_case=Counter();tokens_by_case=Counter();cost_by_case=Counter()
        for r in local:
            u=json.loads(r['usage']);usage.update(u);cid=r['job_id'].split(':')[1]
            settled_by_case[cid]+=1;tokens_by_case[cid]+=u['total_tokens'];cost_by_case[cid]+=r['cost']
            response=json.loads(checked(json.loads(r['response_ref'])).read_bytes())
            models[response.get('model')]+=1;fingerprints[response.get('system_fingerprint')]+=1
            msg=response['choices'][0]['message']
            if not msg.get('tool_calls'):
                try:module.parse_answer(msg.get('content'))
                except (ValueError,TypeError):format_repairs+=1
        rows=[]
        for result in summary['rows']:
            case=next(c for c in plan['cases'] if c['case_id']==result['case_id']);a=result.get('assessment',{})
            row={'version':version,'case_id':result['case_id'],'kind':result['kind'],'status':result['status'],
                'passed':a.get('passed',False),'facts_correct':a.get('facts_correct',False),
                'facts_requested':len(case['expected']['facts']),
                'exact_fact_errors':a.get('fact_error_keys',[]),'assessment':a,
                'reads':len(result['reads']),'physical_requests':settled_by_case[result['case_id']],
                'actual_tokens':tokens_by_case[result['case_id']],'cost_nanoyuan':cost_by_case[result['case_id']],
                'citation_format_repairs':len(result.get('format_feedback',[])),
                'answer':result.get('answer'),'source':reference(run/'cases'/result['case_id']/'result.json')}
            rows.append(row);all_rows.append(row)
        sources=json.loads((run/'sources.json').read_bytes())
        for ref in sources['files']:checked(ref)
        groups[version]={'planned_cases':12,'closed_cases':sum(r['status']=='closed' for r in rows),
            'raw_gate_passed':summary['gate_passed'],'raw_all_criteria_passes':sum(r['passed'] for r in rows),
            'fact_fields_requested':sum(r['facts_requested'] for r in rows),
            'exact_fact_errors':sum(len(r['exact_fact_errors']) for r in rows),
            'physical_requests':len(local),'actual_input_tokens':usage['input_tokens'],
            'actual_output_tokens':usage['output_tokens'],'actual_total_tokens':usage['total_tokens'],
            'cached_input_tokens':usage['cached_input_tokens'],'uncached_input_tokens':usage['cache_miss_input_tokens'],
            'cost_nanoyuan':sum(r['cost'] for r in local),'peak_tariff_CNY':sum(r['cost'] for r in local)/1e9,
            'actual_context_reads':sum(r['reads'] for r in rows),'JSON_format_repair_responses':format_repairs,
            'citation_format_repairs':sum(r['citation_format_repairs'] for r in rows),
            'wall_seconds':summary['wall_seconds'],'frozen_sources_unchanged':True,
            'raw_summary':reference(run/'summary.json')}
    new=sum(g['cost_nanoyuan'] for g in groups.values());total=sum(r['cost'] for r in requests if r['status']=='settled')
    latest=[r for r in all_rows if r['version']=='v179']
    result={'version':'v179-recovery-three-revision-report-r1','groups':groups,'rows':all_rows,
        'latest_gate_passed':groups['v179']['raw_gate_passed'],'best_of_across_revisions_used':False,
        'v177_has_documented_measurement_defects':True,'latest_functional_criterion':'42 exact facts plus necessary actual reads/citations and24 boolean decisions',
        'independent_heldout_confirmation_claimed':False,'autonomous_full_task_recovery_claimed':False,
        'new_API_cost_CNY':new/1e9,'new_actual_tokens':sum(g['actual_total_tokens'] for g in groups.values()),
        'cumulative_cost_CNY':total/1e9,'remaining_CNY':(250_000_000_000-total)/1e9,
        'unknown_or_reserved_requests':sum(r['status']!='settled' for r in requests),
        'actual_models':dict(models),'actual_fingerprints':dict(fingerprints),'new_world_actions':0,
        'deep_read_case':next(r for r in latest if r['case_id']=='r08'),
        'all_prior_request_rows_retained':True,'model_parameter_training':False}
    write_new(OUT/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','deep_read_case')},ensure_ascii=False))


if __name__=='__main__':main()
