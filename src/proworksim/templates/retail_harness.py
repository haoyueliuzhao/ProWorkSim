"""Entity-disjoint UCI development situations for a separately frozen harness.

The reward and business contract deliberately reuse v0.15. No v0.15 registry,
asset, training window, selection score or software evaluation is changed.
"""
import copy
import os
from pathlib import Path

from ..audit import code_identity
from ..experience import ExperienceRecorder, capture_port
from ..scenarios import build_scenario, initial_business_state, save_deployment
from ..storage import digest, json_bytes, read_json
from .decision_team import ROLES, ROLE_TASKS, package as team_package, scenario_spec
from .online_work import PreparedOnlineCase
from .retail_work import _table, basis, initial_code, reward_spec, witness_code

VERSION = 'retail-harness-development-v0.16'
ASSETS_ENV = 'PROWORKSIM_RETAIL_HARNESS_ASSETS'
PIN_PATH = Path(__file__).resolve().parents[3] / 'examples/retail-harness-v16/source-manifest.json'


def assets_root(root=None):
    return Path(root or os.environ.get(ASSETS_ENV) or
                Path(__file__).resolve().parents[3] / 'runs/assets/uci-retail-harness-v016')


def registry():
    situations = []
    tasks = ('implement', 'implement', 'review', 'review', 'pair', 'chain')
    for fact, task in enumerate(tasks):
        active = {'implement': ['implementer'], 'review': ['reviewer'],
                  'pair': ['provider', 'implementer'], 'chain': list(ROLES)}[task]
        limits = {'provider': 6, 'implementer': 12, 'reviewer': 15}
        if task == 'implement':
            limits['implementer'] = 10
        if task == 'review':
            limits['reviewer'] = 9
        situations.append({
            'version': VERSION, 'case_id': f'uci-harness-f{fact}-{task}',
            'pool': 'harness_development', 'split': 'harness_development',
            'task': task, 'fact_position': fact, 'slice_id': f'harness-development-f{fact}',
            'family': 'uci-online-retail-352', 'case_share': 1 / 6,
            'active_roles': active, 'role_decision_limits': {r: limits[r] for r in active},
            'business_facts': {'period': f'UCI-harness-f{fact}', 'edition': 'approved',
                               'start_inclusive': '2010-12-01 00:00:00',
                               'end_exclusive': '2011-07-01 00:00:00' if fact in (1, 5) else '2012-01-01 00:00:00',
                               'invoice_mode': 'net_signed' if fact in (1, 2, 4) else 'sales_only',
                               'currency': 'GBP', 'duplicates': 'retain_source_rows',
                               'missing_customer': 'exclude', 'price_rule': 'strictly_positive',
                               'basis_provider': 'provider'},
            'prepared_submission': ('correct' if fact == 2 else 'wrong_count') if task == 'review' else None,
        })
    return {'version': VERSION, 'source_family_count': 1,
            'source_relationship': 'Six new disjoint-entity UCI development slices, one existing source family; not new independent-source or locked evaluation.',
            'split_rule': 'Harness development only, excludes every v0.15 train/development/locked customer and invoice. Never use the Marshmallow locked requirement for harness tuning.',
            'independent_test_source_families': [], 'situations': situations}


def case_spec(case_id):
    matches = [c for c in registry()['situations'] if c['case_id'] == case_id]
    if len(matches) != 1:
        raise ValueError('Unknown independent harness development case')
    return copy.deepcopy(matches[0])


def _load_slice(case, root):
    root = assets_root(root)
    pin, manifest = read_json(PIN_PATH), read_json(root / 'manifest.json')
    if digest(json_bytes(manifest)) != digest(json_bytes(pin)):
        raise ValueError('Harness source manifest differs from source-controlled pin')
    declared = next(s for s in manifest['slices'] if s['slice_id'] == case['slice_id'])
    path = root / declared['path']
    if digest(path.read_bytes()) != declared['sha256']:
        raise ValueError('Frozen harness development slice changed')
    data = read_json(path)
    if data['source_xlsx_sha256'] != manifest['xlsx']['sha256']:
        raise ValueError('Harness slice source identity changed')
    if set(data['customers']) & set(manifest['excluded_customers']) or set(data['invoice_ids']) & set(manifest['excluded_invoices']):
        raise ValueError('Harness development crossed a frozen v0.15 entity boundary')
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
    spec['world']['world_id'] = 'uci-retail-harness-development'
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


def build_harness_case(case, root, *, assets_root=None):
    if isinstance(case, str):
        case = case_spec(case)
    case = copy.deepcopy(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Harness case differs from its independent frozen catalog')
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
        response = ports[actor].call(tool, request_key=f'harness-retail-preparation-{case["case_id"]}-{actor}-{len(recorder.events)}', **arguments)
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
