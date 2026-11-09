"""Preserve the closed old ledger and seal the small read-only diagnostic."""
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_probe_v179 import RUN,OLD,ROOT
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter


def main():
    if (RUN/'sources.json').exists():raise ValueError('Do not reseal actual runtime')
    plan=json.loads((RUN/'plan.json').read_bytes())
    log=Path('/tmp/proworksim-v179-probe-cpu.log')
    if '3 passed' not in log.read_text():raise ValueError('Necessary real-driver CPU controls did not pass')
    with sqlite3.connect((OLD/'api-ledger.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0]:raise ValueError('Wait for this ledger active jobs')
        if db.execute("SELECT count(*) FROM requests WHERE status!='settled'").fetchone()[0]:raise ValueError('Preserve prior unknowns explicitly')
    backup=RUN/'previous-ledger-before-v179.sqlite';shutil.copyfile(OLD/'api-ledger.sqlite',backup)
    assert reference(backup)['sha256']==reference(OLD/'api-ledger.sqlite')['sha256']
    tokenizer=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    counter=OfficialDeepSeekCounter(tokenizer,manifest_sha256=reference(tokenizer)['sha256'])
    sizes=[]
    for c in plan['cases']:
        payload=json.loads(Path(c['actual_initial_payload']['path']).read_bytes())
        if c['archive_reference'] not in json.dumps(payload):raise ValueError('A critical reference is not visible')
        if payload['tools'][0]['function']['name']!='context_read' or len(payload['tools'])!=1:raise ValueError('Unexpected executable tool')
        sizes.append(counter.measure(payload)['prompt_tokens'])
    if max(sizes)>98304:raise ValueError('No implicit context truncation')
    spec=importlib.util.spec_from_file_location('local_source_closure',ROOT/'tools/seal_context_replay_v175.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    sources=m.closure([ROOT/'src/proworksim/software_context_probe_v179.py',ROOT/'tools/run_context_probe_v179.py',
        ROOT/'tools/prepare_context_probe_v179.py',Path(__file__)])
    out=ROOT/'artifacts/software-benchmark-v179/recovery-probe-design-r1'
    shutil.copyfile(log,out/'cpu-controls.log')
    value={'plan':reference(RUN/'plan.json'),'files':sources,'old_ledger_before_extension':reference(OLD/'api-ledger.sqlite'),
        'immutable_old_ledger_copy':reference(backup),'visible_critical_refs':12,'CPU_controls':reference(out/'cpu-controls.log'),
        'initial_input_token_estimates':sizes,'no_new_root_or_world_operations':True,
        'protocol':reference(ROOT/'docs/experiments/software-benchmark-v179-recovery-probe-protocol.md')}
    write_new(RUN/'sources.json',value);write_new(out/'sources.json',value)
    print(json.dumps({'sealed':True,'source_files':len(sources),'initial_input_min_max':[min(sizes),max(sizes)]}))


if __name__=='__main__':main()
