"""Read small endpoint metadata from retained OOM archives; never choose a tree."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import PurePosixPath
import tarfile

from proworksim.software_benchmark_archive_storage_v064 import open_verified_archive
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_managed_recovery_v095 import ROOT, EPISODES

OUTPUT = ROOT/'runs/software-benchmark-v095/OOM-candidate-audit-r1'
NAMES = {'controller-result.json', 'managed-boundary.json', 'model-ledger/ledger.json',
    'ref-ledger/ledger.json', 'sdk-terminal-state.json', 'project-candidates/lock.json',
    'project-candidates/terminal-code/lock.json', 'project-candidates/terminal-code/submission-binding.json',
    'managed-world/world/control/v054-candidate-close.json', 'delivery-evidence.json',
    'project-delivery-snapshot.json'}


def inspect(row):
    index = row['slot_index']
    output = OUTPUT/str(index)
    output.mkdir(parents=True, exist_ok=False)
    result = {'slot_index': index, 'slot_id': row['slot_id'], 'arm': row['arm'],
        'status': 'metadata_review_only', 'candidate_selected': False,
        'model_rerun_required_claimed': False, 'full_repository_extracted': False}
    try:
        metadata = row.get('dead_owner_archive_metadata') or {}
        if not metadata.get('source') or not metadata.get('blob_present'):
            result.update(status='no_trusted_controller_archive_in_inventory',
                          can_grade_from_this_record=False)
        else:
            transfer = json.loads(checked(metadata['source']).read_bytes())
            storage = transfer['storage']
            selected, names = {}, []
            with open_verified_archive(storage) as raw:
                with tarfile.open(fileobj=raw, mode='r|') as archive:
                    for member in archive:
                        path = PurePosixPath(member.name.removeprefix('./'))
                        if not path.parts or path.parts[0] != 'output' or path.is_absolute() or '..' in path.parts:
                            continue
                        relative = '/'.join(path.parts[1:])
                        if relative not in NAMES:
                            continue
                        names.append({'path': relative, 'bytes': member.size, 'regular': member.isfile()})
                        if not member.isfile() or member.size > 4*1024**2:
                            continue
                        if relative in selected:
                            raise ValueError('Duplicate original metadata member')
                        raw_member = archive.extractfile(member).read()
                        value = json.loads(raw_member)
                        target = output/'metadata'/relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        write_new(target, raw_member)
                        selected[relative] = value
            child = selected.get('controller-result.json', {})
            ledger = selected.get('model-ledger/ledger.json', selected.get('ref-ledger/ledger.json', {}))
            lock = selected.get('project-candidates/lock.json', {})
            terminal = selected.get('project-candidates/terminal-code/lock.json', {})
            boundary = selected.get('managed-boundary.json', {})
            result.update(archive_source=metadata['source'], full_archive_verified=True, members=names,
                child_status=child.get('status'), child_error=child.get('error'),
                child_native_finished=child.get('native_finished'), child_normal_completion=child.get('normal_completion'),
                child_terminal_boundary=child.get('terminal_boundary'),
                managed_boundary_status=boundary.get('status'), managed_integrity_failure=boundary.get('execution_integrity_failure'),
                original_managed_lock_present=bool(lock), original_terminal_lock_present=bool(terminal),
                original_managed_candidate_locked_before_grading=lock.get('locked_before_grading'),
                original_managed_close_claim_present='managed-world/world/control/v054-candidate-close.json' in selected,
                submitted=lock.get('submitted'),
                usage={k:ledger.get(k) for k in ('attempts','decisions','known_actual_tokens','complete_actual_tokens','uncertain_reserved_tokens')},
                unresolved_model_request=ledger.get('inflight') is not None,
                source_files={key:reference(output/'metadata'/key) for key in selected})
            known = ledger.get('complete_actual_tokens') is not None and not ledger.get('uncertain_reserved_tokens') and ledger.get('inflight') is None
            if lock and terminal and known:
                result['followup'] = 'verify_locked_managed_candidate_and_administrative_owner_closure'
            elif row['arm']=='REF' and child.get('status')=='closed' and known:
                result['followup'] = 'verify_unique_stopped_REF_worktree_archive_and_original_candidate_claim'
            else:
                result['followup'] = 'retain_unknown; no_code_candidate_selected_by_this_metadata_audit'
        entry = row['original_entry']
        if entry.get('candidate_evidence'):
            retained = json.loads(checked(entry['candidate_evidence']).read_bytes())
            result['original_writer_boundary'] = retained.get('writer_boundary')
            result['original_stopped_worktree_archive'] = retained.get('archives',{}).get('worktree')
            result['original_usage_observation'] = retained.get('usage_observation')
        result['episode_candidate_claim_present'] = (EPISODES/str(index)/'candidate-claim.json').is_file()
    except Exception as error:
        result.update(status='metadata_evidence_unresolved', error={'type':type(error).__name__,'message':str(error)})
    write_new(output/'summary.json', result)
    return result


if __name__=='__main__':
    source=ROOT/'artifacts/software-benchmark-v095/historical-exception-inventory-r1/candidate-review-handoff.json'
    inventory=json.loads(source.read_bytes())
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(inspect,row) for row in inventory['OOM_rows']]
        for future in as_completed(futures):
            row=future.result()
            rows.append(row)
            print(json.dumps({'slot_index':row['slot_index'],'status':row['status'],'followup':row.get('followup')}),flush=True)
    path=ROOT/'artifacts/software-benchmark-v095/OOM-candidate-audit-r1/summary.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    write_new(path,{'version':'v095-OOM-small-endpoint-evidence-review-r1','inventory':reference(source),
        'rows':sorted(rows,key=lambda r:r['slot_index']),'model_calls':0,'Docker_operations':0,
        'full_repository_extraction':False,'scoring_calls':0,'no_automatic_resampling_decision':True})
