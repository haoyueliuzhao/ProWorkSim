"""Read-only metadata plan for byte-identical historical snapshot hardlinks.

Uses retained SHA256 receipts only to shortlist candidates. It does not hash
snapshot payloads, create links, remove files, change ownership, or touch rootfs.
The executor must independently verify bytes and lock each affected closed batch.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'artifacts/software-benchmark-v203-2-1/snapshot-hardlink-plan-r1'
SHA=re.compile(r'[0-9a-f]{64}\Z')
LIMIT=15000


def load_small(path):
    raw=Path(path).read_bytes()
    if len(raw)>2*1024**2:raise ValueError('Metadata exceeds2MiB')
    return json.loads(raw),{'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def file_stat(path):
    s=path.lstat()
    return {'dev':s.st_dev,'ino':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),
        'nlink':s.st_nlink,'size':s.st_size,'allocated_bytes':s.st_blocks*512,
        'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns,
        'regular':stat.S_ISREG(s.st_mode),'symlink':stat.S_ISLNK(s.st_mode)}


def main():
    started=time.time();uid=os.getuid();reasons=Counter();rows=[];batches=[];metadata_count=0
    provenance_paths_seen=0
    for version_root in sorted((ROOT/'runs').glob('software-benchmark-v*')):
        if version_root.is_symlink() or not version_root.is_dir():continue
        for batch in sorted(version_root.iterdir()):
            if batch.is_symlink() or not batch.is_dir() or not (batch/'episodes').is_dir():continue
            if (batch/'episodes').is_symlink():reasons['symlink_episodes_directory']+=1;continue
            active=sorted(str(p) for p in (batch/'resource-claims').glob('active-*.json'))
            batch_row={'path':str(batch),'active_claims':active,'eligible_episodes':0,'candidate_snapshot_paths':0}
            batches.append(batch_row)
            if active:reasons['batch_has_active_claim']+=1;continue
            for episode in sorted((batch/'episodes').iterdir()):
                if episode.is_symlink() or not episode.is_dir():continue
                proofs=[episode/(kind+'-snapshot-provenance.json') for kind in ('baseline','terminal')]
                proofs=[p for p in proofs if p.is_file()]
                if not proofs:continue
                provenance_paths_seen+=len(proofs)
                if provenance_paths_seen>LIMIT:raise RuntimeError('Declared metadata scan bound exceeded')
                try:
                    quiet,qref=load_small(episode/'quiescence.json');metadata_count+=1
                    if (quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
                        or quiet.get('cleanup_errors')!=[] or quiet.get('create_result_unknown') is not False
                        or quiet.get('retained_objects',[])!=[]):
                        reasons['cleanup_not_proven']+=len(proofs);continue
                    result,rref=load_small(episode/'result.json');metadata_count+=1
                    if result.get('status') not in {'closed','technical_unknown','aborted','cancelled','not_started_cancelled'}:
                        reasons['result_not_known_ended']+=len(proofs);continue
                    if result.get('quiescence') not in (None,qref):
                        reasons['result_quiescence_reference_mismatch']+=len(proofs);continue
                except (OSError,ValueError) as error:
                    reasons['missing_or_bad_terminal_metadata']+=len(proofs);continue
                batch_row['eligible_episodes']+=1
                for proof in proofs:
                    try:
                        provenance,pref=load_small(proof);metadata_count+=1
                        ref=provenance['snapshot'];kind=proof.name.split('-')[0];path=episode/(kind+'-snapshot.json')
                        if (ref.get('path')!=str(path) or path.resolve()!=path
                            or not SHA.fullmatch(ref.get('sha256','')) or type(ref.get('bytes')) is not int):
                            reasons['noncanonical_snapshot_reference']+=1;continue
                        info=file_stat(path)
                        if not info['regular'] or info['symlink'] or info['uid']!=uid:
                            reasons['foreign_or_nonregular_snapshot']+=1;continue
                        if info['size']!=ref['bytes']:
                            reasons['snapshot_size_mismatch']+=1;continue
                        row={'path':str(path),'snapshot':ref,'kind':kind,'provenance':pref,
                            'batch':str(batch),'episode':str(episode),'episode_status':result['status'],
                            'quiescence':qref,'result':rref,'stat':info}
                        if kind=='baseline':
                            store=batch/'content/baselines'/(ref['sha256']+'.json')
                            if store.is_file() and not store.is_symlink():
                                si=file_stat(store)
                                if si['dev']==info['dev'] and si['ino']==info['ino']:
                                    row['known_content_store_alias']={'path':str(store),'stat':si,
                                      'included_in_primary_episode_only_plan':False}
                        rows.append(row);batch_row['candidate_snapshot_paths']+=1
                    except (OSError,ValueError,KeyError,TypeError):reasons['missing_or_bad_snapshot_metadata']+=1
    # A contradictory retained digest for one inode is not a dedupe candidate.
    inode_hashes=defaultdict(set)
    for row in rows:inode_hashes[(row['stat']['dev'],row['stat']['ino'])].add(row['snapshot']['sha256'])
    conflicts={key for key,hashes in inode_hashes.items() if len(hashes)>1}
    groups=defaultdict(list)
    for row in rows:
        s=row['stat'];key=(s['dev'],s['ino'])
        if key in conflicts:reasons['inode_digest_conflict']+=1;continue
        groups[(row['snapshot']['sha256'],row['snapshot']['bytes'],s['dev'],s['uid'],s['gid'],s['mode'])].append(row)
    plans=[];single_inode_groups=0;total_primary=total_with_store=0
    for (sha,size,dev,owner,gid,mode),members in groups.items():
        inodes=defaultdict(list)
        for row in members:inodes[row['stat']['ino']].append(row)
        if len(inodes)<2:single_inode_groups+=1;continue
        records=[]
        for inode,paths in inodes.items():
            first=paths[0];s=first['stat'];aliases={r['path']:r for r in paths}
            stores={r['known_content_store_alias']['path']:r['known_content_store_alias'] for r in paths if 'known_content_store_alias' in r}
            records.append({'inode':inode,'stat':s,'episode_paths':list(aliases.values()),
                'content_store_aliases':list(stores.values()),'known_episode_links':len(aliases),
                'known_episode_and_store_links':len(aliases)+len(stores),
                'unresolved_hardlink_count':max(0,s['nlink']-len(aliases)-len(stores)),
                'all_links_known_episode_only':s['nlink']==len(aliases),
                'all_links_known_including_store':s['nlink']==len(aliases)+len(stores)})
        # Keep a source inode whose external/unselected links would prevent
        # reclaim anyway; otherwise keep the least allocated inode.
        records.sort(key=lambda r:(r['all_links_known_including_store'],r['all_links_known_episode_only'],
                                   r['stat']['allocated_bytes'],r['episode_paths'][0]['path']))
        keep=records[0];replace=records[1:]
        primary=sum(r['stat']['allocated_bytes'] for r in replace if r['all_links_known_episode_only'])
        store=sum(r['stat']['allocated_bytes'] for r in replace if r['all_links_known_including_store'])
        total_primary+=primary;total_with_store+=store
        plans.append({'sha256':sha,'bytes':size,'device':dev,'uid':owner,'gid':gid,'mode':mode,
            'source':keep,'replace_inodes':replace,'inode_count':len(records),'episode_path_count':len(members),
            'reclaimable_episode_paths_only_bytes':primary,
            'reclaimable_including_known_store_aliases_bytes':store,
            'snapshot_payload_hashes_recomputed':False})
    plans.sort(key=lambda p:p['reclaimable_including_known_store_aliases_bytes'],reverse=True)
    summary={'version':'v203.2.1-readonly-snapshot-hardlink-plan-r1','created_unix':started,
        'elapsed_seconds':time.time()-started,'uid':uid,'metadata_files_read':metadata_count,
        'provenance_paths_seen':provenance_paths_seen,'accepted_snapshot_paths':len(rows),
        'duplicate_groups_with_distinct_inodes':len(plans),'already_single_inode_groups':single_inode_groups,
        'groups_whose_keeper_has_unresolved_hardlink_aliases':sum(bool(g['source']['unresolved_hardlink_count']) for g in plans),
        'reclaimable_episode_paths_only_bytes':total_primary,'reclaimable_episode_paths_only_GiB':total_primary/1024**3,
        'reclaimable_including_known_store_aliases_bytes':total_with_store,
        'reclaimable_including_known_store_aliases_GiB':total_with_store/1024**3,
        'exclusions':dict(reasons),'scanned_batches':batches,
        'payload_file_reads_or_rehashes':0,'old_file_mutations':0,'Docker_API_or_service_operations':0,
        'estimate_not_actual_reclaimed_space':True,
        'requirements_before_execution':['Recheck no active owners and quiescence under appropriate owned locks',
          'Verify every affected distinct source/target inode against retained SHA and actual byte equality',
          'Recheck lstat UID/device/mode/size/nlink/ino immediately before linking/replacing',
          'Only link same-device identical content and metadata-permission class',
          'Replace all aliases to a losing inode to reclaim its blocks; unknown aliases prevent counted reclaim',
          'Record changed inode/ctime/nlink and target mtime inheritance; keep paths/bytes/hash/provenance unchanged',
          'Keep replacement atomic and directory-fsync; never modify the shared inode contents',
          'A keeper with unresolved hardlink aliases needs independent no-writer/immutability proof or a different fully known keeper; its aliases must not be assumed safe merely from one closed episode.'],
        'reference_compatibility':'Hardlinking keeps the same absolute paths and Path.resolve outputs, unlike cross-disk symlinks.',
        'mtime_boundary':'Target path inherits the keeper inode mtime; independent per-path mtime preservation is impossible for shared hardlinks. Keeper and all aliases gain ctime/nlink changes.'}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'plan.json').write_text(json.dumps({'summary':summary,'groups':plans},ensure_ascii=False,indent=2)+'\n')
    (OUTPUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['scanned_batches','requirements_before_execution']},ensure_ascii=False))
    print(json.dumps({'top_groups':[{'sha256':g['sha256'],'size':g['bytes'],'inodes':g['inode_count'],
        'episode_only_GiB':g['reclaimable_episode_paths_only_bytes']/1024**3,
        'including_store_GiB':g['reclaimable_including_known_store_aliases_bytes']/1024**3,
        'source':g['source']['episode_paths'][0]['path']} for g in plans[:8]]},ensure_ascii=False))


if __name__=='__main__':main()
