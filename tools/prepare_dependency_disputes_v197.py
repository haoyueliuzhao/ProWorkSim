"""Validate and freeze blind disagreements; no experiment results are read."""
from __future__ import annotations
import json,hashlib,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/software-benchmark-v197'
BLIND=ROOT/'runs/software-benchmark-v197/blind-material-r1'
OUT=ROOT/'runs/software-benchmark-v197/blind-disputes-r1'
LABELS={'essential','useful','irrelevant','uncertain'}

def read(p):return json.loads(p.read_bytes())
def validate(row,brief,who):
    assert row['point']==brief['point'] and row['reviewer']==who
    assert row['review_type']=='AI_blind'
    candidates={e['id']:e for e in brief['historical_candidates']}
    prefix=json.loads(gzip.decompress((BLIND/brief['point']/'visible-prefix.json.gz').read_bytes()))
    legal_indices={x['message_index'] for x in prefix['source_messages']}
    assert len(row['labels'])==len(candidates) and {x['event'] for x in row['labels']}==set(candidates)
    for item in row['labels']:
        assert item['label'] in LABELS and item['reason']
        # A reason may also cite a later, already visible observation that
        # makes the old event redundant. All such citations must be in-prefix.
        assert item['source_messages'] and set(item['source_messages'])<=legal_indices,(brief['point'],who,item['event'],'citation outside visible prefix')
    assert set(row['must_keep_failure_events'])<=set(candidates)
    return {x['event']:x for x in row['labels']}

def main():
    OUT.mkdir(parents=True,exist_ok=True);ready=[]
    for i in range(1,49):
        p=f'P{i:03d}';paths=[BASE/f'reviewer-{w}-r1/{p}.json' for w in ['A','B']]
        if not all(f.exists() for f in paths):break
        a,b=map(read,paths);brief=read(BLIND/p/'brief.json');aa=validate(a,brief,'A');bb=validate(b,brief,'B')
        disagreements=[e for e in aa if aa[e]['label']!=bb[e]['label']]
        packet={'point':p,'reviewer_A':a,'reviewer_B':b,'disagreed_events':disagreements,
            'label_agreement':{e:aa[e]['label'] for e in aa if e not in disagreements},
            'dependency_adjudication_required':a['dependencies']!=b['dependencies'],
            'source_hashes':{w:hashlib.sha256(path.read_bytes()).hexdigest() for w,path in zip(['A','B'],paths)}}
        target=OUT/f'{p}.json'
        if target.exists():assert read(target)==packet,'Frozen review changed'
        else:
            with target.open('x') as f:json.dump(packet,f,ensure_ascii=False,indent=2);f.write('\n')
        ready.append(p)
    (OUT/'progress.json').write_text(json.dumps({'ready':ready,'all48':len(ready)==48},indent=2)+'\n')
    (OUT/'REVIEW.md').write_text('''# Independent blind adjudication

Read only this directory, blind-material-r1, and your own adjudicator output. Do not read experiment results, code, reports, Git, final scores or other directories. This is AI-assisted adjudication, not human gold annotation. Process P001..P048 in order, saving each once before any later point. Wait for missing packets; root will notify when more are available.

For each packet compare the two labels and dependency judgments using only that point's visible prefix. Keep agreed labels unless you find a concrete source error and explain that override. Resolve disagreements on the meaning of essential: an old evidence item needed for the next defensible decision and not already in the recent window or retained actions. Useful means helpful but dispensable. An empty essential set is legitimate. Prefer uncertain when evidence cannot decide; do not force agreement for a gate. Combine verified necessary-entity and dependency annotations with source citations; never promote a likely import target to an observed runtime dependency. Identify clear cross-file, failure/change and version-change coverage from the actual evidence. Recent state and action text are present for all conditions. Full original material is available at blind-material-r1/Pxxx/visible-prefix.json.gz. Do not invent future outcomes or use recalled benchmark solutions.

Output one exclusive JSON file per point to artifacts/software-benchmark-v197/adjudicator-r1/Pxxx.json:
{"point":"P001","review_type":"AI_blind_adjudication","decision":"...","labels":[{"event":"E001","label":"essential|useful|irrelevant|uncertain","reason":"...","source_messages":[12],"resolution":"agreed|adjudicated|uncertain|source_error_override"}],"necessary_entities":[],"dependencies":[{"from":"path/entity","to":"path/entity","relation":"import|call|test|version|other","necessary":true,"certainty":"observed_syntax|observed_execution|version_binding|inferred|uncertain","source_messages":[12],"reason":"..."}],"must_keep_failure_events":[],"missing_evidence":[],"coverage":{"cross_file":false,"failure_and_change":false,"version_change":false},"unresolved_events":[],"adjudication_notes":"..."}

Supply every candidate label. Do not replace reasoning with a rule based on file names or event kinds. You may leave uncertainty and say why. Root will calculate pre-adjudication agreement independently. Report progress every12 points; do not modify reviewer originals. No APIs, containers, GPU, tests, shared-host changes, commits or pushes.
''')
    print('ready',len(ready))

if __name__=='__main__':main()
