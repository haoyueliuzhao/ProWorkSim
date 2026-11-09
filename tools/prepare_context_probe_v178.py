import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_probe_v178 import clarify_cases,input_payload,RUN,ROOT


def main():
    out=ROOT/'artifacts/software-benchmark-v178/recovery-probe-design-r1'
    out.mkdir(parents=True,exist_ok=True);(RUN/'inputs').mkdir(parents=True,exist_ok=True)
    old_plan=ROOT/'runs/software-benchmark-v177/recovery-probe-r1/plan.json'
    original=json.loads(old_plan.read_bytes());cases=clarify_cases(original)
    authority={'standing_budget':original['authority'],'cumulative_cap_CNY':250,
        'scope':'One complete clarified12-case independent diagnostic retest after measurement defects; no best-of replacement',
        'old12_attempts_preserved':True,'no_new_full_task_episodes':True,
        'reason':['passed boolean versus test count question ambiguity','unnecessarily requiring whole message recovery',
                  'overlapping safe decision labels','null and unobserved record status ambiguity','unverified citation index0'],
        'schema_does_not_expose_unknown_answers':True}
    auth=write_new(out/'authority.json',authority)
    for c in cases:c['actual_initial_payload']=write_new(RUN/'inputs'/(c['case_id']+'.json'),input_payload(c))
    plan={**{k:v for k,v in original.items() if k not in ('cases','authority','version')},
        'version':'v178-clarified-real-model-recovery-r1','cases':cases,'authority':auth,
        'earlier_independent_probe_plan':reference(old_plan),'prior_results_used_to_design_retest':True,
        'independent_statistical_confirmation':False,'all12_retested_not_only_failed_cases':True}
    write_new(RUN/'plan.json',plan);write_new(out/'plan.json',plan)
    print(json.dumps({'cases':len(cases),'typed_fact_fields':sum(len(c['expected']['facts']) for c in cases),
        'original_spans_prepared':sum(len(c['fact_evidence_ranges']) for c in cases)}))


if __name__=='__main__':main()
