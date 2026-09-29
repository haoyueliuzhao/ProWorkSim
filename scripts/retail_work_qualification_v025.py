"""Read-only, itemized CPU route qualification for the A-only v25 study."""
import argparse
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v025 as world


def ref(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': digest(path.read_bytes())}


def selected_control(path):
    path = Path(path)
    row = read_json(path/'control.json')
    case = world.case_spec(row['case_id'])
    required = [t for t in row['token_lengths'] if t['action'] not in {'staff_wait', 'staff_done'}]
    return {'case_id': row['case_id'], 'task': row['task'], 'control': row['control'],
            'known': row['score']['eligible'], 'completed': row['score']['completed'], 'reward': row['score']['reward'],
            'role_decisions': row['program_decisions'], 'request_attempts': row['program_request_attempts'],
            'role_limits': case['role_decision_limits'], 'within_role_budgets': row['within_role_budgets'],
            'maximum_required_prompt_tokens': max(t['prompt_tokens'] for t in required),
            'required_actions_fit': all(t['fits_prompt_and_reserved_output'] and t['program_output_within_limit'] for t in required),
            'actual_context_refusals': row['context_rejected_requests'],
            'only_nonessential_stop_refused': all(t['action'] == 'staff_done' for t in row['context_rejected_requests']),
            'prepared_business_state_sha256': row['prepared_business_state_sha256'],
            'mapper': row['score']['mapper'], 'facts': row['score'].get('facts'),
            'control_reference': ref(path/'control.json'), 'episode_reference': row['episode_reference'],
            'passed': bool(row['score']['eligible'] and row['score']['completed'] and row['within_role_budgets']
                           and all(t['action'] == 'staff_done' for t in row['context_rejected_requests']))}


def report():
    manifest = read_json(world.PIN_PATH)
    root = Path('runs')
    controls = [selected_control(root/'retail-work-v025-initial'/('case-00-'+name)) for name in ('active_handoff','request_bound_handoff')]
    controls.append(selected_control(root/'retail-work-v025-compact-preparation/case-01-self_inspection_repair'))
    controls.extend(selected_control(root/'retail-work-v025-materials'/f'case-{i:02d}-complete') for i in range(2,16))
    feedback = selected_control(root/'retail-work-v025-feedback-alias/case-01-evidence_feedback_repair')
    attempts = []
    for folder in ('retail-work-v025-initial', 'retail-work-v025-feedback-short', 'retail-work-v025-feedback-direct', 'retail-work-v025-compact-preparation', 'retail-work-v025-feedback-alias'):
        path = root/folder/'case-01-evidence_feedback_repair/control.json'
        row = read_json(path)
        attempts.append({'path': ref(path), 'case_id': row['case_id'], 'eligible': row['score']['eligible'],
                         'completed': row['score']['completed'], 'reward': row['score']['reward'],
                         'exclusions': row['score']['exclusions'], 'context_refusals': row['context_rejected_requests'],
                         'role_stops': row['termination']['role_stops']})
    identities = {'A_two_methods_same_prepared_state': controls[0]['prepared_business_state_sha256'] == controls[1]['prepared_business_state_sha256'],
                  'B_two_attempts_same_final_prepared_state': controls[2]['prepared_business_state_sha256'] == feedback['prepared_business_state_sha256']}
    def prepared_table(folder):
        prefix=read_json(root/folder/'case-01-self_inspection_repair/preparation.json')
        return next(e['payload']['response']['result']['tables'] for e in prefix['experience']['events'] if e['kind']=='preparation_tool_call' and e['payload']['action']=='sql_build')
    equivalent = prepared_table('retail-work-v025-initial') == prepared_table('retail-work-v025-compact-preparation')
    result = {'version':'retail-work-qualification-v0.25', 'scope':'Actual CPU native-program/WorldCore/official-tokenizer route witnesses only; never current-policy trajectories, teacher labels, model support counts or parameter learning.',
              'model_calls':0,'gpu_calls':0,'api_cost_usd':0,'parameter_updates':0,
              'can_start_A_only_study':len(controls)==17 and all(c['passed'] and c['required_actions_fit'] for c in controls) and all(identities.values()) and equivalent,
              'all_required_routes_passed':False,'full_four_method_qualification':False,
              'pre_model_scope_decision':{'eligible_reconfiguration_blocks_in_order':['joint_a/implementer','joint_a/provider'],
                  'joint_b_members_forced_base_weights':True,'joint_b_real_training_slots':8,
                  'future_model_B_multimethod_observation_does_not_reopen_eligibility':True,
                  'reason':'A methods have complete route qualification. B evidence-feedback repair does not fit the witnessed frozen presentation path; B remains actual base RL with honest validity/method diagnostics. No model outcome used for this narrowing.'},
              'source_pin':ref(world.PIN_PATH),'catalog':ref(world.PIN_PATH.parent/'catalog.json'),
              'source':{'materials':len(manifest['slices']),'customers':sum(len(x['customers']) for x in manifest['slices']),
                        'complete_invoices':sum(len(x['invoice_ids']) for x in manifest['slices']), 'original_rows':sum(x['rows'] for x in manifest['slices']),
                        'excluded_customers':len(manifest['excluded_customers']),'excluded_invoices':len(manifest['excluded_invoices']),
                        'excluded_source_rows':len(manifest['excluded_source_rows']),'source_families':1,'maximum_invoice_rows':3},
              'qualified_controls':controls,'qualified_program_paths':17,'unique_materials_with_at_least_one_qualified_route':16,
              'B_feedback_final_attempt':feedback,'B_feedback_development_attempts':attempts,'same_initial_state_checks':identities,
              'training_B_preparation_variant':{'case_id':world.registry()['training_cases'][1]['case_id'],'variant':'compact-sql-v025-r1',
                  'old_json_bytes':1160,'new_json_bytes':847,'old_standalone_official_tokenizer_tokens':335,'new_standalone_official_tokenizer_tokens':259,
                  'token_scope':'Standalone serialized prepared code JSON, not whole model prompt.',
                  'identical_actual_initial_wrong_result_table':equivalent,'business_test_preserved':'unique_customer',
                  'business_defect_preserved':'COUNT(DISTINCT InvoiceNo)+1; actual initial products match exactly, self-repair reaches original complete assessment.',
                  'changes':'Shorter equivalent SQL and removal of nonbusiness config description; no reward, public review contract, permissions, scheduling, budget or harness change.'},
              'maximum_qualified_required_prompt_tokens':max(c['maximum_required_prompt_tokens'] for c in controls),
              'qualified_post_completion_stop_context_refusals':sum(len(c['actual_context_refusals']) for c in controls),
              'context_capacity':16384,'reserved_output_tokens':2048,
              'limitations':['No complete program witness for B feedback route; not a proof that all possible model/program routes are impossible.',
                  'All16 materials remain one UCI family; source/entity disjointness is not independent-source generalization.',
                  'CPU witness can choose a valid route from actual public evidence but does not establish its frequency under the target model.',
                  'Known fixture transport failures following earlier context stops and the discarded USING syntax failure remain development failures.']}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    result = report()
    atomic_write(Path(args.output), json_bytes(result))
    print({key:result[key] for key in ('can_start_A_only_study','all_required_routes_passed','qualified_program_paths','maximum_qualified_required_prompt_tokens','qualified_post_completion_stop_context_refusals')})
    raise SystemExit(0 if result['can_start_A_only_study'] else 1)
