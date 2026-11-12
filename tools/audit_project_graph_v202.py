#!/usr/bin/env python3
"""Read-only post-run invariants; does not re-extract or rerun experiments."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from project_graph_materials_v202 import ROOT,read,save,ref
from proworksim.software_syntax_facts_v202 import sha

def main():
    art=ROOT/'artifacts/software-benchmark-v202';run=ROOT/'runs/software-benchmark-v202';result=read(art/'offline-results-r2/summary.json');manifest=read(art/'source-freeze-r2/manifest.json')
    errors=[];counts={'snapshots':0,'effective_test_edges':0,'expired_test_edges':0,'facts_in_snapshots':0,'source_documents':0,'adoptions':0}
    for i,sref in enumerate(manifest['streams']):
        stream=read(sref['path']);docs={};counts['source_documents']+=len(stream.get('documents',[]))
        for e in stream['events']:
            if e['kind'] in {'file_observed','file_written'}:
                d=e['data']['document'];docs[(d['source_id'],d['source_hash'])]=d
        for mode in ('PG1','PG2','PG3'):
            payload=read(run/f'offline-results-r2/graph-{i:02}-{mode}.json.gz')
            if payload['events']!=stream['events']:errors.append([i,mode,'event_log_changed'])
            if len(payload['snapshots'])!=len(stream['events']):errors.append([i,mode,'missing_snapshot'])
            for si,g in enumerate(payload['snapshots']):
                counts['snapshots']+=1;nodes=g['nodes'];edges=g['edges']
                for e in edges.values():
                    if e['source'] not in nodes or e['target'] not in nodes or not e['source_ids']:errors.append([i,mode,si,'unbound_edge'])
                    if e['type']=='validates_selected_scope':
                        r=nodes[e['source']];v=nodes[e['target']];current=g['current_versions'].get(r['actor'])
                        if r['version']!=v['reference'] or v['actor']!=r['actor']:errors.append([i,mode,si,'test_version_mismatch'])
                        if e['effective']!=(e['target']==current):errors.append([i,mode,si,'inherited_validation'])
                        counts['effective_test_edges' if e['effective'] else 'expired_test_edges']+=1
                    if e['type']=='may_import' and e['status']!='Inferred':errors.append([i,mode,si,'static_relation_promoted'])
                    if e['type']=='adopts':
                        counts['adoptions']+=1
                        if not e.get('does_not_validate'):errors.append([i,mode,si,'adoption_validation'])
                for node in nodes.values():
                    if node['type']=='Version' and node.get('is_git_commit') is not False:errors.append([i,mode,si,'version_as_commit'])
                    if node['type']!='Fact':continue
                    counts['facts_in_snapshots']+=1;key=(node['source_id'],node['source_hash']);d=docs.get(key)
                    if d is None and node['source_id'].startswith('rename:'):
                        # Same immutable bytes under a new path; explicit rename
                        # receipt is the provenance link, not a fresh source read.
                        d=next((x for x in docs.values() if x['source_hash']==node['source_hash'] and x['scope']==node['scope']),None)
                    if d is None:errors.append([i,mode,si,'unknown_fact_source']);continue
                    raw=d['text'].encode();a,z=node['start_byte'],node['end_byte']
                    if raw[a:z].decode()!=node['value']:errors.append([i,mode,si,'source_bytes_changed'])
                    if not d['complete'] and (node['completeness']=='complete' or node['qualified_scope_known']):errors.append([i,mode,si,'partial_promoted'])
    incremental=all(result['graph'][k]['conditions'][m]['events']==result['graph'][k]['conditions'][m]['exact_match_checkpoints'] for k in ['historical_wire','synthetic_control'] for m in ['PG2','PG3'])
    unchanged=all(ref(f['path'])['sha256']==f['sha256'] for f in manifest['files'])
    report={'scope':'independent snapshot assertions over measured outputs, not independent program-dependency gold','counts':counts,'errors':errors,
        'incremental_exact_reference_match':incremental,'measured_sources_unchanged':unchanged,
        'frozen_F1_unchanged':ref(ROOT/'src/proworksim/software_fact_budget_v200.py')['sha256']==manifest['old_F1_source_sha256'],
        'engineering_gate_pass':not errors and incremental and unchanged,
        'semantic_dependency_completeness_proven':False,'real_team_or_policy_benefit_proven':False,
        'source_manifest':ref(art/'source-freeze-r2/manifest.json'),'measured_result':ref(art/'offline-results-r2/summary.json')}
    save(art/'final-audit-r1/summary.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['engineering_gate_pass']:raise SystemExit(1)

if __name__=='__main__':main()
