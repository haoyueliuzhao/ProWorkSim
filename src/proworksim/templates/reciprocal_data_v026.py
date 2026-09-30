"""Small reciprocal data work over immutable UCI rows and simulated interfaces.

This carrier reuses WorldCore objects, exact adoptions, real DuckDB execution,
fixed submissions and review. The independent checker below never supplies an
answer to workers. Program witness SQL is for CPU reachability controls only.
"""

import copy
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from ..core.world import object_identity
from ..domains.executable_project import _records
from ..episode import assess_historical_episode
from ..online_rewards import _Evidence, _ref
from ..scenarios import SCENARIO_VERSION, build_scenario, initial_business_state, save_deployment
from ..storage import digest, json_bytes, read_json
from .online_work import PreparedOnlineCase
from .retail_work import SOURCE_PIN, _table

VERSION = 'reciprocal-data-v0.26'
REWARD_VERSION = 'reciprocal-data-outcomes-v0.26'
MAPPER_VERSION = 'reciprocal-data-diagnostic-path-v0.26'
PIN_PATH = Path(__file__).resolve().parents[3] / 'examples/reciprocal-data-v026/source-manifest.json'
DEFAULT_ASSETS = Path(__file__).resolve().parents[3] / 'runs/assets/uci-reciprocal-v026'
ROLES = ('maintainer', 'consumer')
WORKS = {'maintainer': 'TEAM::prepare_source', 'consumer': 'TEAM::consume'}
SOURCE_ALIASES = {'maintainer': ('raw', 'demand', 'source_contract'), 'consumer': ('m_result', 'demand')}
OWN_ALIASES = {'maintainer': ('m_code', 'm_result', 'm_query'), 'consumer': ('c_code', 'c_result', 'c_query')}
PUBLIC_REQUIREMENT = (
    'Jointly deliver and verify customer metrics for this fixed UCI slice. The consumer holds the '
    'current demand; the maintainer holds the source export contract. Both must perform actual SQL '
    'work. The maintainer selects rows under the exact demand and exports a fixed invoice view with '
    'its declared amount unit; the consumer uses that exact submitted view and its interface metadata '
    'to compute integer GBP pence and distinct invoice counts, retaining every supplied customer. '
    'The maintainer independently inspects the final consumer code/result before approval. '
    'Read, query, explain, inspect or revise when useful. No conversation order, error, minimum '
    'message count or revision is required. All interface and reporting rules are simulated contracts; '
    'the original UCI fields and rows retain their documented source meanings.'
)
ROLE_TASKS = {
    'maintainer': (
        'Own TEAM::prepare_source and m_code/m_result/m_query. Read your source_contract and '
        'the public raw data, obtain the consumer demand through the declared route, then adopt '
        'raw, demand and source_contract for your work. Write and execute a source export using '
        'm_code, submit m_code/m_result, and ensure the consumer can identify the exact fixed '
        'version. Independently inspect and read the consumer fixed c_code/c_result before '
        'approving TEAM::consume; use real issues for actual discrepancies. '
        'You control your own SQL and evidence choices; no collaboration order is prescribed.'
    ),
    'consumer': (
        'Own TEAM::consume and c_code/c_result/c_query. Read your demand and communicate its '
        'exact version to the maintainer through route demand for TEAM::prepare_source. You may '
        'inspect/query raw samples first. Obtain and inspect the maintainer fixed submission, '
        'read its exact m_code/m_result, and adopt m_result plus demand for your own work. '
        'Build customer metrics using the actual interface_meta amount_unit, run useful checks, '
        'and submit c_code/c_result for maintainer review. Handle any actual evidenced issue. '
        'A correct first product needs no manufactured repair.'
    ),
}


def registry():
    pin = read_json(PIN_PATH)
    cases = []
    for index, (prototype, mode, unit) in enumerate([
        ('demand_pair', 'sales_only', 'pence'),
        ('demand_pair', 'net_signed', 'pence'),
        ('unit_pair', 'sales_only', 'GBP'),
        ('unit_pair', 'sales_only', 'pence'),
    ]):
        material = pin['slices'][index // 2]
        cases.append({
            'version': VERSION, 'case_id': f'reciprocal-v26-{index:02d}',
            'task': 'reciprocal_data', 'prototype': prototype,
            'counterfactual_pair': index // 2, 'counterfactual_member': 'maintainer' if index < 2 else 'consumer',
            'active_roles': list(ROLES), 'role_decision_limits': {r: 24 for r in ROLES},
            'slice_id': material['slice_id'], 'material_sha256': material['sha256'],
            'family': 'uci-online-retail-352', 'pool': 'carrier_development',
            'business_facts': {'invoice_mode': mode, 'amount_unit': unit,
                               'start_inclusive': '2010-12-01 00:00:00',
                               'end_exclusive': '2012-01-01 00:00:00'},
            'model_training_eligible': False,
        })
    slots = [{'slot_id': f'c1-{i:02d}-{condition}-{repeat}', 'case_id': case['case_id'],
              'case_index': i, 'task': case['task'], 'prototype': case['prototype'],
              'condition': condition, 'repeat_index': repeat, 'seed': 202610040000 + 100*(i//2) + repeat,
              'sampling_seed': 202610040000 + 100*(i//2) + repeat}
             for repeat in range(2) for i, case in enumerate(cases)
             for condition in ('normal', 'single_pass')]
    return {'version': VERSION, 'cases': cases, 'all_cases': copy.deepcopy(cases), 'slots': slots,
            'source_family_count': 1, 'model_training_eligible': False,
            'scope': 'Four frozen carrier-development cases, not allocation support or learning evidence.'}


def case_spec(case_id):
    for case in registry()['cases']:
        if case['case_id'] == case_id:
            return copy.deepcopy(case)
    raise ValueError('Unknown frozen reciprocal carrier case')


def reward_spec(case=None):
    # Deliberately invariant: public state cannot reveal a private pair value.
    return {
        'version': REWARD_VERSION, 'reward_id': 'reciprocal-data-carrier',
        'task': 'reciprocal_data', 'project_id': 'TEAM', 'work_id': WORKS['maintainer'],
        'work_ids': list(WORKS.values()), 'active_roles': list(ROLES),
        'public_requirement': PUBLIC_REQUIREMENT, 'preparation_credit': False,
        'terms': [{'term_id': term, 'weight': weight} for term, weight in [
            ('correct_current_source_delivery', .35), ('correct_current_consumer_delivery', .35),
            ('reciprocal_consumption_and_revalidation', .30)]],
        'unknown_rule': 'Missing immutable evidence or critical evaluator/service failure is unknown, not zero.',
        'credit_rule': 'Current exact executed products and supported review only; no message-count reward.',
        'scope': 'Frozen-parameter carrier qualification only; no method support or learning effect is inferred.',
    }


def _load(case, assets_root=None):
    root = Path(assets_root or DEFAULT_ASSETS)
    pin, manifest = read_json(PIN_PATH), read_json(root / 'manifest.json')
    if pin != manifest:
        raise ValueError('Source manifest differs from the source-controlled pin')
    entry = next(s for s in manifest['slices'] if s['slice_id'] == case['slice_id'])
    path = root / entry['path']
    if digest(path.read_bytes()) != entry['sha256'] or entry['sha256'] != case['material_sha256']:
        raise ValueError('Pinned source material changed')
    data = read_json(path)
    if data['source_xlsx_sha256'] != SOURCE_PIN['xlsx_sha256']:
        raise ValueError('Source workbook identity differs')
    if entry.get('source_rows') is not None and {r[-1] for r in data['rows']} != set(entry['source_rows']):
        raise ValueError('Pinned original row selection differs')
    for field, excluded in [('customers', 'excluded_customers'), ('invoice_ids', 'excluded_invoices')]:
        if set(data[field]) & set(manifest.get(excluded, [])):
            raise ValueError('Source material overlaps an excluded prior entity')
    if {r[-1] for r in data['rows']} & set(manifest.get('excluded_source_rows', [])):
        raise ValueError('Source material overlaps excluded prior rows')
    return data, manifest, entry


def _demand(case):
    facts = case['business_facts']
    names = ('start_inclusive', 'end_exclusive', 'invoice_mode')
    return {'tables': {'demand_meta': _table([(n, 'VARCHAR') for n in names], [[facts[n] for n in names]])},
            'meaning': 'Apply the stated half-open source-local date interval. sales_only excludes InvoiceNo starting C/c and Quantity<=0; net_signed keeps signed quantities including cancellations. Both exclude missing CustomerID and UnitPrice<=0, retain source duplicate rows, and preserve all supplied customers with zeros. Final output uses integer GBP pence and counts distinct qualifying InvoiceNo.',
            'origin': 'Simulated current client demand; not original retailer policy.'}


def _source_contract(case):
    return {'tables': {'source_meta': _table([('amount_unit', 'VARCHAR')], [[case['business_facts']['amount_unit']]])},
            'meaning': 'Raw UnitPrice is always GBP per unit. Select original rows using the exact client demand, sum Quantity*UnitPrice per CustomerID+InvoiceNo, and export amount in the declared unit. GBP means unchanged GBP; pence means GBP*100. Export exactly invoice_view(CustomerID,InvoiceNo,amount), customers(CustomerID), interface_meta(amount_unit). Export amount as DOUBLE so the existing managed SQL reader can load it; this finite slice has at most two decimal places, and the consumer rounds only final GBP pence. This unit is a simulated output-interface choice, not a change of original source meaning.',
            'origin': 'Simulated source publication contract; no expected answer table.'}


def initial_code(role):
    if role not in ROLES:
        raise ValueError('Unknown reciprocal member')
    return {'models': [], 'tests': [], 'config': {'exports': [], 'description': 'Create SQL models for your visible work contract. No answer SQL or prior delivery is prepared.'}}


def witness_code(case, role):
    """Generic valid CPU reachability program, never inserted into model input."""
    if isinstance(case, str):
        case = case_spec(case)
    if role == 'maintainer':
        models = [
            {'name': 'invoice_view', 'sql': "SELECT r.CustomerID,r.InvoiceNo,CAST(SUM(r.Quantity*r.UnitPrice)*(CASE WHEN s.amount_unit='pence' THEN 100 ELSE 1 END) AS DOUBLE) AS amount FROM retail r CROSS JOIN demand_meta d CROSS JOIN source_meta s WHERE r.InvoiceDate>=CAST(d.start_inclusive AS TIMESTAMP) AND r.InvoiceDate<CAST(d.end_exclusive AS TIMESTAMP) AND r.CustomerID IS NOT NULL AND r.UnitPrice>0 AND (d.invoice_mode='net_signed' OR (UPPER(SUBSTR(r.InvoiceNo,1,1))<>'C' AND r.Quantity>0)) GROUP BY r.CustomerID,r.InvoiceNo,s.amount_unit"},
            {'name': 'customers', 'sql': 'SELECT CustomerID FROM raw_customers'},
            {'name': 'interface_meta', 'sql': 'SELECT amount_unit FROM source_meta'},
        ]
    elif role == 'consumer':
        models = [{'name': 'metrics', 'sql': "WITH totals AS (SELECT i.CustomerID,CAST(ROUND(SUM(i.amount)*(CASE WHEN m.amount_unit='GBP' THEN 100 ELSE 1 END)) AS BIGINT) AS revenue_pence,CAST(COUNT(DISTINCT i.InvoiceNo) AS BIGINT) AS invoice_count FROM invoice_view i CROSS JOIN interface_meta m CROSS JOIN demand_meta d WHERE d.invoice_mode IN ('sales_only','net_signed') GROUP BY i.CustomerID,m.amount_unit) SELECT c.CustomerID,COALESCE(t.revenue_pence,0)::BIGINT AS revenue_pence,COALESCE(t.invoice_count,0)::BIGINT AS invoice_count FROM customers c LEFT JOIN totals t ON c.CustomerID=t.CustomerID ORDER BY c.CustomerID"}]
    else:
        raise ValueError('Unknown reciprocal member')
    return {'models': models, 'tests': [], 'config': {'exports': [m['name'] for m in models], 'description': 'CPU feasibility witness only; not a model target or prompt.'}}


def package(case, *, assets_root=None):
    data, manifest, entry = _load(case, assets_root)
    participants = [*ROLES, 'operator']

    def obj(alias, owner, content, *, private=None, role='draft'):
        return {'alias': alias, 'filename': alias + '.json', 'kind': 'json', 'owner': owner,
                'readers': [private, 'operator'] if private else list(participants),
                'writers': [owner], 'deliverable_role': role, 'data': content}

    raw = {'tables': {
        'retail': _table(list(zip(data['fields'], ['VARCHAR', 'VARCHAR', 'VARCHAR', 'BIGINT', 'TIMESTAMP', 'DECIMAL(18,2)', 'VARCHAR', 'VARCHAR', 'BIGINT'])), data['rows']),
        'raw_customers': _table([('CustomerID', 'VARCHAR')], [[c] for c in data['customers']]),
    }, 'source': {'dataset': 'UCI Online Retail', 'doi': manifest['doi'], 'license': manifest['license'],
                  'attribution': manifest['attribution'], 'original_sha256': data['source_xlsx_sha256'],
                  'slice_sha256': entry['sha256'], 'original_rows_preserved': True},
           'field_definitions': {'InvoiceNo': 'Leading C/c is a cancellation.', 'UnitPrice': 'Original GBP per unit.',
                                 'Quantity': 'Signed original units.', 'InvoiceDate': 'Original source-local naive timestamp.',
                                 'SourceRow': 'Original workbook row number including header offset.'},
           'scope': 'Only these complete selected invoices; no whole-customer-history inference.'}
    objects = [obj('raw', 'operator', raw),
               obj('source_contract', 'operator', _source_contract(case), private='maintainer'),
               obj('demand', 'operator', _demand(case), private='consumer')]
    for member in ROLES:
        code, result, query = OWN_ALIASES[member]
        objects.extend([obj(code, member, initial_code(member), role='sql_code'),
                        obj(result, member, {}, role='sql_result'), obj(query, member, {})])
    works, grants = [], []
    for member in ROLES:
        code, result, query = OWN_ALIASES[member]
        local = WORKS[member].split('::')[1]
        structure = ({'invoice_view': ['CustomerID', 'InvoiceNo', 'amount'],
                      'customers': ['CustomerID'], 'interface_meta': ['amount_unit']}
                     if member == 'maintainer' else {'metrics': ['CustomerID', 'revenue_pence', 'invoice_count']})
        requirements = {
            'online_scope': reward_spec(), 'input_policies': {a: 'current_applicable' if a == 'm_result' else 'fixed' for a in SOURCE_ALIASES[member]},
            'input_versions': {a: 'v1' for a in SOURCE_ALIASES[member] if a != 'm_result'},
            'source_objects': {a: object_identity('TEAM', a) for a in SOURCE_ALIASES[member]},
            'output_alias': result,
            'sql_project': {'kind': 'reciprocal_data', 'code_alias': code, 'result_alias': result, 'query_alias': query},
            'public_structure': {'sql_result': {'required_paths': [['tables', t] for t in structure], 'table_columns': structure}},
            'public_format': {
                'source_work': 'Maintainer: read/adopt raw,demand,source_contract; build three exact exported tables. Group all eligible source rows by CustomerID+InvoiceNo. All raw_customers IDs must appear in customers. Read the private demand and source contract to select business values; public observations do not choose them.',
                'consumer_work': 'Consumer: inspect/read the current fixed maintainer submission, then adopt its exact m_result and demand. Compute metrics from invoice_view and interface_meta, convert GBP to integer pence when required, count distinct qualifying invoices, retain all customers including zeros. Never infer a unit from the task identifier.',
                'execution_dependency': 'Exported SQL relations must derive from real inputs, including through CTEs/intermediate models: invoice_view from retail+demand_meta+source_meta; customers from raw_customers; interface_meta from source_meta; consumer metrics from invoice_view+interface_meta+customers. Read/adopt receipts, unused models/tests and hardcoded answer rows alone do not establish consumption.',
                'delivery': 'Submit your own code and actual SQL result, with exact adopted sources and code dependencies. Source delivery is delivery_only; consumer delivery requires maintainer review. Editable tests and preflight are not business truth.',
                'query': 'sql_query may inspect readable raw or output tables and saves to your own query alias; queries do not submit or adopt.',
                'review': 'Maintainer must inspect the consumer fixed submission and read its exact c_code/c_result after submission, using the source and demand as evidence; approve correct work or raise an actual located issue. No error or repair is required.',
            },
        }
        works.append({'work_id': local, 'owner': member, 'goal': PUBLIC_REQUIREMENT,
                      'visible_requirements': [ROLE_TASKS[member]], 'requirements': requirements,
                      'approval_policy': 'delivery_only' if member == 'maintainer' else 'review',
                      'deliverable_contract': {'min_files': 2, 'max_files': 2, 'allowed_roles': ['sql_code', 'sql_result'],
                                               'allowed_kinds': ['json'], 'required_fields': ['tables', 'sources'],
                                               'content_checks': []}})
        grants.extend({'actor_id': member, 'power': p, 'subject': 'artifact', 'work_nodes': [local]}
                      for p in ['adopt', 'execute_sql'])
    grants.extend({'actor_id': 'maintainer', 'power': p, 'subject': 'deliverable', 'work_nodes': ['consume']}
                  for p in ['review', 'approve'])
    routes = []
    for alias, sender, recipient, work in [('demand', 'consumer', 'maintainer', 'prepare_source'),
                                           ('source_contract', 'maintainer', 'consumer', 'consume')]:
        grants.append({'actor_id': sender, 'power': 'provide', 'subject': alias, 'work_nodes': [work], 'object_ids': [alias]})
        routes.append({'route_id': alias, 'mode': 'manual', 'work_id': work, 'provider': sender,
                       'object_alias': alias, 'recipients': [recipient], 'purpose': alias, 'delay': 1})
    return {'project_id': 'TEAM', 'goal': PUBLIC_REQUIREMENT, 'participants': participants,
            'objects': objects, 'works': works, 'grants': grants, 'information_routes': routes,
            'provenance': {'kind': 'reconstructed', 'source_evidence_refs': [manifest['doi'], data['source_xlsx_sha256'], entry['sha256']],
                           'note': 'Unmodified real UCI rows; newly simulated reporting demand, export interface, roles and collaboration contract. No original company collaboration is claimed.'}}


def scenario(case, *, assets_root=None):
    return {'version': SCENARIO_VERSION, 'scenario_id': case['case_id'],
            'world': {'world_id': 'reciprocal-data', 'actors': {r: {} for r in [*ROLES, 'operator']},
                      'applications': ['files', 'sql'], 'publication_policy': 'explicit',
                      'bootstrap_grants': [{'actor_id': 'operator', 'scope': 'world', 'power': 'install_project'}]},
            'installer': 'operator', 'projects': [{'package': package(case, assets_root=assets_root)}],
            'roles': [{'role_id': r, 'actor': r, 'project': 'TEAM', 'policy': 'model', 'config': {'task': ROLE_TASKS[r]}} for r in ROLES],
            'variation': {'kind': 'structure', 'online_case': copy.deepcopy(case), 'online_reward': reward_spec(),
                          'preparation_credit': False, 'mapper_version': MAPPER_VERSION},
            'boundary': {'max_opportunities': 50}}


def build_case(case_id, root, assets_root=None):
    case = case_spec(case_id) if isinstance(case_id, str) else copy.deepcopy(case_id)
    if case != case_spec(case['case_id']):
        raise ValueError('Changed frozen reciprocal case')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario(case, assets_root=assets_root), root / 'world')
    if deployment.status != 'ready':
        raise ValueError(deployment.diagnostics)
    initial_hash = digest(json_bytes(initial_business_state(deployment.world)))
    prefix = {'version': VERSION, 'origin': 'preparation', 'credited_to_current_actor': False,
              'case_id': case['case_id'], 'executed': False,
              'initial_business_state_sha256': initial_hash, 'prepared_business_state_sha256': initial_hash,
              'experience': {'events': []}, 'independent_capture': {r: [] for r in ROLES},
              'note': 'Only package installation. No prepared SQL, policy adoption, handoff or product.'}
    (root / 'preparation.json').write_bytes(json_bytes(prefix))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, reward_spec(), prefix)


def expected_products(raw, demand, source_contract):
    """Independent decimal arithmetic from exact source bytes, not witness SQL."""
    requests = _records(demand['tables']['demand_meta'])
    units = _records(source_contract['tables']['source_meta'])
    if len(requests) != 1 or len(units) != 1:
        raise ValueError('One current demand and source interface required')
    d, unit = requests[0], units[0]['amount_unit']
    if d['invoice_mode'] not in {'sales_only', 'net_signed'} or unit not in {'GBP', 'pence'}:
        raise ValueError('Unknown simulated business or interface choice')
    money, invoice_sets = {}, {}
    for row in _records(raw['tables']['retail']):
        if (row['CustomerID'] is None or Decimal(str(row['UnitPrice'])) <= 0
                or not d['start_inclusive'] <= row['InvoiceDate'] < d['end_exclusive']):
            continue
        if d['invoice_mode'] == 'sales_only' and (row['InvoiceNo'].upper().startswith('C') or row['Quantity'] <= 0):
            continue
        key = (row['CustomerID'], row['InvoiceNo'])
        money[key] = money.get(key, Decimal(0)) + Decimal(row['Quantity']) * Decimal(str(row['UnitPrice']))
        invoice_sets.setdefault(row['CustomerID'], set()).add(row['InvoiceNo'])
    customers = _records(raw['tables']['raw_customers'])
    source = {'invoice_view': [{'CustomerID': c, 'InvoiceNo': i, 'amount': v * (100 if unit == 'pence' else 1)}
                               for (c, i), v in sorted(money.items())],
              'customers': customers, 'interface_meta': [{'amount_unit': unit}]}
    consumer = {'metrics': []}
    for row in customers:
        customer = row['CustomerID']
        total = sum((v for (c, _), v in money.items() if c == customer), Decimal(0))
        consumer['metrics'].append({'CustomerID': customer,
                                    'revenue_pence': int((total * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
                                    'invoice_count': len(invoice_sets.get(customer, set()))})
    return {'maintainer': source, 'consumer': consumer}


def _canonical_row(row):
    def scalar(v):
        if type(v) in (int, float, Decimal):
            return ('number', Decimal(str(v)))
        return (type(v).__name__, v)
    return tuple((k, scalar(v)) for k, v in sorted(row.items()))


def _matches(product, expected):
    try:
        actual = product['tables']
        columns = {'invoice_view': ['CustomerID', 'InvoiceNo', 'amount'], 'customers': ['CustomerID'],
                   'interface_meta': ['amount_unit'], 'metrics': ['CustomerID', 'revenue_pence', 'invoice_count']}
        if any([c['name'] for c in table['columns']] != columns[name] for name, table in actual.items()):
            return False
        if set(actual) != set(expected):
            return False
        return all(Counter(_canonical_row(r) for r in _records(actual[t])) ==
                   Counter(_canonical_row(r) for r in rows) for t, rows in expected.items())
    except (KeyError, TypeError, ValueError):
        return False


def execution_dependencies(role, code, product, sources):
    """Trace saved executed model SQL to input relations using DuckDB's parser.

    An unreferenced CTE, an unused model or a test does not prove that an export
    consumes its sources. This is relation dependency evidence, not a proof of
    unique causal necessity or a general SQL column-lineage analysis.
    """
    import duckdb

    required = {
        'maintainer': {
            'invoice_view': {('raw', 'retail'), ('demand', 'demand_meta'), ('source_contract', 'source_meta')},
            'customers': {('raw', 'raw_customers')},
            'interface_meta': {('source_contract', 'source_meta')},
        },
        'consumer': {'metrics': {('m_result', 'invoice_view'), ('m_result', 'interface_meta'), ('m_result', 'customers')}},
    }[role]
    lineage = {}
    for alias, document in sources.items():
        for name in document['tables']:
            key = name.casefold()
            if key in lineage:
                raise ValueError('Execution source tables have ambiguous case-insensitive names')
            lineage[key] = {(alias, name)}
    model_lineage, direct = {}, {}
    with duckdb.connect(':memory:', config={'enable_external_access': False}) as connection:
        for model in code['models']:
            name = model['name']
            sql = product.get('files', {}).get('models/' + name + '.sql')
            if not isinstance(sql, str) or sql != model['sql'].rstrip().rstrip(';'):
                raise ValueError('Saved executed SQL differs from the fixed code model')
            try:
                tables = connection.get_table_names(sql)
            except duckdb.Error as error:
                raise ValueError('Executed SQL dependency analysis unavailable: ' + str(error)) from error
            references = {table.casefold() for table in tables}
            if name.casefold() in lineage or references - lineage.keys():
                raise ValueError('Executed model relation cannot be traced to earlier models and exact inputs')
            traced = set().union(*(lineage[table] for table in references))
            lineage[name.casefold()] = traced
            model_lineage[name] = traced
            direct[name] = sorted(tables)
    exports = code.get('config', {}).get('exports', [m['name'] for m in code['models']])
    actual = {name: model_lineage.get(name, set()) for name in exports}
    passed = all(name in actual and needs <= actual[name] for name, needs in required.items())
    return {'passed': passed, 'parser': 'duckdb.get_table_names', 'duckdb_version': duckdb.__version__,
            'direct_model_relations': direct,
            'export_input_relations': {name: [list(v) for v in sorted(values)] for name, values in actual.items()},
            'required_input_relations': {name: [list(v) for v in sorted(values)] for name, values in required.items()},
            'scope': 'Executed SQL relation dependencies, not unique necessity or hidden model understanding.'}


def _calls(e, role, action):
    return [v for v in e.successful if v['worker_id'] == role and v['payload']['action'] == action]


def _submission(e, role):
    item = e.state['work_items'][WORKS[role]]
    if not item['submissions']:
        return None
    sub = item['submissions'][-1]
    if (sub.get('review') or {}).get('decision') == 'withdrawn':
        return None
    return sub


def _fixed_build(e, role, expected, required_sources):
    sub = _submission(e, role)
    if sub is None:
        return None
    code_alias, result_alias, _ = OWN_ALIASES[role]
    aliases = e.aliases
    fixed = sub['artifact_versions']
    if set(fixed) != {aliases[code_alias], aliases[result_alias]}:
        return None
    code_ref, result_ref = (aliases[code_alias], fixed[aliases[code_alias]]), (aliases[result_alias], fixed[aliases[result_alias]])
    if any(e.state['artifacts'][oid]['current_version'] != vid for oid, vid in [code_ref, result_ref]):
        return None
    start_subs = e.start['work_items'][WORKS[role]]['submissions']
    if sub['submission_id'] in {s['submission_id'] for s in start_subs}:
        return None
    provenance = e.state['artifacts'][result_ref[0]]['versions'][result_ref[1]].get('execution_provenance', {})
    adopted = {b['alias']: (b['object_id'], b['version_id']) for b in sub.get('adoption_snapshot', {}).values()
               if b.get('work_id') == WORKS[role] and b.get('requirement_version') == e.state['work_items'][WORKS[role]]['requirement_version']}
    sources = {alias: _ref(ref) for alias, ref in provenance.get('source_references', {}).items()}
    if (provenance.get('kind') != 'sql_build' or provenance.get('status') != 'success'
            or provenance.get('work_id') != WORKS[role] or _ref(provenance.get('code_reference')) != code_ref
            or sources != required_sources or adopted != required_sources):
        return None
    product = e.document(result_ref)
    if ({k: _ref(v) for k, v in product.get('sources', {}).items()} != required_sources
            or not _matches(product, expected)):
        return None
    dependency = execution_dependencies(role, e.document(code_ref), product,
                                        {a: e.document(ref) for a, ref in required_sources.items()})
    if not dependency['passed']:
        return None
    builds = [c for c in _calls(e, role, 'sql_build') if _ref(c['payload']['response']['result'].get('reference')) == result_ref]
    submits = [c for c in _calls(e, role, 'submit') if c['payload']['response']['result'].get('submission_id') == sub['submission_id']]
    if not builds or not submits or builds[-1]['sequence'] >= submits[-1]['sequence']:
        return None
    build = builds[-1]
    # An adoption receipt is insufficient: every source must have entered the
    # exact consuming model request (or explicit direct-return rule witness).
    reads = {a: e.read_before(role, ref, build['sequence']) for a, ref in required_sources.items()}
    if not all(reads.values()):
        return None
    return {'submission_id': sub['submission_id'], 'code_reference': list(code_ref),
            'result_reference': list(result_ref), 'source_references': {a: list(r) for a, r in required_sources.items()},
            'build_sequence': build['sequence'], 'submit_sequence': submits[-1]['sequence'],
            'execution_dependency': dependency,
            'input_read_sequences': {a: [v['sequence'] for v in rows] for a, rows in reads.items()}}


def assess_episode(episode_path, spec=None):
    """Read only immutable current-episode receipts and independent source truth."""
    root = Path(episode_path)
    if root.name == 'manifest.json':
        root = root.parent
    report = {'version': REWARD_VERSION, 'eligible': False, 'reward': None, 'completed': False,
              'components': [], 'work_components': {}, 'exclusions': [], 'preparation_credited': False,
              'record_trust': 'unknown', 'independent_assessability': 'unknown',
              'mapper': {'version': MAPPER_VERSION, 'class_id': None, 'eligible': False,
                         'scope': 'Carrier diagnosis only; no allocation method support inferred.'}}
    try:
        manifest = read_json(root / 'manifest.json')
        case = case_spec(manifest['scenario']['variation']['online_case']['case_id'])
        expected_spec = reward_spec(case)
        if (manifest.get('status') != 'closed' or manifest['scenario']['variation']['online_case'] != case
                or manifest['scenario']['variation']['online_reward'] != expected_spec
                or spec is not None and spec != expected_spec):
            raise ValueError('Episode differs from frozen reciprocal contract')
        history = assess_historical_episode(root)
        if history.get('assessment_execution', {}).get('status') != 'complete':
            raise ValueError('Immutable historical evidence unavailable')
        e = _Evidence(root, expected_spec, history)
        for work in WORKS.values():
            if e.start['work_items'][work]['requirements'].get('online_scope') != expected_spec:
                raise ValueError('Public world scope differs from fixed carrier contract')
        critical = {'model_service_error', 'environment_error', 'binding_mismatch', 'model_usage_missing'}
        if any(v.get('kind') in {'interface_exception', 'interface_error', 'model_service_error', 'binding_mismatch'}
               or v.get('status') in critical or (isinstance(v.get('payload'), dict) and v['payload'].get('status') in critical) for v in e.events):
            raise ValueError('Critical runtime failure prevents trusted work outcome')
        original = {a: (e.aliases[a], 'v1') for a in ('raw', 'demand', 'source_contract')}
        docs = {a: e.document(ref) for a, ref in original.items()}
        if docs['demand'] != _demand(case) or docs['source_contract'] != _source_contract(case):
            raise ValueError('Private business evidence differs from frozen declared case')
        pin = read_json(PIN_PATH)
        entry = next(row for row in pin['slices'] if row['slice_id'] == case['slice_id'])
        source_slice = {
            'slice_id': case['slice_id'],
            'fields': [c['name'] for c in docs['raw']['tables']['retail']['columns']],
            'rows': docs['raw']['tables']['retail']['rows'],
            'customers': [r['CustomerID'] for r in _records(docs['raw']['tables']['raw_customers'])],
            'invoice_ids': entry['invoice_ids'], 'complete_invoice_rows': entry['complete_invoice_rows'],
            'source_xlsx_sha256': docs['raw']['source']['original_sha256'],
        }
        if (docs['raw']['source']['slice_sha256'] != case['material_sha256']
                or digest(json_bytes(source_slice)) != case['material_sha256']):
            raise ValueError('Actual source values differ from frozen original material')
        expected = expected_products(**docs)
        maintainer = _fixed_build(e, 'maintainer', expected['maintainer'], original)
        m_sub = _submission(e, 'maintainer')
        c_sources = {'demand': original['demand']}
        if m_sub is not None and e.aliases['m_result'] in m_sub['artifact_versions']:
            c_sources['m_result'] = (e.aliases['m_result'], m_sub['artifact_versions'][e.aliases['m_result']])
        consumer = _fixed_build(e, 'consumer', expected['consumer'], c_sources) if len(c_sources) == 2 else None
        consumer_fixed_inspection = None
        if maintainer and consumer and maintainer['submit_sequence'] < consumer['build_sequence']:
            inspections = [v for v in _calls(e, 'consumer', 'inspect_submission')
                           if v['payload']['arguments'].get('submission_id') == maintainer['submission_id']
                           and maintainer['submit_sequence'] < v['sequence'] < consumer['build_sequence']]
            reads = {name: e.read_before('consumer', tuple(maintainer[name]), consumer['build_sequence'])
                     for name in ('code_reference', 'result_reference')}
            reads = {name: [v for v in rows if v['sequence'] > maintainer['submit_sequence']] for name, rows in reads.items()}
            if inspections and all(reads.values()):
                consumer_fixed_inspection = {'inspect_sequence': inspections[-1]['sequence'],
                                             'read_sequences': {a: [v['sequence'] for v in vs] for a, vs in reads.items()}}
        closure = None
        final_consumer = _submission(e, 'consumer')
        if consumer and final_consumer and (final_consumer.get('review') or {}).get('decision') == 'accepted':
            for approval in _calls(e, 'maintainer', 'approve'):
                if approval['payload']['arguments'].get('submission_id') != consumer['submission_id']:
                    continue
                before = approval['sequence']
                inspections = [v for v in _calls(e, 'maintainer', 'inspect_submission')
                               if v['payload']['arguments'].get('submission_id') == consumer['submission_id']
                               and consumer['submit_sequence'] < v['sequence'] < before]
                reads = {name: e.read_before('maintainer', tuple(consumer[name]), before)
                         for name in ('code_reference', 'result_reference')}
                reads = {name: [v for v in rows if v['sequence'] > consumer['submit_sequence']] for name, rows in reads.items()}
                own_evidence = all(e.read_before('maintainer', ref, before) for ref in original.values())
                if inspections and all(reads.values()) and own_evidence:
                    closure = {'approve_sequence': before, 'inspect_sequence': inspections[-1]['sequence'],
                               'read_sequences': {a: [v['sequence'] for v in rows] for a, rows in reads.items()}}
                    break
        checks = {'correct_current_source_delivery': bool(maintainer),
                  'correct_current_consumer_delivery': bool(consumer and consumer_fixed_inspection),
                  'reciprocal_consumption_and_revalidation': bool(maintainer and consumer and consumer_fixed_inspection and closure)}
        components = [{**term, 'achieved': checks[term['term_id']],
                       'score': term['weight'] if checks[term['term_id']] else 0.0} for term in expected_spec['terms']]
        completed = all(checks.values())
        report.update(case_id=case['case_id'], eligible=True, reward=round(sum(c['score'] for c in components), 10),
                      completed=completed, components=components, record_trust='verified_world_receipts_and_fixed_history',
                      independent_assessability='known', termination=manifest['termination'],
                      facts={'maintainer_current_fixed_build': maintainer, 'consumer_current_fixed_build': consumer,
                             'consumer_fixed_inspection': consumer_fixed_inspection, 'maintainer_revalidation': closure,
                             'communication_action_count': sum(v['payload']['action'] in {'request_information', 'handoff_information'} for v in e.successful),
                             'message_count_used_for_completion': False},
                      work_components={'business_product': bool(maintainer and consumer), 'full_responsibility': completed},
                      episode_manifest_sha256=digest((root / 'manifest.json').read_bytes()),
                      current_actor_tool_calls=len(e.calls), training_projection_available=False)
    except (OSError, KeyError, TypeError, ValueError, StopIteration) as error:
        report['exclusions'].append({'type': type(error).__name__, 'reason': str(error)})
    return report
