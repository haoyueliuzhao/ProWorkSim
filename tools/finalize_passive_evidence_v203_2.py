"""Add explicit review projection from saved receipts; no world or API execution."""
import collections
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from inventory_multimember_v203 import ROOT, read, ref, save
from proworksim.software_passive_observer_v203_2 import PassiveRecorder, PassiveState

ART = ROOT / 'artifacts/software-benchmark-v203-2'
RUN = ROOT / 'runs/software-benchmark-v203-2'

def main():
    previous = read(ART / 'lifecycle-r4/summary.json')
    panel = {r['slot_index']: r for r in read(ROOT / 'artifacts/software-benchmark-v203-1/panel-r1/plan.json')['rows']}
    rows = []
    for row in previous['rows']:
        data = json.loads(gzip.decompress(Path(row['snapshots']['path']).read_bytes()))
        spec = panel[row['slot_index']]
        state = PassiveState(spec['slot_id'], spec['fixed_members'])
        for frame in data['frames']:
            state.apply(frame)
        assert set(state.phases) == set(data['phases'])
        assert all(state.phases[k]['state']['receipt_count'] == data['phases'][k]['state']['receipt_count'] for k in state.phases)
        data.update(phases=state.phases, events=state.events, final_state=state.snapshot())
        destination = ART / f'lifecycle-r5/snapshots/{row["slot_index"]}.json.gz'
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as f:
            f.write(gzip.compress(json.dumps(data, ensure_ascii=False).encode(), mtime=0))
        rows.append({**row, 'source':row['snapshots'], 'snapshots':ref(destination),
                     'event_types':dict(collections.Counter(e['kind'] for e in state.events))})
    summary = {**previous, 'rows':rows, 'canonical_revision':'r5',
               'event_types':dict(sum((collections.Counter(r['event_types']) for r in rows), collections.Counter())),
               'additional_world_or_API_calls':0}
    save(ART / 'lifecycle-r5/summary.json', summary)
    save(ART / 'lifecycle-r5/protocol.json', {'source':ref(Path(__file__)),
        'observer':ref(ROOT / 'src/proworksim/software_passive_observer_v203_2.py'),
        'parent':ref(ART / 'lifecycle-r4/summary.json'),
        'change':'Review decisions and original test evidence preserved separately; no new tests inferred',
        'no_new_source_tree_recovery_or_world_execution':True})
    journal = RUN / 'passive-delivery-r2/observer/events.jsonl'
    if not journal.exists():
        candidates = list((RUN / 'passive-delivery-r2').rglob('events.jsonl'))
        assert len(candidates) == 1
        journal = candidates[0]
    first = json.loads(journal.read_text().splitlines()[0])
    # Use the scope saved by the control rather than inventing another identity.
    old = read(ART / 'passive-delivery-r2/phases.json')
    state0 = next(iter(old.values()))['state']
    state, proof = PassiveRecorder.replay(journal, state0['scope'], state0['members'])
    assert len(state.reviews) == 2 and len(state.deliveries) == 1
    assert state.deliveries[0]['actor'] == 'member_001'
    assert len(state.tests) == 4
    save(ART / 'passive-delivery-r3/summary.json', {'status':'saved_control_journal_reprojection_only',
        'parent':ref(ART / 'passive-delivery-r2/summary.json'), 'source_journal':ref(journal),
        'observer':ref(ROOT / 'src/proworksim/software_passive_observer_v203_2.py'),
        'proof':proof, 'reviews':state.reviews, 'public_test_records':len(state.tests),
        'delivery_member':state.deliveries[0]['actor'], 'phase_count':len(state.phases),
        'additional_world_or_API_calls':0, 'original_control_success_not_a_new_model_result':True})
    print(json.dumps({'historical_tasks':len(rows),'review_events':summary['event_types'].get('Artifact Review Recorded',0),
        'CPU_control_reviews':len(state.reviews),'new_execution':0}))

if __name__ == '__main__':
    main()
