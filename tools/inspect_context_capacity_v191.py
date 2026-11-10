"""Read retained SDK/boundary evidence for capacity failures; no model rerun."""
import gzip,json,os,tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path,PurePosixPath
from proworksim.software_benchmark_archive_storage_v064 import open_verified_archive
from proworksim.software_benchmark_candidates_v054 import reference

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v191/capacity-audit-r1'
RUN=ROOT/'runs/software-benchmark-v191/capacity-audit-r1'

def inspect(index):
    episode=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1/episodes'/str(index)
    transfer=json.loads((episode/'controller-output-transfer.json').read_bytes());retained=[];events=[];names=[]
    with open_verified_archive(transfer['archive_storage']) as stream:
        with tarfile.open(fileobj=stream,mode='r|') as archive:
            for member in archive:
                if not member.isfile():continue
                name=member.name
                if 'managed-runtime/' not in name:continue
                names.append({'name':name,'bytes':member.size})
                if name.endswith('/experience.jsonl'):
                    for raw in archive.extractfile(member):
                        if not any(marker in raw for marker in (b'model_boundary_error',b'model_budget_stop',b'interface_error',b'policy_error')):continue
                        value=json.loads(raw)
                        if value.get('kind') in {'model_boundary_error','model_budget_stop','interface_error','policy_error'}:events.append(value)
                elif (('sdk-conversations/' in name and name.endswith('.json'))
                    or ('context-management/' in name and name.endswith(('events.jsonl','index.json')))
                    or ('history-summaries/' in name and name.endswith(('failure.json','summary.json','record.json')))):
                    if member.size>8*1024**2:continue
                    parts=PurePosixPath(name)
                    if parts.is_absolute() or '..' in parts.parts:raise ValueError('Archive path escapes analysis output')
                    target=RUN/str(index)/'retained'/name
                    target=target.with_name(target.name+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
                    raw=archive.extractfile(member).read();target.write_bytes(gzip.compress(raw,mtime=0))
                    retained.append({'archive_name':name,'original_bytes':len(raw),'retained':reference(target)})
    value={'slot_index':index,'source_transfer':reference(episode/'controller-output-transfer.json'),
        'archive_verified':True,'boundary_events':events,'retained_files':retained,'member_inventory':names,
        'API_calls':0,'World_actions':0}
    target=OUT/f'{index}.json';target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('inspected',index,'events',len(events),'files',len(retained),flush=True)
    return reference(target)

def main():
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]))
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(inspect,(18111,18138,18108,18141)))
    (OUT/'summary.json').write_text(json.dumps({'cases':results,'new_API_calls':0,'original_archives_changed':False},indent=2)+'\n')

if __name__=='__main__':main()
