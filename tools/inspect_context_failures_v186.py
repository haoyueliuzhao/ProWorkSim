"""Read retained stopped-controller archives, without model or world execution."""
import json,os,tarfile
from pathlib import Path
from proworksim.software_benchmark_archive_storage_v064 import open_verified_archive
from proworksim.software_benchmark_candidates_v054 import reference,write_new
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v186/context-failure-analysis-r1'

def main():
 os.sched_setaffinity(0,{46,47});OUT.mkdir(parents=True,exist_ok=True)
 rows=[]
 for index in (18108,18141):
  folder=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1/episodes'/str(index)
  transfer=json.loads((folder/'controller-output-transfer.json').read_bytes())
  storage=transfer['archive_storage'];errors=[];summary_failures=[]
  with open_verified_archive(storage) as stream:
   with tarfile.open(fileobj=stream,mode='r|') as archive:
    for member in archive:
     if not member.isfile():continue
     if member.name.endswith('managed-runtime/experience.jsonl'):
      for raw in archive.extractfile(member):
       value=json.loads(raw)
       if value.get('kind') in {'interface_error','model_error','policy_error','context_error'}:errors.append(value)
     elif '/history-summaries/' in member.name and member.name.endswith('/failure.json'):
      summary_failures.append({'path':member.name,'value':json.load(archive.extractfile(member))})
   for _ in iter(lambda:stream.read(1024*1024),b''):pass
  result={'slot_index':index,'interface_errors':errors,'summary_failures':summary_failures,
   'source_transfer':reference(folder/'controller-output-transfer.json'),'new_API_calls':0,'new_world_actions':0}
  ref=write_new(OUT/f'{index}.json',result);rows.append(ref)
  print(json.dumps({'slot_index':index,'errors':errors[-2:],'summary_failures':summary_failures[-2:]},ensure_ascii=False),flush=True)
 write_new(OUT/'summary.json',{'cases':rows,'new_model_calls':0})
if __name__=='__main__':main()
