"""Freeze48 outcome-blind historical decisions and one common recall interface."""
import json
from pathlib import Path
import sqlite3

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_compression_v175 import VERSION,METHODS

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'
ART=ROOT/'artifacts/software-benchmark-v175/replay-plan-r1'


def main():
    RUN.mkdir(parents=True,exist_ok=True);ART.mkdir(parents=True,exist_ok=True)
    corpus=ROOT/'runs/software-benchmark-v175/context-corpus-r1/dataset.sqlite'
    summary=json.loads((ROOT/'artifacts/software-benchmark-v174/final-report-r1/summary.json').read_bytes())
    rows=[]
    with sqlite3.connect(corpus.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for episode in sorted((r for r in summary['rows'] if r['group_id']=='C0'),key=lambda r:r['instance_id']):
            raw=[json.loads(x[0]) for x in db.execute('SELECT metadata FROM requests WHERE slot_id=? AND member_id=? AND purpose=? ORDER BY request_time,request_id',
                (episode['slot_id'],'member_001','agent'))]
            eligible=[r for r in raw if r['provider_usage']['input_tokens']<=96000]
            if len(eligible)<3:raise ValueError('A task cannot supply two predeclared historical decisions')
            positions=[len(eligible)//3,2*len(eligible)//3]
            for stage,pos in enumerate(positions,1):
                r=eligible[pos];point_id=f'p{len(rows):03d}'
                rows.append({'point_id':point_id,'instance_id':episode['instance_id'],'repo':episode['repo'],
                    'slot_id':episode['slot_id'],'member_id':'member_001','historical_condition':'C0',
                    'partition':'development' if episode['wave']==1 else 'holdout_history',
                    'stage':stage,'selection_quantile':stage/3,'source_request_id':r['request_id'],
                    'source_capture':r['capture'],'source_receipt':r['physical_receipt'],
                    'actual_original_input_tokens':r['provider_usage']['input_tokens'],
                    'source_response_used_to_select_point':False,'historical_gold_score_used_as_input':False})
    assert len(rows)==48 and len({r['instance_id'] for r in rows})==24
    proposal={'version':VERSION,'name':'Communication Optimization V2 P0 and P1 historical replay',
        'rows':rows,'methods':list(METHODS),'development_points':24,'holdout_history_points':24,
        'core_replay_decisions':192,'maximum_additional_M3_guideline_validation_decisions':24,
        'maximum_history_summary_calls':72,'maximum_guideline_calls':2,
        'maximum_context_reads_per_decision':2,'maximum_physical_attempts_per_logical_request':3,
        'max_API_concurrency':32,'new_API_start_budget_CNY':'250',
        'cash_policy':'admit_complete_bounded_job_then_finish_without_cash_interruption',
        'max_job_tokens':5_000_000,'model':'deepseek-flash','thinking':False,
        'temperature':1,'top_p':1,'input_limit':98304,'output_limit':32768,
        'source_corpus':reference(corpus),'user_authority':reference(ROOT/'artifacts/software-benchmark-v175/user-amendment-r1/authorization.json'),
        'common_context_read_tool':True,'new_world_actions_executed':False,
        'single_agent_full_task_score_claimed':False,'original_raw_agent_replication_claimed':False,
        'M0_semantics':'Unmodified captured request history, including any already-existing summary, plus common private recall tool',
        'M2_semantics':'Official frozen LLMLingua-2 preservation probabilities rank complete old tool observations; no code/diff token deletion',
        'M3_semantics':'Mask old observations first; summarize closed history only above32768 local tokens; at most one development-only guideline revision',
        'holdout_is_independent_benchmark':False,'new_multiagent_benchmark_episodes':0,
        'source_labels_and_final_outcomes_never_sent_to_model':True}
    ref=write_new(RUN/'plan.json',proposal);write_new(ART/'proposal.json',proposal)
    print(json.dumps({'plan':ref,'points':48,'core_API_decisions':192,'new_cash_budget_CNY':250}))


if __name__=='__main__':main()
