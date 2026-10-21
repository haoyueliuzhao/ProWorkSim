"""Freeze the complete r3/r3.1 CPU baseline index without redoing preparation."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verified_image_prepare_v054 import now,save  # noqa: E402

RUN=ROOT/'runs/software-benchmark-v054/images/actor-admission-r3'
OUT=ROOT/'artifacts/software-benchmark-v054/actor'
R31_POLICY='7c3206938a850f1446aac627a44d2d87d99c15d742ac046bdebb0b1e00b520ed'


def normalized_format_evidence(path):
    record=json.loads(path.read_bytes())
    if record.get('schema')!='proworksim.v054.actor-admission-r3.1':
        return record
    if record.get('status')!='actor_baseline_admitted' or record['policy_sha256']!=R31_POLICY:
        raise ValueError('Only the executed exact-line r3.1 policy may be normalized')
    closure=record['git_ancestry']
    proofs=closure['historical_format_exceptions']
    if (closure.get('fsck_structural_validation_passed') is not True
            or closure.get('fsck_connectivity_returncode')!=0
            or not all(row['source_same_diagnostic'] and row['source_in_allowed_closure']
                       and row['target_object_hash_verified'] for row in proofs)):
        raise ValueError('Cannot reconstruct diagnostic evidence without the executed equality gate')
    lines=sorted(row['diagnostic_line'] for row in proofs)
    if len(lines)!=len(set(lines)):
        raise ValueError('Repeated historical diagnostic')
    if (closure.get('fsck_diagnostic_lines')==lines
            and record.get('git_fsck_returncode')==closure['fsck_returncode']):
        return record
    # RESTORE in this exact policy required empty stdout and exact equality of
    # these lines with observed stderr. Normalization does not run fsck again.
    closure['fsck_diagnostic_lines']=lines
    closure['fsck_diagnostic_lines_basis']=(
        'Normalized exact diagnostic lines; equality with observed stderr and empty stdout '
        'were enforced by the executed r3.1 policy. Raw diagnostic order was not separately retained.')
    record['git_fsck_returncode']=closure['fsck_returncode']
    record['git_fsck_stdout']=''
    record['git_fsck_stderr']='\n'.join(lines)+('\n' if lines else '')
    save(path,record)
    return record


def main():
    paths=sorted((RUN/'instances').glob('*.json'))
    if len(paths)!=500:
        raise ValueError('Exactly 500 original identities required before freezing')
    rows=[normalized_format_evidence(path) for path in paths]
    if any(row['status']!='actor_baseline_admitted' for row in rows):
        raise ValueError('Full baseline preparation has not closed')
    if any(row['actor_head']!=row['official_head'] or row['actor_tree']!=row['official_tree']
           or row['runtime_version']['equal'] is not True
           or row['runtime_version']['official']['version']!=row['runtime_version']['actor']['version']
           or not row['git_ancestry']['allowed_ancestry_only']
           or not row['git_ancestry']['all_refs_within_allowed_ancestry']
           or not row['git_ancestry']['no_unreachable_objects'] for row in rows):
        raise ValueError('A final ancestry or runtime equality gate is missing')
    index_rows=[]
    keys=('instance_id','repo','dataset_base','base_tree','official_image_id','official_image_name',
          'official_manifest_digest','official_head','official_tree','actor_image_id','actor_image_name',
          'actor_config_digest','actor_config_blob','actor_head','actor_tree','policy_sha256','schema',
          'historical_format_exception_policy_sha256','public_python','public_python_details','platform',
          'status','git_ancestry','submodule_ancestry','runtime_version','parent_gitlinks','submodules',
          'target_copy_actions','target_package_copy_paths','removed_public_build_duplicates','completed_at_utc')
    for path,row in zip(paths,rows,strict=True):
        value={key:row[key] for key in keys if key in row}
        value['actor_config_blob']=str(Path(value['actor_config_blob']).relative_to(ROOT))
        data=path.read_bytes()
        value['mapping_reference']={'path':str(path.relative_to(ROOT)),
                                    'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        index_rows.append(value)
    index={'schema':'proworksim.v054.shared-actor-baseline-index-r3-final','created_at_utc':now(),
           'planned_instances':500,'conditions':['REF','MATCH','PROJECT'],
           'official_grading_images_modified':False,'model_calls':0,'images':index_rows}
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'actor-baseline-index-r3.json'
    data=(json.dumps(index,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
    summary={'schema':'proworksim.v054.shared-actor-baseline-completion-r3','created_at_utc':index['created_at_utc'],
             'scope':'Official image assets and shared CPU Actor baseline only; native tools, public test frontend, scorer, model capacity and formal authorization are separate gates.',
             'official_images_loaded':500,'shared_actor_baselines_admitted':500,'planned_instances':500,
             'technical_unknown':0,'model_calls':0,'new_asset_downloads':0,'large_blobs_rehashed':0,
             'official_grading_images_modified':False,'schema_counts':dict(Counter(row['schema'] for row in rows)),
             'policy_counts':dict(Counter(row['policy_sha256'] for row in rows)),
             'all_runtime_versions_equal_official':True,'all_actual_heads_equal_official':True,
             'all_actor_tracked_trees_equal_official_setup_trees':True,'all_allowed_ancestry_only':True,
             'no_unreachable_objects':True,'all_structural_connectivity_admitted':True,
             'full_fsck_returncode_counts':dict(Counter(str(row['git_ancestry']['fsck_returncode']) for row in rows)),
             'historical_format_exception_tasks':sum(row['schema'].endswith('r3.1') for row in rows),
             'fixed_historical_exception_objects':7,
             'historical_format_exception_policy':{'path':'config/v054-historical-git-format-exceptions-r31.json',
                 'sha256':'43f5dd872f7b6b3eb6ebb48441758daef2c590e40e62f971a5983ad05e9c992c'},
             'repo_counts':dict(Counter(row['repo'] for row in rows)),
             'index':{'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)},
             'runtime_state':'runs/software-benchmark-v054/images/actor-admission-r3/state.json',
             'r2_records_retained':True,'original_r3_failure_records_retained':True}
    path=OUT/'actor-baseline-completion-r3.json'
    with path.open('x') as stream:
        stream.write(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
