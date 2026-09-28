"""Partition new complete UCI customer/invoice groups before v0.24 tasks."""
import argparse
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import openpyxl

from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates.retail_work import SOURCE_PIN
from scripts.import_retail_v015 import FIELDS, sha

VERSION = 'uci-collaboration-assets-v0.24'


def build_assets(source, old_harness, old_v22, old_v23, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Output must be new')
    roots = [source, Path(old_harness), Path(old_v22), Path(old_v23)]
    previous = [(p / 'manifest.json', json.loads((p / 'manifest.json').read_text())) for p in roots]
    old = previous[0][1]
    workbook = source / old['xlsx']['path']
    if sha(workbook) != SOURCE_PIN['xlsx_sha256']:
        raise ValueError('Original XLSX identity changed')
    excluded_customers = {c for _, m in previous for s in m['slices'] for c in s['customers']}
    excluded_invoices = {i for _, m in previous for s in m['slices'] for i in s['invoice_ids']}
    excluded_rows = set()
    for path, manifest in previous:
        for entry in manifest['slices']:
            asset = path.parent / entry['path']
            if sha(asset) != entry['sha256']:
                raise ValueError('Previous derived slice identity changed')
            excluded_rows.update(r[-1] for r in json.loads(asset.read_text())['rows'])
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    it = book.active.iter_rows(values_only=True)
    if list(next(it)) != FIELDS:
        raise ValueError('Unexpected source columns')
    invoices = defaultdict(list)
    for row_index, values in enumerate(it, 2):
        invoice, stock, description, quantity, date, price, customer, country = values
        customer = None if customer is None else str(int(customer))
        invoices[str(invoice)].append([str(invoice), str(stock), description, int(quantity), date.isoformat(sep=' '), str(price), customer, country, row_index])
    book.close()
    by_customer = defaultdict(list)
    for invoice, rows in invoices.items():
        ids = {r[6] for r in rows}
        if (invoice not in excluded_invoices and len(ids) == 1 and None not in ids and not ids & excluded_customers
                and 1 <= len(rows) <= 3 and all(Decimal(r[5]).as_tuple().exponent >= -2 for r in rows)):
            by_customer[next(iter(ids))].append(invoice)
    eligible = {}
    for customer, ids in by_customer.items():
        regular = sorted(i for i in ids if not i.upper().startswith('C') and len(invoices[i]) >= 2)
        cancelled = sorted(i for i in ids if i.upper().startswith('C')
                           and any(r[3] < 0 and Decimal(r[5]) > 0 for r in invoices[i]))
        if len(regular) >= 2 and cancelled:
            eligible[customer] = regular[:2] + cancelled[:1]
    ordered = sorted(eligible, key=lambda c: hashlib.sha256(('collaboration-v024:' + c).encode()).hexdigest())
    if len(ordered) < 28:
        raise ValueError('Need 28 previously unused customer groups')
    # The source usage split is made here; task/quality/seed derivation happens later.
    uses = ['paired_evaluation'] * 6 + ['pilot_training'] * 8
    output.mkdir(parents=True)
    slices, seen_rows, seen_customers, seen_invoices = [], set(), set(), set()
    for position, use in enumerate(uses):
        customers = sorted(ordered[2 * position:2 * position + 2])
        ids = sorted(i for c in customers for i in eligible[c])
        rows = sorted((r for i in ids for r in invoices[i]), key=lambda r: r[-1])
        row_ids = {r[-1] for r in rows}
        if (row_ids & (seen_rows | excluded_rows) or set(customers) & (seen_customers | excluded_customers)
                or set(ids) & (seen_invoices | excluded_invoices)):
            raise ValueError('Entity/row usage boundary violated')
        sid = f'v024-material-{position:02d}'
        asset = {'slice_id': sid, 'fields': FIELDS + ['SourceRow'], 'rows': rows,
                 'customers': customers, 'invoice_ids': ids,
                 'complete_invoice_rows': {i: len(invoices[i]) for i in ids},
                 'source_xlsx_sha256': SOURCE_PIN['xlsx_sha256']}
        target = output / (sid + '.json')
        atomic_write(target, json_bytes(asset))
        slices.append({'slice_id': sid, 'pool': use, 'position': position, 'path': target.name,
                       'sha256': sha(target), 'customers': customers, 'invoice_ids': ids,
                       'rows': len(rows), 'source_rows': sorted(row_ids),
                       'source_rows_sha256': digest(json_bytes(sorted(row_ids))),
                       'complete_invoice_rows': asset['complete_invoice_rows']})
        seen_rows.update(row_ids)
        seen_customers.update(customers)
        seen_invoices.update(ids)
    manifest = {k: old[k] for k in ('dataset_id', 'source_url', 'dataset_url', 'doi', 'license', 'license_url', 'attribution', 'source_revision', 'transformations')}
    manifest.update(version=VERSION, xlsx=old['xlsx'], original_source_directory=str(source.resolve()),
                    previous_manifests=[{'path': str(p.resolve()), 'sha256': sha(p)} for p, _ in previous],
                    excluded_customers=sorted(excluded_customers), excluded_invoices=sorted(excluded_invoices),
                    excluded_source_rows=sorted(excluded_rows), observed_original_rows=row_index - 1,
                    eligible_customer_count=len(eligible), slices=slices,
                    selection_rule='Exclude all v015/v016/v022/v023 customer, complete invoice and source row groups first. Eligible customers have lexical first two complete non-C invoices of 2..3 rows and first complete C invoice of 1..3 rows with a positive-price negative-quantity cancellation; original prices have <=2 decimal places. SHA256(collaboration-v024:ID) order, first28 customers, consecutive pairs. Assign first6 pairs evaluation and remaining8 training before deriving tasks, qualities or seeds. Preserve every selected invoice row.',
                    source_relationship='One UCI Online Retail family; unused entity/row groups, not independent sources or semantic decontamination.',
                    derivative_rule='Every role, preparation quality, seed repeat and maintenance policy derivative retains the parent material usage. Each training window consumes four unique materials; A/B repeats share exact case.',
                    usage='6 paired evaluation materials;8 train materials. No model outcome used in selection.',
                    training_eligible=False, source_admission=False, model_outcomes_used=False)
    atomic_write(output / 'manifest.json', json_bytes(manifest))
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default='runs/assets/uci-online-retail-v015')
    p.add_argument('--old-harness', default='runs/assets/uci-retail-harness-v016')
    p.add_argument('--old-v22', default='runs/assets/uci-collaboration-v022')
    p.add_argument('--old-v23', default='runs/assets/uci-collaboration-v023')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    m = build_assets(a.source, a.old_harness, a.old_v22, a.old_v23, a.output)
    print(json.dumps({'version': m['version'], 'slices': len(m['slices']), 'rows': sum(s['rows'] for s in m['slices'])}))
