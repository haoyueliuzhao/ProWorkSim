"""New complete UCI invoices for W1 and reserved bridge; no model selection."""
import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import openpyxl

from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates.retail_work import SOURCE_PIN
from scripts.import_retail_v015 import FIELDS, sha

VERSION = 'uci-collaboration-assets-v0.22'


def build_assets(source, old_harness, output):
    source, old_harness, output = Path(source), Path(old_harness), Path(output)
    if output.exists():
        raise ValueError('Output must be new')
    old = json.loads((source / 'manifest.json').read_text())
    previous = [(source / 'manifest.json', old), (old_harness / 'manifest.json', json.loads((old_harness / 'manifest.json').read_text()))]
    workbook = source / old['xlsx']['path']
    if sha(workbook) != SOURCE_PIN['xlsx_sha256'] or old['xlsx']['sha256'] != SOURCE_PIN['xlsx_sha256']:
        raise ValueError('Original source bytes changed')
    customers = {c for _, m in previous for s in m['slices'] for c in s['customers']}
    invoice_ids = {i for _, m in previous for s in m['slices'] for i in s['invoice_ids']}
    prior_rows = set()
    for path, m in previous:
        for s in m['slices']:
            asset = path.parent / s['path']
            if sha(asset) != s['sha256']:
                raise ValueError('Prior pinned source slice changed')
            prior_rows.update(r[-1] for r in json.loads(asset.read_text())['rows'])
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    it = book.active.iter_rows(values_only=True)
    if list(next(it)) != FIELDS:
        raise ValueError('Original columns changed')
    invoices = defaultdict(list)
    for row_index, values in enumerate(it, 2):
        invoice, stock, description, quantity, date, price, customer, country = values
        customer = None if customer is None else str(int(customer))
        invoices[str(invoice)].append([str(invoice), str(stock), description, int(quantity), date.isoformat(sep=' '), str(price), customer, country, row_index])
    book.close()
    by_customer = defaultdict(list)
    for invoice, rows in invoices.items():
        ids = {r[6] for r in rows}
        if (invoice not in invoice_ids and len(ids) == 1 and None not in ids and not ids & customers
                and 1 <= len(rows) <= 10 and all(Decimal(r[5]).as_tuple().exponent >= -2 for r in rows)):
            by_customer[next(iter(ids))].append(invoice)
    eligible = {}
    for customer, ids in by_customer.items():
        regular = sorted(i for i in ids if not i.upper().startswith('C') and len(invoices[i]) >= 2)
        cancelled = sorted(i for i in ids if i.upper().startswith('C'))
        if len(regular) >= 2 and cancelled:
            eligible[customer] = regular[:2] + cancelled[:1]
    ordered = sorted(eligible, key=lambda c: hashlib.sha256(('collaboration-v022:' + c).encode()).hexdigest())
    if len(ordered) < 24:
        raise ValueError('Insufficient new complete-invoice customers')
    output.mkdir(parents=True)
    slices, all_rows, seen_customers, seen_invoices = [], set(), set(), set()
    uses = ['w1_development'] * 6 + ['reserved_training'] * 4 + ['reserved_bridge_development'] * 2
    for position, use in enumerate(uses):
        cs = sorted(ordered[2 * position:2 * position + 2])
        ids = sorted(i for c in cs for i in eligible[c])
        rows = sorted((r for i in ids for r in invoices[i]), key=lambda r: r[-1])
        row_ids = {r[-1] for r in rows}
        if row_ids & (all_rows | prior_rows) or set(cs) & seen_customers or set(ids) & seen_invoices:
            raise ValueError('New use crosses an existing entity or source-row group')
        slice_id = f'v022-material-{position:02d}'
        asset = {'slice_id': slice_id, 'fields': FIELDS + ['SourceRow'], 'rows': rows,
                 'customers': cs, 'invoice_ids': ids, 'complete_invoice_rows': {i: len(invoices[i]) for i in ids},
                 'source_xlsx_sha256': old['xlsx']['sha256']}
        target = output / (slice_id + '.json')
        atomic_write(target, json_bytes(asset))
        slices.append({'slice_id': slice_id, 'pool': use, 'position': position, 'path': target.name,
                       'sha256': sha(target), 'customers': cs, 'invoice_ids': ids, 'rows': len(rows),
                       'source_rows': sorted(row_ids), 'source_rows_sha256': digest(json_bytes(sorted(row_ids))),
                       'complete_invoice_rows': asset['complete_invoice_rows']})
        all_rows.update(row_ids)
        seen_customers.update(cs)
        seen_invoices.update(ids)
    manifest = {k: old[k] for k in ('dataset_id', 'source_url', 'dataset_url', 'doi', 'license', 'license_url', 'attribution', 'source_revision', 'transformations')}
    manifest.update(version=VERSION, xlsx=old['xlsx'], original_source_directory=str(source.resolve()),
                    previous_manifests=[{'path': str(p.resolve()), 'sha256': sha(p)} for p, _ in previous],
                    excluded_customers=sorted(customers), excluded_invoices=sorted(invoice_ids),
                    excluded_source_rows=sorted(prior_rows), observed_original_rows=row_index - 1,
                    eligible_customer_count=len(eligible), slices=slices,
                    selection_rule='Exclude all v015 and v016 customers/invoices/source rows; each customer has two complete non-C invoices of 2..10 rows and one complete C invoice of 1..10 rows, one non-null customer per invoice, <=2-decimal prices. Sort customers by SHA256(collaboration-v022:ID), take first24, consecutive pairs define12 materials. Choose lexical first2 normal and first1 cancellation. Preserve every selected invoice row.',
                    source_relationship='Same UCI Online Retail family; entity/source-row-disjoint instances, not independent sources or semantic decontamination.',
                    usage='First6 W1 development, next4 reserved training, last2 reserved bridge development. Reserved does not mean policy/training admission.',
                    training_eligible=False, source_admission=False, model_outcomes_used=False)
    atomic_write(output / 'manifest.json', json_bytes(manifest))
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default='runs/assets/uci-online-retail-v015')
    p.add_argument('--old-harness', default='runs/assets/uci-retail-harness-v016')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    result = build_assets(args.source, args.old_harness, args.output)
    print(json.dumps({'version': result['version'], 'slices': len(result['slices']), 'new_customers': sum(len(s['customers']) for s in result['slices']), 'rows': sum(s['rows'] for s in result['slices'])}))
