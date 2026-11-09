"""Build P0 corpus from all5523 canonical physical requests; no new model call."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import json
import multiprocessing
import os
from pathlib import Path
import resource
import time

from proworksim import software_context_dataset_v175 as corpus
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.storage import atomic_write,json_bytes

ROOT=corpus.ROOT
OUT=ROOT/'artifacts/software-benchmark-v175/p0-corpus-r1'
RUN=ROOT/'runs/software-benchmark-v175/context-corpus-r1'


def main(workers):
    OUT.mkdir(parents=True,exist_ok=True);RUN.mkdir(parents=True,exist_ok=True)
    summary=json.loads((ROOT/'artifacts/software-benchmark-v174/final-report-r1/summary.json').read_bytes())
    evidence=json.loads((ROOT/'artifacts/software-benchmark-v174/final-report-r1/evidence-audit.json').read_bytes())
    rows={r['slot_id']:r for r in summary['rows']}
    db=corpus.open_dataset(RUN/'dataset.sqlite')
    for slot,row in rows.items():
        metadata={'instance_id':row['instance_id'],'group_id':row['group_id'],'repo':row['repo'],
            'slot_index':row['slot_index'],'analysis_labels_only':{'R_code':row['R_code'],'R_delivery':row['delivery']['R_delivery']},
            'historical_development_data':True,'outcomes_excluded_from_replay_payload':True,
            'observation_status':row['observation_status'],'observation_evidence':row['observation_evidence'],
            'communication_extraction':row['communication_extraction'],'boundary':row['boundary_evidence']}
        db.execute('INSERT OR IGNORE INTO episodes VALUES(?,?)',(slot,corpus.canonical(metadata)))
    db.commit()
    completed={r[0] for r in db.execute('SELECT request_id FROM requests')}
    jobs=[]
    for item in evidence['physical_capture_index']:
        if item['request_id'] in completed:continue
        receipt=corpus.load(item['receipt'])
        jobs.append({'request_id':item['request_id'],'slot_id':receipt['ledger_record']['slot_id'],'receipt':item['receipt']})
    began=time.time()
    with ProcessPoolExecutor(max_workers=workers,initializer=corpus.initialize,
            mp_context=multiprocessing.get_context('fork')) as pool:
        for i,value in enumerate(pool.map(corpus.process_request,jobs,chunksize=4)):
            corpus.retain_request(db,value)
            if (i+1)%50==0:
                progress={'completed_requests':len(completed)+i+1,'planned_requests':5523,
                    'elapsed_seconds':time.time()-began,'workers':workers,'model_calls':0,'unix':time.time()}
                atomic_write(OUT/'progress.json',json_bytes(progress));print(json.dumps(progress),flush=True)
    estimates=Counter();unknown=total=0;fractions=[];usage=Counter();purposes={};conditions={}
    for slot,raw in db.execute('SELECT slot_id,metadata FROM requests'):
        value=json.loads(raw);estimates.update(value['source_estimates']);unknown+=value['unknown_estimated_tokens']
        total+=value['estimated_fragment_total'];fractions.append(value['unknown_fraction']);usage.update({k:v for k,v in value['provider_usage'].items() if type(v) is int})
        group=rows[slot]['group_id'];conditions.setdefault(group,Counter()).update(value['source_estimates'])
        purposes.setdefault(value['purpose'],Counter()).update(value['source_estimates'])
    assert len(fractions)==5523
    counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('episodes','requests','units','exposures')}
    db.close()
    result={'version':corpus.VERSION,'counts':counts,'dataset':reference(RUN/'dataset.sqlite'),
        'source_estimates':dict(estimates),'source_estimates_by_condition':{k:dict(v) for k,v in conditions.items()},
        'source_estimates_by_purpose':{k:dict(v) for k,v in purposes.items()},
        'unknown_local_estimated_tokens':unknown,'estimated_fragment_total':total,
        'local_unknown_fraction':unknown/total,'local_unknown_p95':sorted(fractions)[int(.95*len(fractions))-1],
        'provider_usage':dict(usage),'provider_exact_source_attribution':False,
        'old_all_attempt_tokens':summary['all_actual_tokens'],'old_all_attempt_cash_upper_nanoyuan':summary['all_cash_upper_nanoyuan'],
        'model_calls':0,'new_grading_calls':0,'all_true_input_source_units_before_model_response':True,
        'future_outcomes_are_separate_analysis_labels':True,'unknown_behavioral_use_not_filled_with_zero':True,
        'source_manifest':reference(ROOT/'artifacts/software-benchmark-v174/final-report-r1/evidence-audit.json')}
    write_new(OUT/'summary.json',result);atomic_write(OUT/'progress.json',json_bytes({'phase':'complete',**counts,'model_calls':0}))
    print(json.dumps({k:v for k,v in result.items() if k not in {'source_estimates_by_condition','source_estimates_by_purpose'}},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    if not 1<=a.workers<=8:raise ValueError('Use at most8 bounded local workers')
    os.nice(10);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-8:])
    os.environ.update(OMP_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    main(a.workers)
