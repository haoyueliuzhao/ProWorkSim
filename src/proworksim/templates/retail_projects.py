"""Bounded P0 -> P1/P2 -> P3 relationships on the harness development slice.

This template is separate from all six H1 situations and all frozen v0.15 jobs.
It declares contracts and source relationships, never computed downstream work.
"""
import copy

from ..core.world import object_identity
from ..scenarios import SCENARIO_VERSION
from .retail_harness import case_spec, package as retail_package
from .retail_work import basis, initial_code

VERSION = 'retail-project-relations-v0.16'
ACTORS = {'P0': 'source_steward', 'P1': 'metrics_engineer', 'P2': 'customer_analyst', 'P3': 'integrator'}
SOURCES = {'P0': {}, 'P1': {'data': ('P0', 'data'), 'basis': ('P2', 'request')},
           'P2': {'data': ('P0', 'data'), 'basis': ('P2', 'request')},
           'P3': {'metrics': ('P1', 'result'), 'analysis': ('P2', 'result'), 'basis': ('P2', 'request')}}
GOALS = {
    'P0': 'Read and publish the actual supplied complete UCI invoices and field definitions, with the supplied limitation note. Do not synthesize transactions or compute downstream outcomes.',
    'P1': 'Implement customer metrics from the exact published data and P2 reporting contract. Preserve every supplied customer, exact GBP pence and DISTINCT qualifying invoices. Publish actual SQL output. Consume later contract editions explicitly; publication never updates an adoption or builds a result for you.',
    'P2': 'Publish the initial usable customer-grain reporting contract. In parallel with P1, independently compute customer_analysis(CustomerID,revenue_pence,invoice_count,segment) from the published P0 rows and your exact published contract. segment is positive, zero, or negative according to revenue_pence. A later request edition may change the date scope and cancellation treatment; explicitly rebuild and republish analysis.',
    'P3': 'Consume the exact published P1 metrics, P2 customer analysis, and reporting contract. Build integration(CustomerID,metrics_pence,analysis_pence,difference_pence,metrics_invoices,analysis_invoices,invoice_difference). FULL OUTER JOIN by CustomerID, keeping missing counterparts NULL; never coalesce missing sources into agreement. Deliver only when all customers, amounts, counts and policy versions agree.',
}


def request(edition=1):
    case = case_spec('uci-harness-f0-implement')
    if edition == 2:
        case['business_facts']['invoice_mode'] = 'net_signed'
        case['business_facts']['end_exclusive'] = '2011-07-01 00:00:00'
    elif edition != 1:
        raise ValueError('Only the two declared simulated contract editions exist')
    result = basis(case)
    result['request_edition'] = edition
    result['grain'] = 'one row per supplied CustomerID, zero customers retained'
    result['feedback_reason'] = ('Initial usable annual sales contract' if edition == 1 else
                                 'Analyst requests a first-half signed-net view; this is a new simulated client requirement, not a claim about the retailer.')
    return result


def package(project_id):
    owner = ACTORS[project_id]
    participants = [owner, 'operator']
    source_pkg = retail_package(case_spec('uci-harness-f0-implement'))
    source_objects = {o['alias']: o for o in source_pkg['objects']}

    def obj(alias, data, role='draft'):
        return {'alias': alias, 'filename': alias + '.json', 'kind': 'json', 'owner': owner,
                'readers': participants, 'deliverable_role': role, 'data': copy.deepcopy(data)}

    if project_id == 'P0':
        objects = [obj('data', source_objects['data']['data'], 'source'),
                   obj('release_note', {'scope': 'Complete selected invoices only; not full customer history.',
                                        'unresolved': ['Original timezone unspecified; timestamps remain local-naive.',
                                                       'Reporting policies are simulated, not retailer approvals.']}, 'source_note')]
        delivery = {'min_files': 2, 'max_files': 2, 'allowed_kinds': ['json'],
                    'allowed_roles': ['source', 'source_note']}
        requirements = {'source_objects': {}, 'input_policy': 'fixed'}
    else:
        code = initial_code() if project_id == 'P1' else {
            'models': [{'name': 'customer_analysis' if project_id == 'P2' else 'integration',
                        'sql': 'SELECT missing_contract_column FROM missing_input'}],
            'tests': [], 'config': {'exports': ['customer_analysis' if project_id == 'P2' else 'integration']}}
        objects = [obj('code', code, 'sql_code'), obj('result', {}, 'sql_result'), obj('query', {})]
        if project_id == 'P2':
            objects.append(obj('request', request()))
        delivery = {'min_files': 2, 'max_files': 2, 'allowed_kinds': ['json'],
                    'allowed_roles': ['sql_code', 'sql_result'], 'required_fields': ['tables', 'sources']}
        if project_id == 'P1':
            delivery['content_checks'] = [{
                'kind': 'retail_customer_metrics', 'role': 'sql_result', 'path': ['tables'],
                'period': 'UCI-harness-f0',
                'sources': [{'alias': a, 'reference_path': ['sources', a]} for a in ('data', 'basis')]}]
        requirements = {
            'source_objects': {alias: object_identity(pid, alias_) for alias, (pid, alias_) in SOURCES[project_id].items()},
            'input_policy': 'current_published', 'output_alias': 'result',
            'sql_project': {'kind': 'retail_project_relations', 'code_alias': 'code',
                            'result_alias': 'result', 'query_alias': 'query'},
            'reporting_period': 'UCI-harness-f0',
        }
    rules = []
    if project_id in {'P1', 'P2'}:
        rules.append({'rule_id': 'reporting-contract-change',
                      'source': {'object_id': object_identity('P2', 'request'), 'source_project': 'P2'},
                      'work_nodes': ['build'], 'when': ['after_read', 'output_ready', 'pending'],
                      'effect': 'revise', 'actor': 'operator', 'updates': {'goal': GOALS[project_id]}})
    if project_id == 'P3':
        for alias, (pid, artifact) in SOURCES['P3'].items():
            rules.append({'rule_id': 'published-' + alias, 'source': {'object_id': object_identity(pid, artifact), 'source_project': pid},
                          'work_nodes': ['build'], 'when': ['after_read', 'output_ready', 'pending'],
                          'effect': 'revise', 'actor': 'operator', 'updates': {'goal': GOALS['P3']}})
    return {'project_id': project_id, 'participants': participants, 'goal': GOALS[project_id],
            'objects': objects,
            'works': [{'work_id': 'build', 'owner': owner, 'approval_policy': 'delivery_only',
                       'goal': GOALS[project_id], 'requirements': requirements,
                       'visible_requirements': ['Publication and sharing are separate. Reading is not adoption. Every SQL result must come from an actual build; no project computes work for another.'],
                       'deliverable_contract': delivery}],
            'grants': ([{'actor_id': owner, 'power': power, 'subject': 'artifact', 'work_nodes': ['build']}
                        for power in ('adopt', 'execute_sql')] +
                       [{'actor_id': owner, 'power': power, 'subject': 'artifact'} for power in ('share', 'publish')] +
                       [{'actor_id': 'operator', 'power': 'revise_requirement', 'subject': 'requirements', 'work_nodes': ['build']}]),
            'maintenance_rules': rules,
            'provenance': {'kind': 'reconstructed', 'source_evidence_refs': source_pkg['provenance']['source_evidence_refs'],
                           'note': 'Same UCI development source. Four project roles, parallel responsibilities and feedback contract are simulated. No automatic downstream solution.'}}


def scenario_spec():
    return {'version': SCENARIO_VERSION, 'scenario_id': VERSION,
            'world': {'world_id': VERSION, 'actors': {'operator': {}} | {a: {} for a in ACTORS.values()},
                      'applications': ['files', 'sql'], 'publication_policy': 'explicit',
                      'bootstrap_grants': [{'actor_id': 'operator', 'power': 'install_project', 'scope': 'world'}]},
            'installer': 'operator', 'projects': [{'package': package(pid)} for pid in ('P0', 'P2', 'P1', 'P3')],
            'roles': [{'role_id': pid, 'actor': ACTORS[pid], 'project': pid, 'policy': 'model',
                       'config': {'task': GOALS[pid]}} for pid in ACTORS],
            'setup': [], 'events': [], 'start': {'kind': 'initial'}, 'boundary': {'max_opportunities': 180},
            'variation': {'kind': 'structure', 'usage': 'Separate CPU project-relationship feasibility witness; not H1 or online learning.'}}
