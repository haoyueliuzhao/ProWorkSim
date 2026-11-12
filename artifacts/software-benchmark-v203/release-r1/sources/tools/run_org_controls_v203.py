"""Source-frozen O0-O4 structural diagnostics, no counterfactual task scoring."""
import collections,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inventory_multimember_v203 import ROOT,read,ref,save
from org_scenarios_v203 import cases
from proworksim.software_org_policy_v203 import propose
OUT=ROOT/'artifacts/software-benchmark-v203/policy-controls-r1'

def key(c):return (c['operation'],tuple(c['tasks']))
def main():
    frozen=cases();save(OUT/'frozen-cases.json',frozen)
    save(OUT/'protocol.json',{'cases':ref(OUT/'frozen-cases.json'),'sources':[ref(Path(__file__)),ref(ROOT/'tools/org_scenarios_v203.py'),ref(ROOT/'src/proworksim/software_org_policy_v203.py')],
        'conditions':{'O0':'static fixed two-member organization','O1':'one-time initial-topology handoff mapping; not full ToCoMAS','O2':'dynamic project signals, fixed organization','O3':'event counts then common legality checks','O4':'project structure, execution evidence, cost and stability checks'},
        'candidate_limit_per_case':4,'members':2,'operations':['Reassign','Split','Merge','AddHandoff','AddReviewer'],
        'independent_reference':False,'synthetic_development_only':True,'G2_independent_admission_requires_new_reference':True,
        'future_independent_G2_thresholds':{'mismatch_precision':0.9,'mismatch_recall':0.8,'intervention_precision':0.9,'intervention_recall':0.8},
        'G3_G4_control_threshold':'zero task-owner loss, permission escalation, artifact-provenance mutation or skipped transfer-evidence stages',
        'G5_effect_gate':'not assessed by authored controls; independent references and real task interventions required'})
    rows=[];summary={}
    for mode in ['O0','O1','O2','O3','O4']:
        tp=fp=fn=mtp=mfp=mfn=0;seconds=0;raw=valid=rejected=0
        for case in frozen:
            before=json.dumps(case,sort_keys=True);start=time.process_time();r=propose(case['state'],mode);seconds+=time.process_time()-start
            assert json.dumps(case,sort_keys=True)==before
            predicted={key(c) for c in r['candidates'] if c['validation']['valid']};expected={key(c) for c in case['expected_valid_interventions']}
            mismatch={m['kind'] for m in r['mismatches']};truth=set(case['expected_mismatch_types'])
            tp+=len(predicted&expected);fp+=len(predicted-expected);fn+=len(expected-predicted);mtp+=len(mismatch&truth);mfp+=len(mismatch-truth);mfn+=len(truth-mismatch)
            raw+=len(r['candidates']);valid+=len(predicted);rejected+=sum(not c['validation']['valid'] for c in r['candidates'])
            rows.append({'case':case['id'],'condition':mode,'result':r,'matches_authored_expected_interventions':predicted==expected})
        summary[mode]={'cases':len(frozen),'raw_candidates':raw,'legally_valid_candidates':valid,'guard_rejections':rejected,'true_positive':tp,'false_positive':fp,'false_negative':fn,
            'intervention_precision':tp/(tp+fp) if tp+fp else None,'intervention_recall':tp/(tp+fn) if tp+fn else None,
            'mismatch_precision':mtp/(mtp+mfp) if mtp+mfp else None,'mismatch_recall':mtp/(mtp+mfn) if mtp+mfn else None,
            'CPU_seconds':seconds,'world_actions':0,'real_org_churn':0,'real_dependency_satisfaction':None,'token_or_money_cost':None}
    save(OUT/'rows.json',rows);save(OUT/'summary.json',{'conditions':summary,'scientific_G2_or_G5_pass':False,'reason':'authored engineering cases; no independent semantic reference or real task intervention','new_model_API':0})
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
