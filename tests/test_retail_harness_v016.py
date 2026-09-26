"""Only new source boundaries and preparation evidence are tested here."""
import copy
from collections import Counter

import pytest

from proworksim.storage import digest, read_json
from proworksim.templates import retail_harness, retail_work


def test_harness_entities_do_not_touch_any_frozen_usage_pool():
    pin = read_json(retail_harness.PIN_PATH)
    old = read_json(retail_work.assets_root() / 'manifest.json')
    assert pin['previous_manifest_sha256'] == digest((retail_work.assets_root() / 'manifest.json').read_bytes())
    excluded_customers = {c for s in old['slices'] for c in s['customers']}
    excluded_invoices = {i for s in old['slices'] for i in s['invoice_ids']}
    seen_customers, seen_invoices = set(), set()
    for entry in pin['slices']:
        case = next(c for c in retail_harness.registry()['situations'] if c['slice_id'] == entry['slice_id'])
        data, _, _ = retail_harness._load_slice(case, None)
        assert not (excluded_customers | seen_customers) & set(data['customers'])
        assert not (excluded_invoices | seen_invoices) & set(data['invoice_ids'])
        assert dict(Counter(row[0] for row in data['rows'])) == data['complete_invoice_rows']
        seen_customers.update(data['customers'])
        seen_invoices.update(data['invoice_ids'])
    assert (len(seen_customers), len(seen_invoices)) == (12, 36)
    assert Counter(c['task'] for c in retail_harness.registry()['situations']) == {'implement': 2, 'review': 2, 'pair': 1, 'chain': 1}
    assert len(retail_work.registry()['situations']) == 36


def test_harness_manifest_and_case_are_fail_closed(tmp_path):
    root = retail_harness.assets_root()
    if not root.exists():
        pytest.skip('Independent source assets have not been prepared')
    pin = read_json(root / 'manifest.json')
    pin['slices'][0]['customers'] = ['changed']
    import json
    (tmp_path / 'manifest.json').write_text(json.dumps(pin))
    case = retail_harness.case_spec('uci-harness-f0-implement')
    with pytest.raises(ValueError, match='source-controlled'):
        retail_harness.package(case, source_root=tmp_path)
    changed = copy.deepcopy(case)
    changed['business_facts']['currency'] = 'USD'
    with pytest.raises(ValueError, match='independent frozen catalog'):
        retail_harness.build_harness_case(changed, tmp_path / 'world')
