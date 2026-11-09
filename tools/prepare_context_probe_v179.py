import json
from pathlib import Path
from proworksim.software_context_probe_v179 import ROOT,RUN,input_payload
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def main():
    old=ROOT/'runs/software-benchmark-v178/recovery-probe-clarified-r1/plan.json';plan=json.loads(old.read_bytes())
    out=ROOT/'artifacts/software-benchmark-v179/recovery-probe-design-r1'
    out.mkdir(parents=True,exist_ok=True);(RUN/'inputs').mkdir(parents=True,exist_ok=True)
    auth={'standing_budget':plan['authority'],'cumulative_CNY':250,'old_attempts_preserved':True,
        'scope':'One complete12-case independent verification of corrected source labels and budgeted citation feedback',
        'new_full_task_runs':0,'candidate_or_score_selection':False}
    plan['authority']=write_new(out/'authority.json',auth)
    plan['version']='v179-source-reader-real-model-validation-r1'
    plan['previous_independent_probe']=reference(old)
    plan['reader_revision']='v179-source-labeled-recoverable-reader-r1'
    plan['format_feedback_reveals_expected_answers']=False
    for c in plan['cases']:c['actual_initial_payload']=write_new(RUN/'inputs'/(c['case_id']+'.json'),input_payload(c))
    write_new(RUN/'plan.json',plan);write_new(out/'plan.json',plan)
    print(json.dumps({'cases':len(plan['cases']),'same_expected_fact_and_decision_values_as_v178':True}))


if __name__=='__main__':main()
