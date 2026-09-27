"""Independent finite retail branch quality and exact integration fidelity.

This evaluator never executes model SQL. Actual execution and exact submitted
source bindings are checked by work_product before the Decimal/row comparisons.
"""
import copy
from collections import Counter

from ..storage import digest, json_bytes
from .executable_project import _canonical, _records
from .retail_work import expected_metrics

CHECK_KIND = 'retail_project_product'


def validate_check(spec):
    result = copy.deepcopy(spec)
    if set(result) != {'kind', 'role', 'path', 'sources', 'period', 'project_kind', 'policy_sha256s'}:
        raise ValueError('Finite retail project contract fields must be explicit')
    project = result['project_kind']
    aliases = {'metrics', 'analysis', 'basis'} if project == 'P3' else {'data', 'basis'}
    if project not in {'P1', 'P2', 'P3'} or result['path'] != ['tables'] or result['role'] != 'sql_result':
        raise ValueError('Unsupported retail project product')
    if not isinstance(result['period'], str) or not result['period']:
        raise ValueError('Reporting period required')
    sources = result['sources']
    if not isinstance(sources, list) or len(sources) != len(aliases) or {s.get('alias') for s in sources} != aliases:
        raise ValueError('Exact declared sources required')
    if any(set(s) != {'alias', 'reference_path'} or s['reference_path'] != ['sources', s['alias']] for s in sources):
        raise ValueError('Source paths must refer to actual SQL inputs')
    hashes = result['policy_sha256s']
    if not isinstance(hashes, list) or len(hashes) != 2 or any(not isinstance(h, str) or len(h) != 64 for h in hashes):
        raise ValueError('Both publicly declared reporting contract hashes required')
    return result


def validate_fixed_inputs(state, item, submission, selected, spec):
    if spec['project_kind'] != 'P3':
        return
    product = next(e for e in selected if e['data'] is not None and 'tables' in e['data'])
    metadata = product['artifact']['versions'][product['version_id']]
    built_at = metadata['logical_time']
    for alias, project in (('metrics', 'P1'), ('analysis', 'P2')):
        ref = product['data']['sources'][alias]
        matches = [(work, sub) for work in state['work_items'].values() if work['project_id'] == project
                   for sub in work['submissions'] if sub['at'] <= built_at
                   and sub['artifact_versions'].get(ref['object_id']) == ref['version_id']]
        if not matches:
            raise ValueError('P3 input was not an actual fixed upstream submission before its SQL build: ' + alias)


def expected_integration(metrics, analysis):
    left = {r['CustomerID']: r for r in metrics}
    right = {r['CustomerID']: r for r in analysis}
    if len(left) != len(metrics) or len(right) != len(analysis):
        raise ValueError('Upstream customer keys are not unique')
    result = []
    for customer in sorted(set(left) | set(right)):
        m, a = left.get(customer), right.get(customer)
        result.append({'CustomerID': customer,
                       'metrics_pence': m['revenue_pence'] if m else None,
                       'analysis_pence': a['revenue_pence'] if a else None,
                       'difference_pence': m['revenue_pence'] - a['revenue_pence'] if m and a else None,
                       'metrics_invoices': m['invoice_count'] if m else None,
                       'analysis_invoices': a['invoice_count'] if a else None,
                       'invoice_difference': m['invoice_count'] - a['invoice_count'] if m and a else None})
    return result


def evaluate_check(spec, data, load_source):
    try:
        policy = load_source('basis')
        rules = _records(policy['tables']['basis_meta'])
        if digest(json_bytes(policy)) not in spec['policy_sha256s'] or len(rules) != 1 or rules[0]['period'] != spec['period']:
            return {'passed': False, 'reason': 'unregistered_or_inapplicable_client_contract'}
        project = spec['project_kind']
        table = {'P1': 'metrics', 'P2': 'customer_analysis', 'P3': 'integration'}[project]
        if project == 'P3':
            expected = expected_integration(_records(load_source('metrics')['tables']['metrics']),
                                            _records(load_source('analysis')['tables']['customer_analysis']))
        else:
            original = load_source('data')['tables']
            expected = expected_metrics(_records(original['retail']), _records(original['customers']), rules[0])
            if project == 'P2':
                expected = [{**r, 'segment': 'positive' if r['revenue_pence'] > 0 else 'negative' if r['revenue_pence'] < 0 else 'zero'} for r in expected]
        actual = _records(data['tables'][table])
        correct = set(data['tables']) == {table} and Counter(_canonical(r) for r in actual) == Counter(_canonical(r) for r in expected)
        return {'passed': correct, 'reason': 'actual_upstream_row_fidelity' if project == 'P3' else 'independent_decimal_branch_quality',
                'project_kind': project, 'expected_rows': len(expected), 'actual_rows': len(actual),
                'scope': 'Integration fidelity does not certify upstream correctness' if project == 'P3' else 'Actual adopted reporting policy and original invoice lines',
                'editable_tests_used_as_truth': False}
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        return {'passed': False, 'reason': 'invalid_project_product_or_source', 'diagnostic': str(error)}
