"""Freeze six harness-development slices, excluding every v0.15 entity.

This uses the same real UCI source, not another independent source. The source
XLSX is scanned, but only the six bounded slices become worker-visible assets.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import openpyxl

from scripts.import_retail_v015 import FIELDS, sha
from proworksim.templates.retail_work import SOURCE_PIN

VERSION = 'uci-retail-harness-assets-v0.16'


def build_assets(source, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Harness assets must use a new output directory')
    old = json.loads((source / 'manifest.json').read_text())
    original = source / old['xlsx']['path']
    if old['xlsx']['sha256'] != SOURCE_PIN['xlsx_sha256'] or sha(original) != old['xlsx']['sha256']:
        raise ValueError('Original XLSX differs from frozen v0.15 source')
    excluded_customers = {c for s in old['slices'] for c in s['customers']}
    excluded_invoices = {i for s in old['slices'] for i in s['invoice_ids']}
    book = openpyxl.load_workbook(original, read_only=True, data_only=True)
    iterator = book.active.iter_rows(values_only=True)
    if list(next(iterator)) != FIELDS:
        raise ValueError('Source schema changed')
    invoices = defaultdict(list)
    row_count = 0
    for excel_row, values in enumerate(iterator, 2):
        invoice, stock, desc, quantity, date, price, customer, country = values
        customer = None if customer is None else str(int(customer))
        row = [str(invoice), str(stock), desc, int(quantity), date.isoformat(sep=' '),
               str(price), customer, country, excel_row]
        invoices[str(invoice)].append(row)
        row_count += 1
    book.close()
    by_customer = defaultdict(list)
    for invoice, rows in invoices.items():
        customers = {r[6] for r in rows}
        if (invoice not in excluded_invoices and len(customers) == 1
                and None not in customers and not customers & excluded_customers
                and 1 <= len(rows) <= 10
                and all(Decimal(r[5]).as_tuple().exponent >= -2 for r in rows)):
            by_customer[next(iter(customers))].append(invoice)
    eligible = {}
    for customer, ids in by_customer.items():
        normal = sorted(i for i in ids if not i.upper().startswith('C') and len(invoices[i]) >= 2)
        cancelled = sorted(i for i in ids if i.upper().startswith('C'))
        if len(normal) >= 2 and cancelled:
            eligible[customer] = normal[:2] + cancelled[:1]
    ordered = sorted(eligible, key=lambda c: hashlib.sha256(('harness-v016:' + c).encode()).hexdigest())
    if len(ordered) < 12:
        raise ValueError('Insufficient disjoint complete invoice entities')
    output.mkdir(parents=True)
    slices = []
    for index in range(6):
        customers = sorted(ordered[2 * index:2 * index + 2])
        ids = sorted(i for c in customers for i in eligible[c])
        rows = sorted((r for i in ids for r in invoices[i]), key=lambda r: r[-1])
        slice_id = f'harness-development-f{index}'
        asset = {'slice_id': slice_id, 'fields': FIELDS + ['SourceRow'], 'rows': rows,
                 'customers': customers, 'invoice_ids': ids,
                 'complete_invoice_rows': {i: len(invoices[i]) for i in ids},
                 'source_xlsx_sha256': old['xlsx']['sha256']}
        path = output / (slice_id + '.json')
        path.write_text(json.dumps(asset, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        slices.append({'slice_id': slice_id, 'pool': 'harness_development', 'customers': customers,
                       'invoice_ids': ids, 'rows': len(rows), 'sha256': sha(path), 'path': path.name})
    manifest = {key: old[key] for key in ('dataset_id', 'source_url', 'dataset_url', 'doi', 'license', 'license_url', 'attribution', 'source_revision', 'transformations')}
    manifest.update(version=VERSION, xlsx=old['xlsx'], original_source_directory=str(source.resolve()),
                    observed_original_rows=row_count, previous_manifest_sha256=sha(source / 'manifest.json'),
                    excluded_customers=sorted(excluded_customers), excluded_invoices=sorted(excluded_invoices),
                    selection_rule='Exclude all v0.15 train/development/locked customers and invoices. Eligible customers have >=2 normal invoices of 2..10 rows and >=1 C invoice of 1..10 rows, single non-null customer per invoice, <=2-decimal prices. Sort eligible customer IDs by SHA256(harness-v016:ID), take first 12; consecutive pairs form six slices. Retain lexically first two normal and first cancellation invoices and every original row.',
                    source_relationship='Same UCI source; six new entity-disjoint development situations. Neither independent-source evaluation nor locked evaluation.',
                    usage='Harness development only; excludes v0.15 selection, online training and software transfer probe.',
                    slices=slices)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_assets(args.source, args.output)
    print(json.dumps({'rows_scanned': result['observed_original_rows'], 'slices': result['slices']}))


if __name__ == '__main__':
    main()
