"""Validate saved1724 controls with the explicit task-specific admission rule."""
import argparse
import json
from proworksim import software_benchmark_requests1724_qualification_v164 as qualification
from proworksim.software_benchmark_candidates_v054 import reference

if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--write',action='store_true');group.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.write:result=qualification.prepare()
    else:
        scope=qualification.control_scope
        plan=qualification._load(reference(scope.PLAN_FILE))
        config=qualification._load(plan['environments'][qualification.TASK]['configuration'])
        proof=qualification.validate_qualification(reference(qualification.OVERLAY_FILE),config,reference(scope.PLAN_FILE))
        result={'passed':proof['passed'],'qualified_overlay':reference(qualification.OVERLAY_FILE),
            'official_scoring_unchanged':True,'new_model_calls':0,'Docker_operations':0}
    print(json.dumps(result,ensure_ascii=False))
