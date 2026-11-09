"""Freeze12 actual recovery cases; retain previous costs in the same250CNY ledger."""
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_probe_v177 import build_cases,input_payload,RUN,OLD,VERSION

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v177/recovery-probe-design-r1'


def retain(path,value):
    if path.exists():
        if json.loads(path.read_bytes())!=value:raise ValueError('A prepared object changed')
        return reference(path)
    return write_new(path,value)


def main():
    RUN.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    (RUN/'inputs').mkdir(exist_ok=True)
    source=ROOT/'artifacts/software-benchmark-v176/summary-recovery-controls-r2/summary.json'
    cases=build_cases(json.loads(source.read_bytes()))
    authority={'user_request':'参照审计修订并开展后续实验','budget_reply':'沿用旧账本，累计上限仍250元',
        'cumulative_CNY':250,'old_ledger':str(OLD/'api-ledger.sqlite'),'prior_known_upper_CNY':21.065782,
        'old_requests_and_metadata_preserved':True,'cash_gate':'new_work_only_started_work_finishes',
        'scope':'12 read-only recovery probes plus preparation of four-arm full-task protocol',
        'input_audit':reference('/home/zhuxinrui/.codex/attachments/eb72535b-29c4-499f-9228-340bced0824c/已粘贴的文本.txt'),
        'new_shared_host_configuration':False,'training':False}
    authorization=retain(OUT/'authority.json',authority)
    for case in cases:
        case['actual_initial_payload']=retain(RUN/'inputs'/(case['case_id']+'.json'),input_payload(case))
    plan={'version':VERSION,'cases':cases,'case_count':12,'maximum_concurrency':12,
        'max_agent_decisions_per_case':9,'max_context_reads_per_case':8,'max_physical_attempts_per_logical':3,
        'model':'deepseek-flash','thinking':False,'input_limit':98304,'output_limit':4096,
        'maximum_whole_case_CNY_reservation':7,'maximum_physical_requests':324,
        'source_material':reference(source),'authority':authorization,
        'same_ledger_cumulative_cap_CNY':250,'new_full_task_episodes_started':0,
        'expected_outcomes_are_not_in_model_payload':True,'original_world_tools_execute':False,
        'gate_requires_all12':True,'unknown_negative_controls':2,
        'case_selection':'Predeclared semantic/structural coverage of retained G0 archives; no new model outcomes used',
        'expected_unknown_does_not_count_as_a_technical_fault':True}
    retain(RUN/'plan.json',plan);retain(OUT/'plan.json',plan)
    print(json.dumps({'cases':12,'case_types':[c['kind'] for c in cases],
        'deep_seek_original_page':cases[8]['required_original_ranges'][0]['start']//8192+1,'authority':authorization}))


if __name__=='__main__':main()
