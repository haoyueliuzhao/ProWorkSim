"""Finite development collaboration contracts, real prepared work, fixed history.

The six E cases are predeclared. CPU quality crosses are separate controls, not
extra E samples. No policy training projection or source independence is claimed.
"""
import copy
from pathlib import Path

from ..domains.work_product import evaluate_submission
from ..episode import assess_historical_episode
from ..online_rewards import _ref
from ..retail_rewards import RetailEvidence
from ..storage import digest, json_bytes, read_json
from . import retail_balanced, retail_work
from .online_work import PreparedOnlineCase

VERSION = 'retail-collaboration-v0.21'
REWARD_VERSION = 'retail-collaboration-outcomes-v0.21'
MAPPER_VERSION = 'retail-collaboration-observed-path-v0.21'
WORK = 'TEAM::build'
TERMS = {
    'implement': [('current_correct_build', .4), ('current_correct_fixed_delivery', .6)],
    'review': [('independent_review_evidence', .25), ('correct_fixed_review_judgment', .75)],
    'joint_a': [('applicable_basis_delivered', .2), ('delivered_basis_used_in_build', .3), ('correct_fixed_delivery', .5)],
    'joint_b': [('independent_final_review', .4), ('correct_fixed_final_product', .3), ('valid_review_and_repair_path', .3)],
}
PUBLIC = {
    'implement': 'Read and adopt exact data and applicable policy, execute real SQL, and fix independently correct code/result in a new submission. Prepared reads and deliveries are not your actions.',
    'review': 'Independently inspect the original fixed submission, its exact code/result, actual data and applicable audit facts. Approve correct work or raise a blocking issue at a real wrong row/cell with exact data/audit evidence. The submission may already be correct.',
    'joint_a': 'Provider reads an applicable private business basis and legally delivers its exact version through the declared route. The implementer obtains and adopts that delivered version with actual data, uses it in a correct real build and fixes the code/result in a new submission. A message without consumption is insufficient. Proactive delivery and a recipient request are both legitimate.',
    'joint_b': 'A real fixed submission is already pending. The implementer may inspect it and repair a real defect independently or respond to an evidenced review. The reviewer independently reads data, applicable audit facts and exact submitted code/result; approve correct work or raise a located evidenced issue. For repair, withdraw the pending submission, execute changed code, submit a new fixed result, respond to actual issues and independently check their treatment before final approval. Correct initial work can be approved without manufacture of a defect or unnecessary repair. Prior preparation is not current actor work.',
}


def _case(task, fact, quality=None):
    legacy = {'joint_a': 'pair', 'joint_b': 'review'}.get(task, task)
    base = retail_balanced.resolve('development', fact, legacy, quality)
    identity = [VERSION, task, fact, quality]
    active = {'implement': ['implementer'], 'review': ['reviewer'],
              'joint_a': ['provider', 'implementer'], 'joint_b': ['implementer', 'reviewer']}[task]
    limits = {'implement': {'implementer': 12}, 'review': {'reviewer': 12},
              'joint_a': {'provider': 6, 'implementer': 16},
              'joint_b': {'implementer': 24, 'reviewer': 28}}[task]
    return {**base, 'version': VERSION, 'case_id': 'retail-v21-' + digest(json_bytes(identity))[:16],
            'task': task, 'active_roles': active, 'role_decision_limits': limits,
            'purpose': 'interface_development', 'model_training_eligible': False,
            'base_task': legacy, 'mapper_version': MAPPER_VERSION}


def registry():
    cases = [_case('implement', 0), _case('implement', 1), _case('review', 0, 'correct'),
             _case('review', 0, 'wrong_count'), _case('joint_a', 2), _case('joint_b', 0, 'wrong_amount')]
    return {'version': VERSION, 'situations': cases, 'source_family_count': 1,
            'selection': 'Fixed before target model outcomes: two implementation, two same-policy review, joint A and joint B. No replacement or outcome-based resampling.',
            'usage': 'Existing UCI development slices and simulated reporting policies only; not independent held-out sources.',
            'cpu_quality_controls': list(retail_balanced.QUALITIES), 'learning_projection_available': False}


def cpu_variant(quality):
    if quality not in retail_balanced.QUALITIES:
        raise ValueError('Unknown crossed CPU preparation quality')
    return _case('joint_b', 0, quality)


def case_spec(case_id):
    cases = {c['case_id']: c for c in [*registry()['situations'], *(cpu_variant(q) for q in retail_balanced.QUALITIES)]}
    if case_id not in cases:
        raise ValueError('Unknown frozen collaboration case')
    return copy.deepcopy(cases[case_id])


def reward_spec(case):
    task = case['task']
    return {'version': REWARD_VERSION, 'reward_id': 'collaboration-' + task,
            'task': task, 'project_id': 'TEAM', 'work_id': WORK,
            'period': case['business_facts']['period'], 'basis_provider': 'provider',
            'active_roles': case['active_roles'], 'preparation_credit': False,
            'terms': [{'term_id': k, 'weight': w} for k, w in TERMS[task]],
            'public_requirement': PUBLIC[task], 'mapper_version': MAPPER_VERSION,
            'credit_rule': 'Finite Boolean outcomes only, no message/action counts. An initially correct fixed product is inherited state, not current implementation credit.',
            'unknown_rule': 'Missing or corrupt fixed evidence is unknown. A trusted closed episode with incomplete work is assessable failure; termination labels alone do not replace content evidence.',
            'training_projection': 'Not available in v0.21; fixed-policy evaluation only.'}


def build_case(case, root, *, assets_root=None):
    if isinstance(case, str):
        case = case_spec(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Changed frozen collaboration case')
    case = copy.deepcopy(case)
    base = {**case, 'task': case['base_task']}
    spec = retail_work.scenario(base, source_root=assets_root)
    contract = reward_spec(case)
    spec['world']['world_id'] = 'retail-collaboration-v021'
    spec['scenario_id'] = case['case_id']
    spec['variation'] = {'kind': 'structure', 'online_case': case, 'online_reward': contract,
                         'source_asset': {'family': case['family'], 'usage_pool': case['pool'], 'slice_id': case['slice_id']},
                         'mapper_version': MAPPER_VERSION, 'preparation_credit': False}
    pkg = spec['projects'][0]['package']
    item = pkg['works'][0]
    item['requirements']['online_scope'] = contract
    item['visible_requirements'].append(PUBLIC[case['task']])
    item['goal'] = pkg['goal'] = PUBLIC[case['task']]
    tasks = {
        'provider': 'Read your privately held applicable policy and provide its exact version legally. You may hand it over proactively or after a request. Do not produce the implementer result.',
        'implementer': 'Implement the public retail contract using legally obtained exact source versions. Inspect an existing fixed submission when present; it may be correct. You may self-check and repair a genuine defect or respond to independently evidenced review. Do not manufacture rework. Pending submissions need withdrawal before replacement. Read the public online_scope.',
        'reviewer': 'Independently check actual fixed code/result against exact UCI data and your private applicable audit facts, which contain no answer table. Any initial submission may be correct or incorrect. Approve supported work, or raise a genuinely located issue with data/audit evidence, then inspect real repaired fixed versions and decide issue responses before final approval. Read public online_scope.',
    }
    spec['roles'] = [{'role_id': r, 'actor': r, 'project': 'TEAM', 'policy': 'model', 'config': {'task': tasks[r]}}
                     for r in case['active_roles']]
    spec['boundary'] = {'max_opportunities': sum(case['role_decision_limits'].values()) + len(case['active_roles'])}
    prepared = retail_work._build_prepared_case(base, root, declaration=spec, version=VERSION)
    return PreparedOnlineCase(prepared.deployment, case, contract, prepared.prefix)


def _quality(evidence, sub):
    if sub is None:
        return None
    result = evaluate_submission(evidence.store, evidence.state, evidence.item, sub)
    if result['status'] not in {'pass', 'content_failure', 'structure_failure'}:
        raise ValueError('Fixed submission lacks independent assessability')
    return result


def _calls(e, actor, action, sid=None):
    return [c for c in e.successful if c['worker_id'] == actor and c['payload']['action'] == action
            and (sid is None or c['payload']['arguments'].get('submission_id') == sid)]


def _actual_fixed_build(e, sub, *, current):
    if not sub or (sub.get('review') or {}).get('decision') == 'withdrawn' or not _quality(e, sub)['passed']:
        return None
    result_ref = (e.aliases['result'], sub['artifact_versions'].get(e.aliases['result']))
    code_ref = (e.aliases['code'], sub['artifact_versions'].get(e.aliases['code']))
    provenance = e.state['artifacts'][result_ref[0]]['versions'][result_ref[1]].get('execution_provenance', {})
    sources = {k: _ref(v) for k, v in provenance.get('source_references', {}).items()}
    if (provenance.get('kind') != 'sql_build' or provenance.get('status') != 'success'
            or provenance.get('work_id') != WORK or _ref(provenance.get('code_reference')) != code_ref
            or sources != e.adopted_refs(sub) or not e.applicable_basis(sources.get('basis'))):
        return None
    builds = [c for c in _calls(e, 'implementer', 'sql_build')
              if _ref(c['payload']['response']['result'].get('reference')) == result_ref]
    submits = [c for c in _calls(e, 'implementer', 'submit')
               if c['payload']['response']['result'].get('submission_id') == sub['submission_id']]
    is_new = sub['submission_id'] not in {s['submission_id'] for s in e.start['work_items'][WORK]['submissions']}
    if current and (not is_new or not builds or not submits or builds[-1]['sequence'] >= submits[-1]['sequence']
                    or not e.read_inputs(builds[-1]['sequence'], sub)):
        return None
    return {'submission_id': sub['submission_id'], 'result_reference': list(result_ref),
            'code_reference': list(code_ref), 'source_references': {k: list(v) for k, v in sources.items()},
            'current_actor_build': bool(is_new and builds and submits),
            'build_sequence': builds[-1]['sequence'] if builds else None,
            'submit_sequence': submits[-1]['sequence'] if submits else None}


def _judgments(e):
    rows = []
    for call in e.successful:
        if call['worker_id'] != 'reviewer' or call['payload']['action'] not in {'approve', 'raise_issue'}:
            continue
        arguments = call['payload']['arguments']
        sub = next((s for s in e.item['submissions'] if s['submission_id'] == arguments.get('submission_id')), None)
        if sub is None:
            raise ValueError('Missing immutable review target')
        quality = _quality(e, sub)
        reads = e.review_reads(sub, call['sequence'])
        issue = None
        if call['payload']['action'] == 'approve':
            valid = quality['passed'] and bool(reads)
        else:
            issue_id = call['payload']['response']['result']['issue_id']
            issue = e.state['issues'][issue_id]
            valid = (not quality['passed'] and bool(reads) and issue['blocking'] and issue['active_at_creation']
                     and e.wrong_location(sub, issue, reads))
        rows.append({'action': call['payload']['action'], 'sequence': call['sequence'],
                     'submission_id': sub['submission_id'], 'valid': bool(valid),
                     'read_evidence': reads, 'issue_id': issue['issue_id'] if issue else None})
    return rows


def _implementation_inspected(e, original, before):
    refs = [(oid, vid) for oid, vid in original['artifact_versions'].items()]
    return bool(any(c['sequence'] < before for c in _calls(e, 'implementer', 'inspect_submission', original['submission_id']))
                and all(e.read_before('implementer', ref, before) for ref in refs)
                and e.read_inputs(before, original))


def _issue_treatment(e, judgment, final):
    iid = judgment['issue_id']
    responses = [c for c in _calls(e, 'implementer', 'respond_issue', final['submission_id'])
                 if c['payload']['arguments'].get('issue_id') == iid]
    for response in responses:
        rid = response['payload']['response']['result']['response_id']
        for decision in _calls(e, 'reviewer', 'decide_issue'):
            args = decision['payload']['arguments']
            if (args.get('issue_id') == iid and args.get('response_id') == rid and args.get('decision') == 'accept_fix'
                    and judgment['sequence'] < response['sequence'] < decision['sequence']
                    and e.review_reads(final, decision['sequence'])):
                return {'issue_id': iid, 'response_id': rid, 'decision_sequence': decision['sequence'],
                        'submission_id': final['submission_id']}
    return None


def _mapping(task, completed, facts):
    label = None
    if completed:
        if task == 'joint_a':
            label = 'requested_delivery_and_use' if facts.get('requested') else 'proactive_delivery_and_use'
        elif task == 'joint_b':
            label = facts['repair_path']
        else:
            label = 'independent_' + task
    return {'version': MAPPER_VERSION, 'class_id': label, 'eligible': bool(completed),
            'features': {k: facts.get(k) for k in ('requested', 'initial_correct', 'repair_path')},
            'scope': 'Descriptive actual path within this exact initial situation only. No causal member contribution, model support counts, SFT target or training projection.'}


def assess_episode(episode_path, spec=None):
    """The v0.21 public entry stays bound to its original frozen contract."""
    return _assess_episode(episode_path, spec, resolve_case=case_spec,
                           make_reward_spec=reward_spec, report_version=REWARD_VERSION,
                           mapper_version=MAPPER_VERSION, map_method=_mapping)


def _assess_episode(episode_path, spec, *, resolve_case, make_reward_spec,
                    report_version, mapper_version, map_method):
    """Shared fixed-history mechanics; callers explicitly bind their own catalog."""
    root = Path(episode_path)
    if root.name == 'manifest.json':
        root = root.parent
    report = {'version': report_version, 'eligible': False, 'reward': None, 'completed': False,
              'components': [], 'work_components': {}, 'record_trust': 'unknown',
              'independent_assessability': 'unknown', 'exclusions': [], 'preparation_credited': False,
              'mapper': {'version': mapper_version, 'class_id': None, 'eligible': False}}
    try:
        manifest = read_json(root / 'manifest.json')
        case = resolve_case(manifest['scenario']['variation']['online_case']['case_id'])
        expected = make_reward_spec(case)
        declared = manifest['scenario']['variation']['online_reward']
        if manifest['status'] != 'closed' or declared != expected or (spec is not None and spec != expected):
            raise ValueError('Closed episode must bind its frozen collaboration contract')
        if manifest['scenario']['variation']['online_case'] != case:
            raise ValueError('Scenario case differs from the fixed source/quality declaration')
        report['termination'] = manifest['termination']
        report['case_id'] = case['case_id']
        assessment = assess_historical_episode(root)
        if assessment.get('assessment_execution', {}).get('status') != 'complete':
            raise ValueError('Independent historical evidence unavailable: ' + str(assessment.get('assessment_execution')))
        e = RetailEvidence(root, expected, assessment)
        if e.start['work_items'][WORK]['requirements'].get('online_scope') != expected:
            raise ValueError('Public world contract differs from episode scope')
        critical = [event for event in e.events
                    if event.get('kind') in {'interface_exception', 'interface_error', 'model_service_error', 'binding_mismatch'}
                    or event.get('status') in {'model_service_error', 'environment_error', 'binding_mismatch', 'model_usage_missing'}
                    or (isinstance(event.get('payload'), dict) and event['payload'].get('status') in {'model_service_error', 'environment_error', 'binding_mismatch', 'model_usage_missing'})]
        if critical:
            report['record_trust'] = 'service_identity_or_interface_failure'
            raise ValueError('Critical runtime failure prevents trusted scoped evaluation')
        report['record_trust'] = 'verified_world_receipts_and_fixed_history'
        submissions = e.item['submissions']
        final = submissions[-1] if submissions else None
        fixed = _actual_fixed_build(e, final, current=case['task'] in {'implement', 'joint_a'})
        task = case['task']
        built = e.correct_build() if task in {'implement', 'joint_a'} else None
        if built and not e.read_inputs(built['action_sequence']):
            built = None
        facts, predicates = {'final_fixed_build': fixed, 'current_correct_build': built}, {}
        if task in {'implement', 'joint_a'}:
            if task == 'implement':
                predicates = {'current_correct_build': bool(built), 'current_correct_fixed_delivery': bool(fixed)}
            else:
                handoff = e.handoff()
                built_basis = (_ref(e.document(tuple(built['reference'])).get('sources', {}).get('basis'))
                               if built else None)
                used = bool(handoff and built and tuple(handoff['reference']) == built_basis
                            and handoff['action_sequence'] < built['action_sequence'])
                delivered_fixed = bool(used and fixed and handoff['reference'] == fixed['source_references']['basis'])
                delivered = e.state['handoffs'].get(handoff['handoff_id'], {}) if handoff else {}
                requested = any(c['sequence'] < handoff['action_sequence']
                                and c['payload']['arguments'].get('route_id') == 'basis'
                                and c['payload']['arguments'].get('work_id') == WORK
                                and c['payload']['response']['result'].get('request_id') == delivered.get('request_id')
                                for c in _calls(e, 'implementer', 'request_information')) if handoff and delivered.get('request_id') else False
                facts.update(handoff=handoff, requested=requested)
                predicates = {'applicable_basis_delivered': bool(handoff), 'delivered_basis_used_in_build': used,
                              'correct_fixed_delivery': delivered_fixed}
        else:
            judgments = _judgments(e)
            facts['judgments'] = judgments
            if task == 'review':
                original = e.start['work_items'][WORK]['submissions'][-1]
                decisions = [j for j in judgments if j['submission_id'] == original['submission_id']]
                before = min((j['sequence'] for j in decisions), default=float('inf'))
                initial = next(s for s in submissions if s['submission_id'] == original['submission_id'])
                predicates = {'independent_review_evidence': bool(e.review_reads(initial, before)),
                              'correct_fixed_review_judgment': bool(decisions and all(j['valid'] for j in decisions))}
            else:
                initial = e.start['work_items'][WORK]['submissions'][-1]
                original = next(s for s in submissions if s['submission_id'] == initial['submission_id'])
                initial_correct = bool(_quality(e, original)['passed'])
                approval = [j for j in judgments if final and j['submission_id'] == final['submission_id'] and j['action'] == 'approve' and j['valid']]
                review_ok = bool(approval and all(j['valid'] for j in judgments))
                new_fixed = _actual_fixed_build(e, final, current=True)
                issues = [j for j in judgments if j['action'] == 'raise_issue' and j['valid']]
                treatment = [_issue_treatment(e, j, final) for j in issues] if final else []
                if initial_correct and final and final['submission_id'] == initial['submission_id']:
                    path, path_ok = 'verified_correct_without_repair', not issues
                else:
                    withdrawals = _calls(e, 'implementer', 'withdraw', initial['submission_id'])
                    before = withdrawals[0]['sequence'] if withdrawals else float('-inf')
                    inspected = _implementation_inspected(e, original, before)
                    if issues:
                        path = 'evidenced_review_then_targeted_repair'
                        path_ok = (bool(new_fixed and withdrawals and inspected and all(treatment))
                                   and all(j['sequence'] < before for j in issues))
                    else:
                        path = 'implementer_self_check_then_independent_review'
                        path_ok = bool(new_fixed and withdrawals and inspected)
                facts.update(initial_correct=initial_correct, repair_path=path,
                             initial_submission_id=initial['submission_id'], treatment=treatment,
                             current_repair_build=new_fixed)
                predicates = {'independent_final_review': review_ok,
                              'correct_fixed_final_product': bool(fixed and (new_fixed or approval)),
                              'valid_review_and_repair_path': bool(path_ok and review_ok)}
        components = [{**term, 'achieved': bool(predicates[term['term_id']]),
                       'score': term['weight'] if predicates[term['term_id']] else 0.0} for term in expected['terms']]
        completed = all(c['achieved'] for c in components)
        report.update(eligible=True, independent_assessability='known', components=components,
                      reward=round(sum(c['score'] for c in components), 10), completed=completed,
                      facts=facts, mapper=map_method(task, completed, facts),
                      work_components={'business_product': bool(fixed), 'full_responsibility': completed},
                      episode_manifest_sha256=digest((root / 'manifest.json').read_bytes()),
                      current_actor_tool_calls=len(e.calls), training_projection_available=False)
    except (KeyError, OSError, ValueError, TypeError) as error:
        report['exclusions'].append({'type': type(error).__name__, 'reason': str(error)})
    return report
