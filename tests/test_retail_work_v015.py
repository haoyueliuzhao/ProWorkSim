"""New real-source boundaries, not a repeated full legacy regression."""
import copy
import shutil

import pytest

from proworksim.domains.retail_work import expected_metrics
from proworksim.storage import read_json
from proworksim.templates.retail_work import SOURCE_PIN, assets_root, case_spec, package, registry


def rules(mode='sales_only'):
    return {'edition': 'approved', 'invoice_mode': mode, 'currency': 'GBP',
            'duplicates': 'retain_source_rows', 'missing_customer': 'exclude',
            'price_rule': 'strictly_positive', 'start_inclusive': '2011-01-01 00:00:00',
            'end_exclusive': '2011-02-01 00:00:00'}


def test_gbp_cancellations_invoice_grain_and_zero_customers():
    # Two identical observed lines are retained; invoice count is distinct.
    row = {'CustomerID': '1', 'InvoiceNo': '100', 'InvoiceDate': '2011-01-01 00:00:00',
           'Quantity': 2, 'UnitPrice': '1.25'}
    rows = [row, copy.deepcopy(row), {**row, 'InvoiceNo': 'c100', 'Quantity': -1},
            {**row, 'InvoiceNo': 'boundary', 'InvoiceDate': '2011-02-01 00:00:00'},
            {**row, 'InvoiceNo': 'free', 'UnitPrice': '0.00'},
            {**row, 'InvoiceNo': 'missing', 'CustomerID': None}]
    clients = [{'CustomerID': '1'}, {'CustomerID': '2'}]
    assert expected_metrics(rows, clients, rules()) == [
        {'CustomerID': '1', 'revenue_pence': 500, 'invoice_count': 1},
        {'CustomerID': '2', 'revenue_pence': 0, 'invoice_count': 0}]
    assert expected_metrics(rows, clients, rules('net_signed'))[0] == {
        'CustomerID': '1', 'revenue_pence': 375, 'invoice_count': 2}
    with pytest.raises(ValueError, match='currency'):
        expected_metrics(rows, clients, {**rules(), 'currency': 'USD'})


def test_declared_entity_pools_and_all_responsibility_descendants():
    root = assets_root()
    if not (root / 'manifest.json').exists():
        pytest.skip('Pinned real source asset import is a separate preparation command')
    manifest = read_json(root / 'manifest.json')
    assert manifest['xlsx']['sha256'] == SOURCE_PIN['xlsx_sha256']
    customer_sets, invoice_sets = {}, {}
    for entry in manifest['slices']:
        data = read_json(root / entry['path'])
        pool = entry['pool']
        customer_sets.setdefault(pool, set()).update(entry['customers'])
        invoice_sets.setdefault(pool, set()).update(entry['invoice_ids'])
        assert len(data['rows']) <= 60
        assert {i: sum(row[0] == i for row in data['rows']) for i in entry['invoice_ids']} == data['complete_invoice_rows']
    pools = list(customer_sets)
    for i, left in enumerate(pools):
        for right in pools[i+1:]:
            assert not customer_sets[left] & customer_sets[right]
            assert not invoice_sets[left] & invoice_sets[right]
    cases = registry()['situations']
    assert len(cases) == 36
    for entry in manifest['slices']:
        descendants = [c for c in cases if c['slice_id'] == entry['slice_id']]
        assert {c['task'] for c in descendants} == {'implement', 'review', 'pair', 'chain'}
        assert {c['pool'] for c in descendants} == {entry['pool']}


def test_untracked_manifest_cannot_substitute_source_pin(tmp_path):
    root = assets_root()
    if not (root / 'manifest.json').exists():
        pytest.skip('Pinned assets absent')
    shutil.copy(root / 'manifest.json', tmp_path / 'manifest.json')
    path = tmp_path / 'manifest.json'
    path.write_text(path.read_text().replace(SOURCE_PIN['xlsx_sha256'], '0' * 64))
    with pytest.raises(ValueError, match='source-controlled'):
        package(case_spec('uci-development-f0-implement'), source_root=tmp_path)


def test_readable_data_retains_real_semantics_and_no_expected_result():
    root = assets_root()
    if not (root / 'manifest.json').exists():
        pytest.skip('Pinned assets absent')
    pkg = package(case_spec('uci-development-f0-pair'))
    objects = {o['alias']: o for o in pkg['objects']}
    data = objects['data']['data']
    assert [c['name'] for c in data['tables']['retail']['columns']] == [
        'InvoiceNo', 'StockCode', 'Description', 'Quantity', 'InvoiceDate', 'UnitPrice', 'CustomerID', 'Country', 'SourceRow']
    assert objects['basis']['readers'] == ['operator', 'provider']
    assert 'expected' not in data and 'metrics' not in data['tables']
    assert pkg['works'][0]['deliverable_contract']['content_checks'][0]['kind'] == 'retail_customer_metrics'
