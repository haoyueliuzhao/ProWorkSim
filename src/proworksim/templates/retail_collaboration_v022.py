"""New UCI work materials and explicit public review locator contract for W1."""
import copy
from pathlib import Path

from ..storage import digest, json_bytes, read_json
from . import retail_collaboration_v021 as prior
from . import retail_work
from .decision_team import package as base_package, scenario_spec
from .online_work import PreparedOnlineCase

VERSION = 'retail-collaboration-v0.22'
REWARD_VERSION = 'retail-collaboration-outcomes-v0.22'
MAPPER_VERSION = 'retail-collaboration-observed-path-v0.22'
WORK = prior.WORK
PIN_PATH = Path(__file__).resolve().parents[3] / 'examples/retail-collaboration-v22/source-manifest.json'
DEFAULT_ASSETS = Path(__file__).resolve().parents[3] / 'runs/assets/uci-collaboration-v022'
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


def _case(position, task, quality, purpose):
    active = {'implement': ['implementer'], 'review': ['reviewer'], 'joint_a': ['provider', 'implementer'], 'joint_b': ['implementer', 'reviewer']}[task]
    limits = {'implement': {'implementer': 12}, 'review': {'reviewer': 12},
              'joint_a': {'provider': 6, 'implementer': 16}, 'joint_b': {'implementer': 24, 'reviewer': 28}}[task]
    return {'version': VERSION, 'case_id': 'retail-v22-' + digest(json_bytes([position, task, quality, purpose]))[:16],
            'task': task, 'base_task': {'joint_a': 'pair', 'joint_b': 'review'}.get(task, task),
            'pool': purpose, 'split': purpose, 'purpose': purpose, 'fact_position': position,
            'slice_id': f'v022-material-{position:02d}', 'family': 'uci-online-retail-352',
            'active_roles': active, 'role_decision_limits': limits, 'prepared_submission': quality,
            'model_training_eligible': False, 'source_admission': False, 'mapper_version': MAPPER_VERSION,
            'business_facts': {'period': 'UCI-2011-fixed-slice', 'edition': 'approved',
                               'start_inclusive': '2010-12-01 00:00:00',
                               'end_exclusive': '2011-07-01 00:00:00' if task == 'joint_a' else '2012-01-01 00:00:00',
                               'invoice_mode': 'net_signed' if position == 1 else 'sales_only',
                               'currency': 'GBP', 'duplicates': 'retain_source_rows', 'missing_customer': 'exclude',
                               'price_rule': 'strictly_positive', 'basis_provider': 'provider'}}


def registry():
    tasks = ['implement', 'implement', 'review', 'review', 'joint_a', 'joint_b', 'implement', 'review', 'joint_a', 'joint_b', 'joint_a', 'joint_b']
    qualities = [None, None, 'correct', 'wrong_count', None, 'wrong_amount', None, 'wrong_count', None, 'wrong_amount', None, 'wrong_count']
    purposes = ['w1_development'] * 6 + ['reserved_training'] * 4 + ['reserved_bridge_development'] * 2
    rows = [_case(i, t, q, use) for i, (t, q, use) in enumerate(zip(tasks, qualities, purposes))]
    slots = []
    for i, row in enumerate(rows[:6]):
        for arm in (ARMS if i % 2 == 0 else tuple(reversed(ARMS))):
            slots.append({'slot_id': f'w1-{i}-{arm}', 'case_id': row['case_id'], 'case_index': i,
                          'arm': arm, 'sampling_seed': 202609290100 + i, 'purpose': 'w1_development'})
    return {'version': VERSION, 'situations': rows[:6], 'reserved_training': rows[6:10], 'reserved_bridge': rows[10:],
            'arms': list(ARMS), 'ordered_slots': slots, 'source_family_count': 1,
            'policy': 'New complete invoice/customer/source-row groups within the existing UCI source, not renamed old facts or independent sources.',
            'comparison': 'Same new public contract, exact case, paired seed, role opportunities, tools, model,16384 total context and2048 output. Only deterministic presentation changes. Alternating within-case arm order fixed before outcomes.',
            'reserved_materials_run': False, 'model_training_eligible': False, 'learning_projection_available': False}


def case_spec(case_id):
    catalog = registry()
    for row in catalog['situations'] + catalog['reserved_training'] + catalog['reserved_bridge']:
        if row['case_id'] == case_id:
            return copy.deepcopy(row)
    raise ValueError('Unknown frozen v0.22 source situation')


def reward_spec(case):
    result = prior.reward_spec(case)
    result.update(version=REWARD_VERSION, mapper_version=MAPPER_VERSION,
                  training_projection='Unadmitted: reserved training requires a separate actual-token/identity/outcome projection and execution qualification.',
                  deliverable_scope='Correct result table for this exact fixed supplied material only; not a reusable-query or arbitrary-future-input guarantee.',
                  public_review_contract=copy.deepcopy(REVIEW_CONTRACT))
    return result


def _load(case, assets_root):
    root = Path(assets_root or DEFAULT_ASSETS)
    pin, manifest = read_json(PIN_PATH), read_json(root / 'manifest.json')
    if pin != manifest:
        raise ValueError('Source manifest differs from the source-controlled pin')
    entry = next(s for s in manifest['slices'] if s['slice_id'] == case['slice_id'])
    path = root / entry['path']
    if digest(path.read_bytes()) != entry['sha256']:
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
    objects['basis']['data'] = retail_work.basis(case)
    objects['audit_basis']['data'] = {**case['business_facts'], 'independent_checks': retail_work.basis(case)['meaning'], 'origin': 'Independent simulated reporting policy; no numerical answer table.'}
    work = pkg['works'][0]
    work['goal'] = pkg['goal'] = prior.PUBLIC[case['task']]
    work['visible_requirements'] = [prior.PUBLIC[case['task']], 'Deliver only the current fixed material result table; arbitrary future-input correctness is not evaluated. Public review target, locator and evidence rules are in requirements.review_contract.']
    req = work['requirements']
    req['online_scope'] = reward_spec(case)
    req['reporting_period'] = case['business_facts']['period']
    req['sql_project']['kind'] = 'uci_retail'
    req['public_structure']['sql_result']['table_columns']['metrics'] = ['CustomerID', 'revenue_pence', 'invoice_count']
    req['public_format']['output'] = 'Exactly metrics with CustomerID text, revenue_pence integer GBP pence, invoice_count integer distinct qualifying InvoiceNo. One row per data.customers including zeros. Read applicable policy for date/cancellation/quantity/price/duplicates. Current bounded source slice only.'
    req['review_contract'] = {'audit_alias': 'audit_basis', **copy.deepcopy(REVIEW_CONTRACT)}
    work['deliverable_contract']['content_checks'][0].update(kind='retail_customer_metrics', period=case['business_facts']['period'])
    pkg['provenance'] = {'kind': 'reconstructed', 'source_evidence_refs': [manifest['doi'], manifest['xlsx']['sha256'], entry['sha256']],
                         'note': 'New entity-disjoint raw UCI material; simulated workflow and reporting policy. Same source family and fixed-material responsibility.'}
    return pkg


def build_case(case, root, *, assets_root=None):
    if isinstance(case, str):
        case = case_spec(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Changed v0.22 frozen case')
    case = copy.deepcopy(case)
    spec = scenario_spec()
    spec['world']['world_id'] = 'retail-collaboration-v022'
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
    prepared = retail_work._build_prepared_case(base, root, declaration=spec, version=VERSION)
    return PreparedOnlineCase(prepared.deployment, case, reward_spec(case), prepared.prefix)


def _map_method(task, completed, facts):
    return {**prior._mapping(task, completed, facts), 'version': MAPPER_VERSION}


def assess_episode(episode_path, spec=None):
    return prior._assess_episode(episode_path, spec, resolve_case=case_spec,
                                 make_reward_spec=reward_spec, report_version=REWARD_VERSION,
                                 mapper_version=MAPPER_VERSION, map_method=_map_method)
