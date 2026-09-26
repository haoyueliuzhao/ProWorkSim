"""Finite real-source retail responsibilities in the shared work world.

UCI transaction bytes are real; business contracts, roles and workflow are
explicitly simulated. Initialization is outside the current learning episode.
"""
import copy
import os
from pathlib import Path

from ..audit import code_identity
from ..experience import ExperienceRecorder, capture_port
from ..scenarios import build_scenario, initial_business_state, save_deployment
from ..storage import digest, json_bytes, read_json
from .decision_team import ROLES, ROLE_TASKS, package as team_package, scenario_spec
from .online_work import PreparedOnlineCase, TERMS as ONLINE_TERMS

VERSION = 'retail-work-v0.15'
REWARD_VERSION = 'retail-work-reward-v0.15'
TASKS = ('implement', 'review', 'pair', 'chain')
TERMS = {key: copy.deepcopy(ONLINE_TERMS[key]) for key in ('implement', 'review', 'chain')}
TERMS['pair'] = [
    ('deliver_applicable_basis', 0.2, 'Actually read and deliver the applicable immutable retail policy to the implementer through its public route.'),
    ('correct_actual_build', 0.3, 'Use the received policy and exact adopted real source to execute independently correct customer metrics.'),
    ('correct_fixed_submission', 0.5, 'Actually read the adopted sources and submit the newly built correct SQL and result with fixed provenance.'),
]
ASSETS_ENV = 'PROWORKSIM_RETAIL_ASSETS'
SOURCE_PIN = {'xlsx_sha256': '43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d', 'slices': {'train-f0': '685e44105ee2b528044c3455770596796cbd35620b161ffed840d6973bb9ac8b', 'train-f1': '1615fe8f0c082e22644965091ce5ad6e16de87d62ccebadef5d79e4a0b8d2bfd', 'train-f2': '68e2c20aae52c4b7aef3aa3b7f63a583611d97dad0688c6b25956e22f1a93b34', 'development-f0': '83798906b4a50df4ddd41b2623a586902a52ba3f9906c3559a8c1da0a3dee09f', 'development-f1': '7bb816b40f9b8cdc6c17c20ead80b52cb17e8bfc5902f9cc7cef98caa9e3cc0c', 'development-f2': '7dd5ff2ede371ed91bb2df6ce20ab1f0af6b10f3fd9835c70e2a9252ef85cf1c', 'locked-f0': 'b3990d01fb4f837b157b41c294e9f96867ed6305263fe7d157eafcbc13a2bd36', 'locked-f1': '34a26a3fcccccfaa61445bfa7c91fe3a6753978b6525f0b008449ae50a6223da', 'locked-f2': 'c2864f8ce7feb8294109c0de5392bc48e5f22ab028a78046ad2a7afe20c18030'}}


def assets_root(root=None):
    if root is not None:
        return Path(root)
    if os.environ.get(ASSETS_ENV):
        return Path(os.environ[ASSETS_ENV])
    return Path(__file__).resolve().parents[3] / 'runs/assets/uci-online-retail-v015'


def registry():
    situations = []
    for pool in ('train', 'development', 'locked'):
        for fact in range(3):
            for task in TASKS:
                active = {'implement': ['implementer'], 'review': ['reviewer'],
                          'pair': ['provider', 'implementer'], 'chain': list(ROLES)}[task]
                limit = {'provider': 6, 'implementer': 12, 'reviewer': 15}
                if task == 'implement':
                    limit['implementer'] = 10
                if task == 'review':
                    limit['reviewer'] = 9
                situations.append({
                    'version': VERSION, 'case_id': f'uci-{pool}-f{fact}-{task}', 'pool': pool,
                    'split': pool, 'task': task, 'fact_position': fact, 'slice_id': f'{pool}-f{fact}',
                    'family': 'uci-online-retail-352', 'case_share': 0.25, 'active_roles': active,
                    'role_decision_limits': {r: limit[r] for r in active},
                    'business_facts': {'period': f'UCI-{pool}-f{fact}', 'edition': 'approved',
                                       'start_inclusive': '2010-12-01 00:00:00',
                                       'end_exclusive': '2011-07-01 00:00:00' if fact == 2 else '2012-01-01 00:00:00',
                                       'invoice_mode': 'net_signed' if fact == 1 else 'sales_only',
                                       'currency': 'GBP', 'duplicates': 'retain_source_rows',
                                       'missing_customer': 'exclude', 'price_rule': 'strictly_positive',
                                       'basis_provider': 'provider'},
                    'prepared_submission': ('correct', 'wrong_count', 'wrong_amount')[fact] if task == 'review' else None,
                })
    return {'version': VERSION, 'source_family_count': 1,
            'source_relationship': 'One real UCI Online Retail family. Pools use disjoint customer identities and complete invoice entities; these are within-source usages, not independent-source test families.',
            'split_rule': 'train is parameter learning, development is model/algorithm selection, locked is within-source frozen evaluation. All derived tasks of the same slice retain its usage pool.',
            'independent_test_source_families': [], 'situations': situations}


def case_spec(case_id):
    matches = [c for c in registry()['situations'] if c['case_id'] == case_id]
    if len(matches) != 1:
        raise ValueError('Unknown frozen retail case')
    return copy.deepcopy(matches[0])


def reward_spec(case):
    return {'version': REWARD_VERSION, 'reward_id': 'retail-' + case['task'] + '-v0.15',
            'task': case['task'], 'project_id': 'TEAM', 'work_id': 'TEAM::build',
            'period': case['business_facts']['period'], 'basis_provider': 'provider',
            'active_roles': list(case['active_roles']),
            'terms': [{'term_id': n, 'weight': w, 'public_requirement': t} for n, w, t in TERMS[case['task']]],
            'preparation_credit': False,
            'credit_rule': 'Only independent real work outcomes, each once; no action-count reward. MC and RTG use this same terminal contract.',
            'unknown_rule': 'Missing immutable evidence or evaluator/service fault is unknown, not reward zero.'}


def _table(columns, rows):
    return {'columns': [{'name': n, 'type': t} for n, t in columns], 'rows': rows}


def basis(case):
    facts = {k: v for k, v in case['business_facts'].items() if k != 'basis_provider'}
    return {'tables': {'basis_meta': _table([(k, 'VARCHAR') for k in facts], [list(facts.values())])},
            'meaning': 'UCI InvoiceNo starting C (case insensitive) is a cancellation; UnitPrice is GBP per unit. sales_only excludes C invoices and nonpositive quantities; net_signed retains signed Quantity including cancellations. Both exclude nonpositive prices and missing CustomerID. Keep all original rows (no duplicate deletion), sum Quantity*UnitPrice in GBP and output rounded integer pence, count DISTINCT qualifying InvoiceNo. Retain every customer in data.customers with zeros as needed. Date interval is start inclusive/end exclusive using source local-naive timestamps.',
            'policy_origin': 'This reporting policy is an explicit simulated client contract; it is not asserted to be the original retailer policy.'}


def initial_code():
    return {'models': [{'name': 'metrics', 'sql': 'SELECT CustomerID, SUM(UnitPrice * Quantity * 100)::BIGINT AS revenue_pence, COUNT(*)::BIGINT AS invoice_count FROM retail GROUP BY CustomerID'}],
            'tests': [{'name': 'unique_customer', 'sql': 'SELECT CustomerID FROM metrics GROUP BY CustomerID HAVING COUNT(*) <> 1'}],
            'config': {'exports': ['metrics'], 'description': 'Edit this actual SQL to implement the declared adopted retail policy. Editable tests do not determine final content correctness.'}}


def witness_code(*, defect=None):
    """Private CPU feasibility program; not a training demonstration or prompt."""
    code = initial_code()
    count = 'COUNT(DISTINCT InvoiceNo)' + ('+1' if defect == 'wrong_count' else '')
    amount = 'SUM(Quantity * UnitPrice) * 100'
    final_amount = 'COALESCE(a.revenue_pence,0)' + ('+1' if defect == 'wrong_amount' else '')
    code['models'][0]['sql'] = (
        "WITH eligible AS (SELECT r.* FROM retail r CROSS JOIN basis_meta b WHERE b.edition='approved' "
        "AND r.InvoiceDate>=CAST(b.start_inclusive AS TIMESTAMP) AND r.InvoiceDate<CAST(b.end_exclusive AS TIMESTAMP) "
        "AND r.CustomerID IS NOT NULL AND r.UnitPrice>0 AND (b.invoice_mode='net_signed' OR "
        "(UPPER(SUBSTR(r.InvoiceNo,1,1))<>'C' AND r.Quantity>0))), a AS (SELECT CustomerID,"
        + '(' + amount + ')::BIGINT AS revenue_pence,(' + count + ')::BIGINT AS invoice_count FROM eligible GROUP BY CustomerID) '
        'SELECT c.CustomerID, (' + final_amount + ')::BIGINT AS revenue_pence, COALESCE(a.invoice_count,0)::BIGINT AS invoice_count '
        'FROM customers c LEFT JOIN a ON c.CustomerID=a.CustomerID ORDER BY c.CustomerID'
    )
    return code


def _load_slice(case, root):
    root = assets_root(root)
    manifest = read_json(root / 'manifest.json')
    declared = next(row for row in manifest['slices'] if row['slice_id'] == case['slice_id'])
    if manifest['xlsx']['sha256'] != SOURCE_PIN['xlsx_sha256'] or declared['sha256'] != SOURCE_PIN['slices'][case['slice_id']]:
        raise ValueError('Runtime asset manifest differs from source-controlled source pins')
    path = root / declared['path']
    if digest(path.read_bytes()) != declared['sha256']:
        raise ValueError('Frozen UCI slice content changed')
    data = read_json(path)
    if data['source_xlsx_sha256'] != manifest['xlsx']['sha256']:
        raise ValueError('Slice source identity differs from manifest')
    return data, manifest, declared


def package(case, *, source_root=None):
    data, manifest, declared = _load_slice(case, source_root)
    pkg = team_package()
    objects = {o['alias']: o for o in pkg['objects']}
    columns = [(n, t) for n, t in zip(data['fields'], ['VARCHAR', 'VARCHAR', 'VARCHAR', 'BIGINT', 'TIMESTAMP', 'DECIMAL(18,2)', 'VARCHAR', 'VARCHAR', 'BIGINT'])]
    objects['data']['data'] = {
        'tables': {'retail': _table(columns, data['rows']), 'customers': _table([('CustomerID', 'VARCHAR')], [[v] for v in data['customers']])},
        'source': {'dataset': 'UCI Online Retail', 'doi': manifest['doi'], 'license': manifest['license'],
                   'attribution': manifest['attribution'], 'original_sha256': manifest['xlsx']['sha256'],
                   'slice_sha256': declared['sha256'], 'original_rows_preserved': True},
        'field_definitions': {'InvoiceNo': 'Invoice identifier; leading C/c marks cancellation.', 'StockCode': 'Product identifier.',
                              'Description': 'Original product text.', 'Quantity': 'Signed units in this source row.',
                              'InvoiceDate': 'Source transaction date/time, local naive; no timezone conversion.',
                              'UnitPrice': 'GBP (sterling) per unit, exact selected source decimal.',
                              'CustomerID': 'Customer identifier.', 'Country': 'Customer country.',
                              'SourceRow': 'Original XLSX row including header offset; no synthesized transactions.'},
        'slice_boundary': 'These are complete selected invoices, not all customer history. Metrics are ONLY over this supplied slice; do not extrapolate to the whole retailer.'}
    objects['code']['data'] = initial_code()
    objects['basis']['data'] = basis(case)
    objects['audit_basis']['data'] = {**case['business_facts'], 'independent_checks': basis(case)['meaning'],
                                    'origin': 'Independently supplied simulated reporting contract; no numeric answer.'}
    work = pkg['works'][0]
    work['goal'] = 'Implement and independently review customer metrics over the supplied complete UCI invoice slice.'
    req = work['requirements']
    req['online_scope'] = reward_spec(case)
    req['reporting_period'] = case['business_facts']['period']
    req['sql_project']['kind'] = 'uci_retail'
    req['public_structure']['sql_result']['table_columns']['metrics'] = ['CustomerID', 'revenue_pence', 'invoice_count']
    req['public_format']['output'] = 'Exactly one metrics table: CustomerID (text), revenue_pence (integer GBP pence), invoice_count (integer distinct qualifying invoices); one row per data.customers, including zeros. Read applicable basis for the exact date range, cancellation/quantity, price and duplicate policy. The source is invoice lines, not a completed/pending order table. Output is for the supplied bounded slice only.'
    req['review_contract']['requirements'] = 'Read the fixed submitted code/result, actual UCI data and applicable independent audit_basis. Recompute the public policy; accept only supported work, otherwise raise a located issue with exact data/audit evidence.'
    work['deliverable_contract']['content_checks'][0].update(kind='retail_customer_metrics', period=case['business_facts']['period'])
    pkg['goal'] = work['goal']
    pkg['provenance'] = {'kind': 'reconstructed', 'source_evidence_refs': [manifest['doi'], manifest['xlsx']['sha256'], declared['sha256']],
                         'note': 'Real unmodified UCI invoice rows; simulated reporting policies, participants and collaboration. No original company approval or communication history is claimed.'}
    return pkg


def scenario(case, *, source_root=None):
    spec = scenario_spec()
    spec['scenario_id'] = case['case_id']
    spec['world']['world_id'] = 'uci-retail'
    spec['projects'] = [{'package': package(case, source_root=source_root)}]
    descriptions = dict(ROLE_TASKS)
    descriptions['implementer'] = 'Implement the customer metrics for the supplied real UCI invoice slice. Read the work contract and legal sources, adopt exact data/policy, edit the actual SQL, execute it and submit the actual code/result. Obtain missing policy through the public route. No numeric answer is supplied. Review is a separate responsibility when a reviewer is present.'
    descriptions['reviewer'] = 'Independently review the actual fixed customer metrics submission against its exact UCI rows and approved audit policy. Read exact code/result references, verify date/cancellation/quantity/GBP/invoice grain, then approve supported work or raise a located, evidenced issue. The submission may be correct or incorrect; its label is not evidence.'
    spec['roles'] = [{'role_id': r, 'actor': r, 'project': 'TEAM', 'policy': 'model', 'config': {'task': descriptions[r]}} for r in case['active_roles']]
    spec['boundary'] = {'max_opportunities': sum(case['role_decision_limits'].values()) + len(case['active_roles'])}
    validity = spec['variation']['validity_spec']
    validity['read_operations'] = ['read_object', 'read_alias', 'read_version']
    spec['variation'] = {'kind': 'structure', 'online_case': copy.deepcopy(case), 'online_reward': reward_spec(case),
                         'source_asset': {'family': 'uci-online-retail-352', 'usage_pool': case['pool'], 'slice_id': case['slice_id']},
                         'support_scope': 'Same exact prepared retail situation and current shared policy/window only; no cross-pool or cross-policy pooling.'}
    if case['task'] == 'chain':
        spec['variation']['validity_spec'] = validity
    return spec


def build_retail_case(case, root, *, assets_root=None):
    if isinstance(case, str):
        case = case_spec(case)
    case = copy.deepcopy(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Retail case differs from frozen catalog')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario(case, source_root=assets_root), root / 'world')
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
            call('implementer', 'adopt', alias=alias, **ref, policy='fixed', work_ids=['TEAM::build'])
            refs.append(ref)
        if case['task'] == 'review':
            call('implementer', 'write_object', alias='code', work_id='TEAM::build', dependencies=refs,
                 data=witness_code(defect=case['prepared_submission']))
            built = call('implementer', 'sql_build', work_id='TEAM::build', code_alias='code', output_alias='result', input_aliases=['data', 'basis'])
            if built['execution_status'] != 'success':
                raise ValueError({'prepared_sql_failed': built})
            call('implementer', 'submit', work_id='TEAM::build', artifacts=['code', 'result'])
    prefix = {'version': VERSION, 'origin': 'preparation', 'credited_to_current_actor': False,
              'case_id': case['case_id'], 'executed': bool(recorder.events), 'initial_business_state_sha256': before,
              'prepared_business_state_sha256': digest(json_bytes(initial_business_state(world))),
              'experience': recorder.snapshot(), 'independent_capture': captured, 'source_before': source, 'source_after': code_identity()}
    (root / 'preparation.json').write_bytes(json_bytes(prefix))
    (root / 'scenario.json').write_bytes(json_bytes(deployment.spec))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, reward_spec(case), prefix)
