"""Import pinned UCI rows; freeze disjoint-customer, complete-invoice slices.

This is source preparation only. No SQL solution, result or demonstration is
written into the worker data asset.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import zipfile

import openpyxl

URL = 'https://archive.ics.uci.edu/static/public/352/online+retail.zip'
PAGE = 'https://archive.ics.uci.edu/dataset/352/online+retail'
FIELDS = ['InvoiceNo', 'StockCode', 'Description', 'Quantity', 'InvoiceDate', 'UnitPrice', 'CustomerID', 'Country']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_assets(root):
    root = Path(root)
    archive = root / 'online-retail.zip'
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if names != ['Online Retail.xlsx']:
            raise ValueError('Unexpected source archive layout')
        original = root / names[0]
        if not original.exists():
            original.write_bytes(zipped.read(names[0]))
    book = openpyxl.load_workbook(original, read_only=True, data_only=True)
    rows = book.active.iter_rows(values_only=True)
    if list(next(rows)) != FIELDS:
        raise ValueError('Unexpected official field layout')
    invoices = defaultdict(list)
    counts = {'rows': 0, 'missing_customer_rows': 0, 'cancellation_rows': 0}
    for excel_row, values in enumerate(rows, 2):
        invoice, stock, desc, quantity, date, price, customer, country = values
        customer = None if customer is None else str(int(customer))
        row = [str(invoice), str(stock), desc, int(quantity), date.isoformat(sep=' '),
               str(price), customer, country, excel_row]
        invoices[str(invoice)].append(row)
        counts['rows'] += 1
        counts['missing_customer_rows'] += customer is None
        counts['cancellation_rows'] += str(invoice).upper().startswith('C')
    book.close()
    customers = defaultdict(list)
    for invoice, group in invoices.items():
        ids = {row[6] for row in group}
        if len(ids) == 1 and None not in ids and 1 <= len(group) <= 10 and all(
            Decimal(row[5]).as_tuple().exponent >= -2 for row in group
        ):
            customers[next(iter(ids))].append(invoice)
    eligible = {}
    for customer, identifiers in customers.items():
        normal = sorted(i for i in identifiers if not i.upper().startswith('C') and len(invoices[i]) >= 2)
        cancelled = sorted(i for i in identifiers if i.upper().startswith('C'))
        if len(normal) >= 2 and cancelled:
            eligible[customer] = normal[:2] + cancelled[:1]
    slices = []
    selected_customers = set()
    for pool_index, pool in enumerate(('train', 'development', 'locked')):
        candidates = sorted(c for c in eligible if int(hashlib.sha256(c.encode()).hexdigest(), 16) % 3 == pool_index)
        if len(candidates) < 6:
            raise ValueError('Insufficient full customer entities for frozen slices')
        for fact in range(3):
            clients = candidates[2*fact:2*fact+2]
            if selected_customers.intersection(clients):
                raise ValueError('Customer usage pools overlap')
            selected_customers.update(clients)
            ids = sorted(i for c in clients for i in eligible[c])
            data = sorted((r for i in ids for r in invoices[i]), key=lambda r: r[-1])
            slice_id = f'{pool}-f{fact}'
            asset = {'slice_id': slice_id, 'fields': FIELDS + ['SourceRow'], 'rows': data,
                     'customers': clients, 'invoice_ids': ids,
                     'complete_invoice_rows': {i: len(invoices[i]) for i in ids},
                     'source_xlsx_sha256': sha(original)}
            payload = json.dumps(asset, ensure_ascii=False, sort_keys=True, indent=2).encode()
            path = root / (slice_id + '.json')
            path.write_bytes(payload)
            slices.append({'slice_id': slice_id, 'pool': pool, 'customers': clients,
                           'invoice_ids': ids, 'rows': len(data), 'sha256': sha(path), 'path': path.name})
    manifest = {
        'version': 'uci-online-retail-assets-v0.15', 'dataset_id': 352,
        'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_url': URL, 'dataset_url': PAGE, 'doi': '10.24432/C5BW33',
        'source_revision': 'No immutable upstream release supplied; original bytes pinned by SHA-256.',
        'license': 'CC-BY-4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'attribution': 'Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33.',
        'archive': {'path': archive.name, 'sha256': sha(archive), 'bytes': archive.stat().st_size},
        'xlsx': {'path': original.name, 'sha256': sha(original), 'bytes': original.stat().st_size},
        'observed_source_counts': counts, 'distinct_invoices': len(invoices),
        'selection_rule': 'CustomerID SHA256 modulo 3 assigns train/development/locked. Within each bucket take lexically first six eligible customers, two per slice. Eligible customer has >=2 non-C invoices of 2..10 rows and >=1 C invoice of 1..10 rows; each retained invoice has a single non-null CustomerID and all UnitPrice values have <=2 decimals. Retain first two normal and first cancellation invoices lexically and ALL their original rows. No row-level split or deduplication. Other invoices of these customers are not used in another pool.',
        'transformations': 'Original XLSX retained. IDs become lossless text, InvoiceDate ISO local-naive text, UnitPrice exact decimal text, and SourceRow is original Excel row number. No transaction value is synthesized or cleaned.',
        'source_relationship': 'One UCI source family; customer/entity disjoint usages do not establish independent-source generalization. Derived responsibilities of a slice remain in its same pool.',
        'slices': slices,
    }
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    manifest = build_assets(args.root)
    print(json.dumps({'source_rows': manifest['observed_source_counts'], 'slices': manifest['slices']}, indent=2))


if __name__ == '__main__':
    main()
