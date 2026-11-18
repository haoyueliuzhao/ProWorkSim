"""Read-only operation-boundary responsibility and review-evidence audit."""
import json,collections
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v211/final-report-r1';rows=json.loads((O/'episodes.json').read_text());out=[]
for row in rows:
 p=Path(row['source']['path']).parent;w=json.loads((p/'final-world.json').read_text());events=w['software_events'];dy=json.loads((p/'dynamic-final.json').read_text());plan=json.loads((p/'organization-plan.json').read_text())['candidate']['target']
 # First two events are zero-model common create/claim before exposure. Internal
 # create+claim events in split are one transaction; audit the final snapshot.
 final_by_op={e['operation_id']:e for e in events if e['sequence']>2}
 owner_gaps=[{'sequence':e['sequence'],'operation_id':e['operation_id'],'snapshot':e['responsibility_snapshot']} for e in final_by_op.values() if any(owner not in ('member_001','member_002') for owner in e['responsibility_snapshot'].values())]
 bad_authors=[e for e in events if e['kind']=='organization_v211:work_performed' and e['responsibility_snapshot'].get(e['task_id'])!=e['actor_id']]
 refs={e['sequence']:e for e in events};reviews=[]
 for e in events:
  if e['kind']!='organization_v141:candidate_reviewed' or e['decision']!='accept':continue
  test=e['test_evidence'];actual=refs[test['sequence']]
  exact=(test['actor_id']==e['actor_id'] and e['actor_id']!=e['author'] and actual['kind']=='test' and actual['executed'] is True and actual['source_reference']==e['adopted_source_reference'] and all(actual[k]==e['identity'][k] for k in ('files_sha256','entry_metadata_sha256')))
  reviews.append({'sequence':e['sequence'],'exact_adopted_version_executed':exact,'public_test_passed':test['passed'],'public_test_validation_status':test.get('validation_status'),'review_is_not_test_pass':True})
 leaves={k:v for k,v in dy['work'].items() if not v['children']}
 expected_edges=sorted(tuple(e) for e in plan['dependencies']);actual_edges=sorted((k,parent) for k,v in leaves.items() for parent in v['depends_on'])
 expected_collab={(k,a,b) for k in leaves for a,b in [('member_001','member_002'),('member_002','member_001')]};actual_collab={tuple(e) for e in dy['collaboration'] if e[0] in leaves}
 out.append({'index':row['index'],'condition':row['condition'],'checked_eventful_operation_boundaries':len(final_by_op),'initial_create_claim_excluded_preexposure':True,'owner_gaps':owner_gaps,'work_by_nonowner':bad_authors,'accepted_reviews':reviews,'dependency_target_match':expected_edges==actual_edges,'expected_dependencies':expected_edges,'actual_dependencies':actual_edges,'all_leaf_collaboration_edges_present':expected_collab<=actual_collab,'full_target_scope_owner_reviewer_dependency_collaboration_match':row['target_scope_owner_reviewer_exact'] and expected_edges==actual_edges and expected_collab<=actual_collab})
summary={'rows':out,'eventful_boundaries_checked':sum(x['checked_eventful_operation_boundaries'] for x in out),'runs_with_owner_gaps':sum(bool(x['owner_gaps']) for x in out),'runs_with_nonowner_code_work':sum(bool(x['work_by_nonowner']) for x in out),'accepted_reviews':sum(len(x['accepted_reviews']) for x in out),'accepted_reviews_with_failed_public_test':sum(y['public_test_passed'] is False for x in out for y in x['accepted_reviews']),'all_accepted_reviews_exact_execution_evidence':all(y['exact_adopted_version_executed'] for x in out for y in x['accepted_reviews']),'boundary_scope':'Event-bearing committed operations after common preparation; does not claim semantic requirement satisfaction or arbitrary hidden actions'}
(O/'invariant-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False,indent=2))
