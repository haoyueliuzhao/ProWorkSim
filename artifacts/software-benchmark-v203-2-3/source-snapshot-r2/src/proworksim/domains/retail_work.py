"""Independent Decimal evaluation of a declared UCI retail metric contract."""
import copy
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from .executable_project import _canonical, _records

CHECK_KIND = 'retail_customer_metrics'


def validate_check(spec):
    result = copy.deepcopy(spec)
    if set(result) - {'kind', 'role', 'path', 'sources', 'period'} or result.get('path') != ['tables']:
        raise ValueError('Retail check requires its public tables contract')
    if not isinstance(result.get('period'), str) or not result['period']:
        raise ValueError('Retail work needs an explicit reporting period label')
    sources = result.get('sources')
    if not isinstance(sources, list) or len(sources) != 2 or {s.get('alias') for s in sources} != {'data', 'basis'}:
        raise ValueError('Retail SQL requires exact original data and adopted policy')
    if any(set(s) != {'alias', 'reference_path'} or s['reference_path'] != ['sources', s['alias']] for s in sources):
        raise ValueError('Retail source paths must identify declared aliases')
    return result


def expected_metrics(rows, customers, rules):
    """No SQL, result fixture or editable test is used as evaluation truth."""
    if rules.get('edition') != 'approved' or rules.get('invoice_mode') not in {'sales_only', 'net_signed'}:
        raise ValueError('Unapproved/unknown retail policy')
    if rules.get('currency') != 'GBP' or rules.get('duplicates') != 'retain_source_rows':
        raise ValueError('Unsupported public currency or duplicate policy')
    if rules.get('missing_customer') != 'exclude' or rules.get('price_rule') != 'strictly_positive':
        raise ValueError('Unsupported public missing customer or price rule')
    expected = []
    for customer in customers:
        cid = customer['CustomerID']
        eligible = [r for r in rows if r['CustomerID'] is not None and r['CustomerID'] == cid
                    and rules['start_inclusive'] <= r['InvoiceDate'] < rules['end_exclusive']
                    and Decimal(str(r['UnitPrice'])) > 0
                    and (rules['invoice_mode'] == 'net_signed'
                         or (not r['InvoiceNo'].upper().startswith('C') and r['Quantity'] > 0))]
        amount = sum((Decimal(str(r['UnitPrice'])) * r['Quantity'] for r in eligible), Decimal(0))
        expected.append({'CustomerID': cid,
                         'revenue_pence': int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
                         'invoice_count': len({r['InvoiceNo'] for r in eligible})})
    return expected


def evaluate_check(spec, data, load_source):
    try:
        public = load_source('data')['tables']
        basis = _records(load_source('basis')['tables']['basis_meta'])
        if len(basis) != 1 or basis[0]['period'] != spec['period']:
            return {'passed': False, 'reason': 'chosen_retail_basis_not_applicable'}
        expected = expected_metrics(_records(public['retail']), _records(public['customers']), basis[0])
        actual = data['tables']
        passed = set(actual) == {'metrics'} and Counter(_canonical(r) for r in _records(actual['metrics'])) == Counter(_canonical(r) for r in expected)
        return {'passed': passed, 'reason': 'independent_public_retail_contract',
                'expected_row_count': len(expected), 'actual_row_count': len(actual.get('metrics', {}).get('rows', [])),
                'editable_tests_used_as_truth': False}
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        return {'passed': False, 'reason': 'invalid_retail_product_or_basis', 'diagnostic': str(error)}
