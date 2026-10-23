"""Reuse closed-slot metadata; read only missing PROJECT cost/schema fields."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT/'runs/software-benchmark-v055/score-gap-evidence-r1'
rows = json.loads((OUT/'normal-closed-slot-metadata.json').read_bytes())
output = []
constraints = Counter()
examples = {}
read_bytes = 0
for row in rows:
    if not row['group'].startswith('Qwen:'):
        continue
    value = {key: row[key] for key in ('slot_id', 'group', 'controller', 'tokens', 'complete_tokens', 'attempts', 'decisions')}
    if row['group'] == 'Qwen:PROJECT':
        raw = Path(row['controller']['path']).read_bytes()
        read_bytes += len(raw)
        model = json.loads(raw)['ledger']['model']
        charges = [item['charge'] for item in model['records'].values() if 'charge' in item]
        statuses = Counter(charge.get('usage_status') for charge in charges)
        value.update(charged_tokens=model['charged_tokens'], held_tokens=model['held_tokens'],
            integrity_failure=model['integrity_failure'], charge_usage_status_counts=dict(statuses),
            all_charges_reported_actual_trace=bool(charges) and set(statuses)=={'reported_actual_trace'},
            known_reported_actual_tokens=sum(charge.get('reported_usage', {}).get('total_tokens', 0)
                for charge in charges if charge.get('usage_status')=='reported_actual_trace'),
            counted_source='direct original normal-closed controller ledger.model; no inferred held/integrity')
        if row.get('recoverable_argument_errors'):
            p = Path(row['controller']['path']).parent/'managed-boundary.json'
            raw = p.read_bytes()
            read_bytes += len(raw)
            boundary = json.loads(raw)
            for item in boundary['action_error_policy'].get('argument_rejections', []):
                failure = item.get('parser_failure', {})
                key = str(failure.get('constraint')) + ':' + '.'.join(str(x) for x in failure.get('field_path') or [])
                constraints[key] += 1
                if key not in examples:
                    examples[key] = {'selection': 'first in frozen slot order', 'slot_id': row['slot_id'],
                        'boundary': {'path': str(p), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)},
                        'rejection': item, 'tool_name_available_in_rejection_record': 'tool' in item}
    else:
        value['counted_source'] = 'reused first normal-closed pass; no reread of native controller'
    output.append(value)
value = {'created_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'original 1485 Qwen normal-closed slots; original 15 generation unknowns remain in prior audit',
    'rows': output, 'project_argument_constraint_field_counts': dict(constraints), 'first_mechanical_examples': examples,
    'additional_read_bytes': read_bytes, 'model_calls': 0, 'test_executions': 0, 'scoring_calls': 0}
for root in [OUT, ROOT/'artifacts/software-benchmark-v055/score-gap-evidence-r1']:
    with (root/'qwen-cost-and-schema.json').open('x') as stream:
        json.dump(value, stream, indent=2)
print(json.dumps({'rows': len(output), 'constraints': dict(constraints), 'additional_read_bytes': read_bytes}))
