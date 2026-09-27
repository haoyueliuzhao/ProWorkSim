"""New source-partitioned finite responsibilities for the four-window Q=B pilot."""
import copy
from pathlib import Path

from ..storage import digest, json_bytes, read_json
from . import retail_collaboration_v021 as prior
from . import retail_work
from .decision_team import package as base_package, scenario_spec
from .online_work import PreparedOnlineCase

VERSION = 'retail-collaboration-v0.23'
REWARD_VERSION = 'retail-collaboration-outcomes-v0.23'
MAPPER_VERSION = 'retail-collaboration-observed-path-v0.23'
WORK = prior.WORK
PIN_PATH = Path(__file__).resolve().parents[3] / 'examples/retail-collaboration-v23/source-manifest.json'
DEFAULT_ASSETS = Path(__file__).resolve().parents[3] / 'runs/assets/uci-collaboration-v023'
ARMS = ('original_history', 'compact_work')
REVIEW_CONTRACT = {
    'version': 'public-result-review-contract-v0.22',
    'target': 'For a scored blocking issue, object_id/version_id MUST identify the result object in the exact inspected fixed submission. A code-only issue can be stored by the generic tool but does not fulfill this result-table review responsibility.',
    'row_locator': '["tables", "metrics", "rows", i]',
    'cell_locator': '["tables", "metrics", "rows", i, j]',
    'indices': 'i is a zero-based integer index in the exact fixed result tables.metrics.rows array. j is a zero-based integer index in that same table columns array. Row-level location asserts at least one business cell in that actual row is wrong; cell-level asserts the specifically indexed business cell is wrong. Neither customer IDs nor SQL text offsets are row indices.',
    'evidence': 'Explicitly include BOTH the exact data object/version adopted by this submission and your applicable independent audit_basis object/version in evidence. Read those exact versions before judgment, and also inspect the fixed submission and read its exact code/result. Merely having read data, citing it in prose or citing code instead does not supply its required evidence reference.',
    'example': {'scope': 'Structural illustration only; angle-bracket values are placeholders, not an executable call or an answer location.',
                'object_id': '<fixed_result_object_id>', 'version_id': '<fixed_result_version>',
                'locator': ['tables', 'metrics', 'rows', '<zero_based_row_i>', '<optional_zero_based_column_j>'],
                'evidence': [{'object_id': '<adopted_data_object_id>', 'version_id': '<adopted_data_version>'},
                             {'object_id': '<read_applicable_audit_object_id>', 'version_id': '<read_audit_version>'}]},
    'correct_work': 'If the independently inspected fixed product is correct, approve it; no issue or repair is required.',
}


def _case(position, task, quality, purpose, window_index=None):
    material_sha256 = read_json(PIN_PATH)['slices'][position]['sha256']
    base_task = 'joint_b' if task == 'maintenance' else task
    active = {'implement': ['implementer'], 'review': ['reviewer'], 'joint_a': ['provider', 'implementer'], 'joint_b': ['implementer', 'reviewer']}[base_task]
    limits = {'implement': {'implementer': 12}, 'review': {'reviewer': 12},
              'joint_a': {'provider': 6, 'implementer': 16}, 'joint_b': {'implementer': 24, 'reviewer': 28}}[base_task]
    maintenance = {'event_id': 'client-policy-reissue', 'old_basis_version': 'v1', 'new_basis_version': 'v2',
                   'new_audit_version': 'v2', 'old_fixed_product_prepared_correct': True,
                   'expected_result_change': position in (8, 9)} if task == 'maintenance' else None
    facts = {'period': 'UCI-2011-fixed-slice', 'edition': 'approved',
             'start_inclusive': '2010-12-01 00:00:00',
             'end_exclusive': '2011-07-01 00:00:00' if task == 'joint_a' else '2012-01-01 00:00:00',
             'invoice_mode': 'net_signed' if maintenance and maintenance['expected_result_change'] else 'sales_only',
             'currency': 'GBP', 'duplicates': 'retain_source_rows', 'missing_customer': 'exclude',
             'price_rule': 'strictly_positive', 'basis_provider': 'provider'}
    return {'version': VERSION, 'case_id': 'retail-v23-' + digest(json_bytes([material_sha256, position, task, quality, purpose, window_index]))[:16],
            'task': task, 'base_task': {'joint_a': 'pair', 'joint_b': 'review', 'maintenance': 'review'}.get(task, task),
            'pool': purpose, 'split': purpose, 'purpose': purpose, 'fact_position': position,
            'window_index': window_index, 'material_sha256': material_sha256, 'slice_id': f'v023-material-{position:02d}', 'family': 'uci-online-retail-352',
            'active_roles': active, 'role_decision_limits': limits, 'prepared_submission': quality,
            'model_training_eligible': False, 'source_admission': False, 'mapper_version': MAPPER_VERSION,
            'maintenance': maintenance, 'business_facts': facts}


def registry():
    evaluation = [_case(i, 'joint_a' if i < 4 else 'joint_b' if i < 8 else 'maintenance',
                        None if i < 4 else ('correct', 'wrong_count', 'wrong_amount', 'correct')[i-4] if i < 8 else 'correct',
                        'paired_evaluation') for i in range(12)]
    windows, train = [], []
    b_qualities = ['correct', 'wrong_count', 'wrong_amount', 'wrong_count']
    review_qualities = ['wrong_amount', 'correct', 'wrong_count', 'correct']
    for w in range(4):
        cases = [_case(12+4*w+k, task, quality, 'pilot_training', w)
                 for k, (task, quality) in enumerate(zip(['joint_a', 'joint_b', 'implement', 'review'],
                                                        [None, b_qualities[w], None, review_qualities[w]]))]
        train.extend(cases)
        slots = []
        for k, (case_index, repeat) in enumerate([(0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1)]):
            case = cases[case_index]
            seed = 202609300000 + 100*w + k
            slots.append({'slot_id': f'train-{w+1}-{k}', 'case_id': case['case_id'], 'task': case['task'],
                          'seed': seed, 'sampling_seed': seed, 'repeat_index': repeat})
        windows.append({'window_id': f'v023-window-{w+1}', 'window_index': w, 'slots': slots})
    slots = [{'slot_id': f'eval-{i:02d}-{r}', 'case_id': c['case_id'], 'case_index': i,
              'task': c['task'], 'repeat_index': r, 'seed': 202609301000 + 2*i+r,
              'sampling_seed': 202609301000 + 2*i+r} for i, c in enumerate(evaluation) for r in range(2)]
    return {'version': VERSION, 'evaluation_cases': evaluation, 'evaluation_slots': slots,
            'training_windows': windows, 'training_cases': train, 'all_cases': evaluation + train,
            'source_family_count': 1, 'model_training_eligible': False,
            'presentation': 'compact_work', 'context_tokens': 16384, 'max_output_tokens': 2048,
            'qualities': {'evaluation_b': ['correct', 'wrong_count', 'wrong_amount', 'correct'],
                         'training_b_by_window': b_qualities, 'training_review_by_window': review_qualities},
            'maintenance': 'Two actual policy changes require new results; two actual policy reissues require evidence-based retention. Prepared old correct fixed delivery is not current model credit.',
            'usage': '72 internal episodes:24 initial evaluation,4 windows x6 train,24 final evaluation; two repeats are not distinct situations; same UCI source family.',
            'quality_and_seed_order': 'Fixed before model outcomes; no replacement, outcome-based selection or pool crossing.'}


def case_spec(case_id):
    for row in registry()['all_cases']:
        if row['case_id'] == case_id:
            return copy.deepcopy(row)
    raise ValueError('Unknown frozen v0.23 source situation')


MAINTENANCE_PUBLIC = (
    'A previously correct fixed pending delivery was prepared before your episode; it is not your work. '
    'The client has now actually reissued basis v2 and audit_basis v2. Read the new exact policy and independently '
    'inspect the old fixed code/result and data. If the existing numerical result still satisfies the reissued policy, '
    'retain it and independently approve after full evidence reads; do not manufacture a change. Otherwise the '
    'implementer must withdraw, adopt current exact basis, execute and submit the correct new fixed result; the reviewer '
    'must independently read its exact code/result, data and current audit before approval. Resolve any actually raised '
    'issues. The implementer must inspect old code/result, data and new policy even when retention is justified. '
    'The basis adoption is current_applicable: after reading basis v2, explicitly use adopt_version with exact work_id and alias basis before rebuilding. Never re-adopt an existing binding. Only this triggered fixed-material maintenance responsibility is evaluated, not arbitrary future inputs.'
)


def reward_spec(case):
    base = {**case, 'task': 'joint_b'} if case['task'] == 'maintenance' else case
    result = prior.reward_spec(base)
    result.update(version=REWARD_VERSION, mapper_version=MAPPER_VERSION,
                  training_projection='Conditional actual-token/window admission is separate from this public work contract.',
                  deliverable_scope='Correct result table for this exact fixed supplied material only; not arbitrary-future-input correctness.',
                  public_review_contract=copy.deepcopy(REVIEW_CONTRACT))
    if case['task'] == 'maintenance':
        result.update(task='maintenance', reward_id='collaboration-maintenance', public_requirement=MAINTENANCE_PUBLIC,
                      terms=[{'term_id': n, 'weight': w} for n, w in
                             [('independent_current_policy_review', .4), ('correct_current_policy_fixed_product', .3), ('valid_maintenance_response', .3)]],
                      maintenance_event={'event_id': 'client-policy-reissue', 'basis_version': 'v2', 'audit_version': 'v2'},
                      credit_rule='No credit for prepared correct delivery or event execution. Current implementer inspection and independent current-policy review are required; unchanged correct values are retained without invented rework.')
    return result


def _load(case, assets_root):
    root = Path(assets_root or DEFAULT_ASSETS)
    pin, manifest = read_json(PIN_PATH), read_json(root / 'manifest.json')
    if pin != manifest:
        raise ValueError('Source manifest differs from the source-controlled pin')
    entry = next(s for s in manifest['slices'] if s['slice_id'] == case['slice_id'])
    path = root / entry['path']
    if digest(path.read_bytes()) != entry['sha256'] or entry['sha256'] != case['material_sha256']:
        raise ValueError('New source material changed')
    data = read_json(path)
    if (data['source_xlsx_sha256'] != retail_work.SOURCE_PIN['xlsx_sha256']
            or {r[-1] for r in data['rows']} != set(entry['source_rows'])
            or set(data['customers']) & set(manifest['excluded_customers'])
            or set(data['invoice_ids']) & set(manifest['excluded_invoices'])
            or set(entry['source_rows']) & set(manifest['excluded_source_rows'])):
        raise ValueError('New material violates its source/entity/row boundary')
    return data, manifest, entry


def package(case, *, assets_root=None):
    data, manifest, entry = _load(case, assets_root)
    pkg = base_package()
    objects = {o['alias']: o for o in pkg['objects']}
    columns = list(zip(data['fields'], ['VARCHAR', 'VARCHAR', 'VARCHAR', 'BIGINT', 'TIMESTAMP', 'DECIMAL(18,2)', 'VARCHAR', 'VARCHAR', 'BIGINT']))
    objects['data']['data'] = {'tables': {'retail': retail_work._table(columns, data['rows']),
                                         'customers': retail_work._table([('CustomerID', 'VARCHAR')], [[x] for x in data['customers']])},
                              'source': {'dataset': 'UCI Online Retail', 'doi': manifest['doi'], 'license': manifest['license'],
                                         'attribution': manifest['attribution'], 'original_sha256': manifest['xlsx']['sha256'],
                                         'slice_sha256': entry['sha256'], 'original_rows_preserved': True},
                              'slice_boundary': 'Complete selected invoices only, not all customer history. Evaluate only this supplied fixed slice.',
                              'field_definitions': {'InvoiceNo': 'Leading C/c is a cancellation.', 'UnitPrice': 'GBP per unit; exact original selected decimal.',
                                                    'Quantity': 'Signed original units.', 'InvoiceDate': 'Source local-naive timestamp.', 'SourceRow': 'Original XLSX row including header offset.'}}
    objects['code']['data'] = retail_work.initial_code()
    initial_case = copy.deepcopy(case)
    if case['task'] == 'maintenance':
        initial_case['business_facts']['invoice_mode'] = 'sales_only'
    objects['basis']['data'] = retail_work.basis(initial_case)
    objects['audit_basis']['data'] = {**initial_case['business_facts'], 'independent_checks': retail_work.basis(case)['meaning'], 'origin': 'Independent simulated reporting policy; no numerical answer table.'}
    work = pkg['works'][0]
    work['goal'] = pkg['goal'] = reward_spec(case)['public_requirement']
    work['visible_requirements'] = [reward_spec(case)['public_requirement'], 'Deliver only the current fixed material result table; arbitrary future-input correctness is not evaluated. Public review target, locator and evidence rules are in requirements.review_contract.']
    req = work['requirements']
    req['online_scope'] = reward_spec(case)
    req['reporting_period'] = case['business_facts']['period']
    req['sql_project']['kind'] = 'uci_retail'
    req['public_structure']['sql_result']['table_columns']['metrics'] = ['CustomerID', 'revenue_pence', 'invoice_count']
    req['public_format']['output'] = 'Exactly metrics with CustomerID text, revenue_pence integer GBP pence, invoice_count integer distinct qualifying InvoiceNo. One row per data.customers including zeros. Read applicable policy for date/cancellation/quantity/price/duplicates. Current bounded source slice only.'
    req['review_contract'] = {'audit_alias': 'audit_basis', **copy.deepcopy(REVIEW_CONTRACT)}
    if case['task'] == 'maintenance':
        req['input_policies']['basis'] = 'current_applicable'
        req['maintenance_notice'] = {'event_id': 'client-policy-reissue', 'basis': {'alias': 'basis', 'version_id': 'v2'}, 'audit': {'alias': 'audit_basis', 'version_id': 'v2'}, 'status': 'Actual reissue and delivered handoff executed before the current episode; inspect the immutable current policy, not a host quality label.'}
    work['deliverable_contract']['content_checks'][0].update(kind='retail_customer_metrics', period=case['business_facts']['period'])
    pkg['provenance'] = {'kind': 'reconstructed', 'source_evidence_refs': [manifest['doi'], manifest['xlsx']['sha256'], entry['sha256']],
                         'note': 'New entity-disjoint raw UCI material; simulated workflow and reporting policy. Same source family and fixed-material responsibility.'}
    return pkg


def build_case(case, root, *, assets_root=None):
    if isinstance(case, str):
        case = case_spec(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Changed v0.23 frozen case')
    case = copy.deepcopy(case)
    spec = scenario_spec()
    spec['world']['world_id'] = 'retail-collaboration-v023'
    spec['scenario_id'] = case['case_id']
    spec['projects'] = [{'package': package(case, assets_root=assets_root)}]
    descriptions = {
        'provider': 'Read and legally hand off your privately held applicable basis. Proactive delivery or responding to a recipient request is legitimate. Do not produce the implementer result.',
        'implementer': 'Implement the public fixed-material retail result contract through actual read/adoption/edit/build/submit actions. Existing pending work may be correct. Self-check or respond to evidenced review; withdraw before replacing a pending fixed submission. Read requirements.online_scope; it is an observation field, not a file alias.',
        'reviewer': 'Independently inspect fixed code/result using actual data and your audit_basis. Follow the explicit requirements.review_contract: result target, zero-based row/cell locator, BOTH exact already-read data and audit evidence references. Approve correct work without invented repair. Read requirements.online_scope; it is an observation field, not a file alias.'}
    spec['roles'] = [{'role_id': role, 'actor': role, 'project': 'TEAM', 'policy': 'model', 'config': {'task': descriptions[role]}} for role in case['active_roles']]
    spec['variation'] = {'kind': 'structure', 'online_case': case, 'online_reward': reward_spec(case),
                         'source_asset': {'family': case['family'], 'usage_pool': case['pool'], 'slice_id': case['slice_id']},
                         'mapper_version': MAPPER_VERSION, 'preparation_credit': False}
    spec['boundary'] = {'max_opportunities': sum(case['role_decision_limits'].values()) + len(case['active_roles'])}
    base = {**case, 'task': case['base_task']}
    prepared = _build_prepared_case(base, root, declaration=spec, version=VERSION) if case['task'] == 'maintenance' else retail_work._build_prepared_case(base, root, declaration=spec, version=VERSION)
    if case['task'] == 'maintenance':
        _trigger_maintenance(prepared, case, root)
    prepared.prefix['prepared_business_state_sha256_order_sensitive_legacy'] = prepared.prefix['prepared_business_state_sha256']
    prepared.prefix['prepared_business_state_sha256'] = prepared_business_state_hash(prepared.world)
    prepared.prefix['prepared_business_state_hash_format'] = 'canonical-keys-v023-all-original-business-fields-and-immutable-file-bytes'
    Path(root, 'preparation.json').write_bytes(json_bytes(prepared.prefix))
    return PreparedOnlineCase(prepared.deployment, case, reward_spec(case), prepared.prefix)


def _map_method(task, completed, facts):
    return {**prior._mapping(task, completed, facts), 'version': MAPPER_VERSION}


def assess_episode(episode_path, spec=None):
    root = Path(episode_path)
    if root.name == 'manifest.json':
        root = root.parent
    case = case_spec(read_json(root / 'manifest.json')['scenario']['variation']['online_case']['case_id'])
    if case['task'] == 'maintenance':
        return _assess_maintenance(root, case, spec)
    return prior._assess_episode(episode_path, spec, resolve_case=case_spec,
                                 make_reward_spec=reward_spec, report_version=REWARD_VERSION,
                                 mapper_version=MAPPER_VERSION, map_method=_map_method)


def _trigger_maintenance(prepared, case, root):
    """Execute the declared client event through real public object/handoff tools."""
    from ..experience import capture_port
    from ..scenarios import initial_business_state, save_deployment

    world = prepared.world
    captures = {r: [] for r in ('operator', 'provider')}
    ports = {r: capture_port(world.session(r, 'TEAM'), captures[r]) for r in captures}
    actions = []
    before = len(world.state['event_history'])

    def call(actor, tool, **args):
        response = ports[actor].call(tool, request_key=f'v023-maintenance-event-{len(actions)}', **args)
        actions.append({'actor': actor, 'tool': tool, 'arguments': args, 'response': response})
        if not response['ok']:
            raise ValueError({'maintenance_event_rejected': actions[-1]})
        return response['result']

    basis = call('operator', 'write_object', alias='basis', data=retail_work.basis(case))
    audit = call('operator', 'write_object', alias='audit_basis',
                 data={**case['business_facts'], 'independent_checks': retail_work.basis(case)['meaning'],
                       'origin': 'Actual client policy reissue; no answer table.'})
    ref = call('provider', 'read_alias', alias='basis', work_id=WORK)['reference']
    handoff = call('provider', 'handoff_information', route_id='basis', work_id=WORK,
                   handoff_key='client-policy-reissue', reference=ref,
                   body='The client reissued the applicable policy as basis v2 and audit_basis v2. Independently check the prior fixed delivery under the current policy; preserve correct values or update real differences. This event is not your current work.')
    call('operator', 'wait', ticks=1)
    if ref['version_id'] != 'v2':
        raise ValueError('Maintenance must publish the pinned second version')
    event = {'event_id': 'client-policy-reissue', 'origin': 'declared_external_event_after_correct_preparation',
             'credited_to_current_actor': False, 'actions': actions, 'captures': captures,
             'environment_events': copy.deepcopy(world.state['event_history'][before:]),
             'basis_write': basis, 'audit_write': audit, 'handoff': handoff}
    prepared.prefix['maintenance_event'] = event
    prepared.prefix['prepared_business_state_sha256'] = digest(json_bytes(initial_business_state(world)))
    Path(root, 'preparation.json').write_bytes(json_bytes(prepared.prefix))
    save_deployment(prepared.deployment)


def _assess_maintenance(root, case, supplied_spec):
    """Independently settle current policy response from frozen actual evidence."""
    from ..domains.retail_work import evaluate_check
    from ..episode import assess_historical_episode
    from ..online_rewards import _ref
    from ..retail_rewards import RetailEvidence

    expected = reward_spec(case)
    report = {'version': REWARD_VERSION, 'case_id': case['case_id'], 'eligible': False,
              'reward': None, 'completed': False, 'components': [], 'work_components': {},
              'record_trust': 'unknown', 'independent_assessability': 'unknown',
              'exclusions': [], 'preparation_credited': False,
              'mapper': {'version': MAPPER_VERSION, 'class_id': None, 'eligible': False}}
    try:
        manifest = read_json(root / 'manifest.json')
        variation = manifest['scenario']['variation']
        if (manifest['status'] != 'closed' or variation['online_case'] != case
                or variation['online_reward'] != expected
                or supplied_spec is not None and supplied_spec != expected):
            raise ValueError('Maintenance episode differs from frozen public contract')
        assessment = assess_historical_episode(root)
        if assessment.get('assessment_execution', {}).get('status') != 'complete':
            raise ValueError('Independent historical evidence unavailable')

        class CurrentEvidence(RetailEvidence):
            def applicable_audit(self, reference):
                return super().applicable_audit(reference) and reference[1] == 'v2'

        e = CurrentEvidence(root, expected, assessment)
        if e.start['work_items'][WORK]['requirements']['online_scope'] != expected:
            raise ValueError('Maintenance public world contract differs')
        critical = [v for v in e.events if v.get('kind') in {'interface_exception', 'interface_error', 'model_service_error', 'binding_mismatch'}
                    or v.get('status') in {'model_service_error', 'environment_error', 'binding_mismatch', 'model_usage_missing'}
                    or isinstance(v.get('payload'), dict) and v['payload'].get('status') in {'model_service_error', 'environment_error', 'binding_mismatch', 'model_usage_missing'}]
        if critical:
            raise ValueError('Critical runtime failure prevents known outcome')
        current_basis = (e.aliases['basis'], 'v2')
        current_audit = (e.aliases['audit_basis'], 'v2')
        e.document(current_basis)
        e.document(current_audit)
        handoffs = [h for h in e.start['handoffs'].values() if _ref(h.get('reference')) == current_basis
                    and h.get('status') == 'delivered' and h.get('response_status') == 'delivered'
                    and h.get('work_item_id') == WORK and h.get('recipients') == ['implementer']]
        if not handoffs:
            raise ValueError('Declared policy reissue did not actually reach its recipient before work')
        original_id = e.start['work_items'][WORK]['submissions'][-1]['submission_id']
        original = next(s for s in e.item['submissions'] if s['submission_id'] == original_id)
        if not prior._quality(e, original)['passed']:
            raise ValueError('Inherited old delivery was not independently correct under its original policy')

        def current_quality(sub):
            if sub is None:
                return False
            product = e.document((e.aliases['result'], sub['artifact_versions'][e.aliases['result']]))
            refs = e.adopted_refs(sub)
            check = e.item['deliverable_contract']['content_checks'][0]
            return evaluate_check(check, product, lambda alias: e.document(current_basis if alias == 'basis' else refs[alias]))['passed']

        changed = not current_quality(original)
        if changed != case['maintenance']['expected_result_change']:
            raise ValueError('Pinned maintenance material does not realize its predeclared changed/unchanged condition')
        judgments = []
        for call in e.successful:
            if call['worker_id'] != 'reviewer' or call['payload']['action'] not in {'approve', 'raise_issue'}:
                continue
            args = call['payload']['arguments']
            sub = next(s for s in e.item['submissions'] if s['submission_id'] == args.get('submission_id'))
            reads = e.review_reads(sub, call['sequence'])
            issue = None
            if call['payload']['action'] == 'approve':
                valid = current_quality(sub) and bool(reads)
            else:
                issue = e.state['issues'][call['payload']['response']['result']['issue_id']]
                valid = (not current_quality(sub) and bool(reads) and issue['blocking'] and issue['active_at_creation']
                         and e.wrong_location(sub, issue, reads))
            judgments.append({'action': call['payload']['action'], 'sequence': call['sequence'],
                              'submission_id': sub['submission_id'], 'valid': bool(valid),
                              'read_evidence': reads, 'issue_id': issue['issue_id'] if issue else None})
        final = e.item['submissions'][-1]
        approvals = [j for j in judgments if j['action'] == 'approve' and j['valid'] and j['submission_id'] == final['submission_id']]
        review_ok = bool(approvals and all(j['valid'] for j in judgments))
        new_fixed = prior._actual_fixed_build(e, final, current=True)
        current_build = bool(new_fixed and new_fixed['source_references']['basis'] == list(current_basis)
                             and current_quality(final))
        withdrawals = prior._calls(e, 'implementer', 'withdraw', original_id)
        before = withdrawals[0]['sequence'] if withdrawals else min((j['sequence'] for j in approvals), default=float('inf'))
        def own_received(reference):
            # A reviewer judgment is never used as an implementer consumer.
            # Require each implementer read return in that role's actual later
            # native request before the cross-role approval, even for no-change.
            for read in e.read_before('implementer', reference):
                if read['sequence'] >= before:
                    continue
                call_id = read['payload'].get('model_call_id')
                if call_id is None:
                    return True
                messages = [v['payload']['message'] for v in e.events
                            if v.get('worker_id') == 'implementer' and v['kind'] == 'model_tool_result'
                            and v['payload'].get('call_id') == call_id and v['sequence'] < before]
                attempts = [v for v in e.events if v.get('worker_id') == 'implementer' and v['kind'] == 'model_attempt'
                            and read['sequence'] < v['sequence'] < before and v['payload'].get('stage') == 'finished'
                            and v['payload'].get('status') == 'success']
                if any(m in v['payload']['request']['messages'] for m in messages for v in attempts):
                    return True
            return False

        inspected = bool(any(c['sequence'] < before for c in prior._calls(e, 'implementer', 'inspect_submission', original_id))
                         and all(own_received((oid, vid)) for oid, vid in original['artifact_versions'].items())
                         and own_received(e.adopted_refs(original)['data']) and own_received(current_basis))
        issues = [j for j in judgments if j['action'] == 'raise_issue' and j['valid']]
        treatments = [prior._issue_treatment(e, j, final) for j in issues]
        if changed:
            path = 'actual_policy_change_rebuilt_and_reviewed'
            path_ok = bool(inspected and withdrawals and current_build and review_ok and all(treatments))
        else:
            path = 'policy_reissue_verified_without_unnecessary_change'
            mutations = [c for c in e.successful if c['worker_id'] == 'implementer'
                         and c['payload']['action'] in {'write_object', 'sql_build', 'submit', 'withdraw'}]
            path_ok = bool(inspected and final['submission_id'] == original_id and not mutations and not issues and review_ok)
        product_ok = bool(current_quality(final) and (final.get('review') or {}).get('decision') != 'withdrawn'
                          and (current_build or approvals))
        predicates = {'independent_current_policy_review': review_ok,
                      'correct_current_policy_fixed_product': product_ok, 'valid_maintenance_response': path_ok}
        components = [{**t, 'achieved': predicates[t['term_id']], 'score': t['weight'] if predicates[t['term_id']] else 0.0} for t in expected['terms']]
        completed = all(v['achieved'] for v in components)
        report.update(eligible=True, reward=round(sum(v['score'] for v in components), 10), completed=completed,
                      components=components, record_trust='verified_world_receipts_and_fixed_history', independent_assessability='known',
                      facts={'maintenance_event_triggered': True, 'old_delivery_prepared_correct': True,
                             'actual_result_change_required': changed, 'implementer_current_inspection': inspected,
                             'judgments': judgments, 'current_repair_build': new_fixed,
                             'repair_path': path, 'treatment': treatments, 'initial_submission_id': original_id},
                      mapper={'version': MAPPER_VERSION, 'class_id': path if completed else None, 'eligible': completed,
                              'scope': 'Descriptive finite maintenance only; not ID-VTDO support or a teacher target.'},
                      work_components={'business_product': product_ok, 'full_responsibility': completed},
                      termination=manifest['termination'], episode_manifest_sha256=digest((root / 'manifest.json').read_bytes()),
                      current_actor_tool_calls=len(e.calls), training_projection_available=False)
    except (KeyError, OSError, ValueError, TypeError, StopIteration) as error:
        report['exclusions'].append({'type': type(error).__name__, 'reason': str(error)})
    return report


def _build_prepared_case(case, root, *, declaration, version):
    """Shared actual initialization after the caller validates its frozen catalog.

    Host-only preparation spec is not inserted in worker tasks or observations.
    """
    from ..audit import code_identity
    from ..experience import ExperienceRecorder, capture_port
    from ..scenarios import build_scenario, initial_business_state, save_deployment
    from .decision_team import ROLES

    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(declaration, root / 'world')
    if deployment.status != 'ready':
        raise ValueError(deployment.diagnostics)
    world = deployment.world
    captured = {r: [] for r in ROLES}
    ports = {r: capture_port(world.session(r, 'TEAM'), captured[r]) for r in ROLES}
    recorder = ExperienceRecorder()
    before = digest(json_bytes(initial_business_state(world)))
    offset = len(world.state['event_history'])
    source = code_identity()

    def call(actor, tool, **arguments):
        nonlocal offset
        response = ports[actor].call(tool, request_key=f'retail-preparation-{case["case_id"]}-{actor}-{len(recorder.events)}', **arguments)
        recorder.record('preparation_tool_call', {'origin': 'preparation', **captured[actor][-1]['payload']}, actor)
        for event in world.state['event_history'][offset:]:
            recorder.record('preparation_environment_event', event)
        offset = len(world.state['event_history'])
        if not response['ok']:
            raise ValueError({'preparation_rejected': tool, 'response': response})
        return response['result']

    if case['task'] in {'implement', 'review'}:
        ref = call('provider', 'read_alias', alias='basis', work_id='TEAM::build')['reference']
        call('provider', 'handoff_information', route_id='basis', work_id='TEAM::build', handoff_key='prepared-basis', reference=ref,
             body='Actual inherited policy delivery; preparation is excluded from current actor credit.')
        refs = []
        for alias in ('data', 'basis'):
            ref = call('implementer', 'read_alias', alias=alias, work_id='TEAM::build')['reference']
            call('implementer', 'adopt', alias=alias, **ref, policy='current_applicable' if alias == 'basis' else 'fixed', work_ids=['TEAM::build'])
            refs.append(ref)
        if case['task'] == 'review':
            call('implementer', 'write_object', alias='code', work_id='TEAM::build', dependencies=refs,
                 data=retail_work.witness_code(defect=case['prepared_submission']))
            built = call('implementer', 'sql_build', work_id='TEAM::build', code_alias='code', output_alias='result', input_aliases=['data', 'basis'])
            if built['execution_status'] != 'success':
                raise ValueError({'prepared_sql_failed': built})
            call('implementer', 'submit', work_id='TEAM::build', artifacts=['code', 'result'])
    prefix = {'version': version, 'origin': 'preparation', 'credited_to_current_actor': False,
              'case_id': case['case_id'], 'executed': bool(recorder.events), 'initial_business_state_sha256': before,
              'prepared_business_state_sha256': digest(json_bytes(initial_business_state(world))),
              'experience': recorder.snapshot(), 'independent_capture': captured, 'source_before': source, 'source_after': code_identity()}
    (root / 'preparation.json').write_bytes(json_bytes(prefix))
    (root / 'scenario.json').write_bytes(json_bytes(deployment.spec))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, reward_spec(case), prefix)


def runtime(owner, prepared, folder, arm='compact_work'):
    """Keep v022 compact; expose one existing legal tool only for maintenance."""
    from ..experience import ExperienceRecorder, capture_port
    from ..online_collection import _config
    from ..staff_runtime import StaffRuntime
    from ..work_interface import WorkInterface
    from ..work_view_v022 import CompactWorkModelPolicy, runtime as ordinary_runtime

    if prepared.case['task'] != 'maintenance':
        return ordinary_runtime(owner, prepared, folder, arm)
    if arm != 'compact_work':
        raise ValueError('Maintenance presentation is frozen to compact_work')
    folder = Path(folder)
    policies, ports, captures, interfaces = {}, {}, {}, {}
    for role in prepared.scenario['roles']:
        label = role['role_id']
        interface = WorkInterface(prepared.world.session(role['actor'], role['project']), label,
                                  audit_dir=folder/'public-projections'/label,
                                  variant='v23_maintenance' if label == 'implementer' else 'v14', presentation='compact_v14')
        interfaces[label] = interface
        ports[label] = capture_port(interface, captures.setdefault(label, []))
        config = _config(owner, label, role['config']['task'], prepared.case['role_decision_limits'])
        policies[label] = CompactWorkModelPolicy(config, transport=owner.transport, audit_dir=folder/'model-calls'/label)
        role.update(policy='model', config=copy.deepcopy(policies[label].config))
    return StaffRuntime(ports, policies, recorder=ExperienceRecorder()), captures, interfaces


def prepared_business_state_hash(world):
    """Canonical keys remove set iteration order, not business state or bytes."""
    from ..core.journal import canonical_digest
    from ..scenarios import initial_business_state

    return canonical_digest(initial_business_state(world))
