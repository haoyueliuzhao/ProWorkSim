"""Bind the approved pair to the fixed -P loader; original launch issued zero model calls."""
import argparse
from pathlib import Path
import sys

TOOLS=Path(__file__).resolve().parent
sys.path.insert(0,str(TOOLS))
import run_active_diagnosis_pair_v228_2 as batch
from proworksim.software_fixed_organization_clone_v131 import clone_function

PLAN=batch.ROOT/'artifacts/software-benchmark-v228/diagnosis-supplement-launch-r2'
RUN=batch.RUN.with_name('astropy-evidence-r2-launch2')
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-pair',action='store_true')
    parser.add_argument('--index',type=int);parser.add_argument('--condition',choices=batch.ARMS)
    parser.add_argument('--output',type=Path);parser.add_argument('--prefix',type=Path)
    args=parser.parse_args()
    if args.run_pair:
        import sqlite3
        with sqlite3.connect(f'file:{batch.DB}?mode=ro',uri=True) as db:
            slots=tuple(f'v228:{batch.RUN.name}:{a}' for a in batch.ARMS)
            if db.execute('SELECT count(*) FROM slots WHERE id IN (?,?)',slots).fetchone()!=(0,):
                raise ValueError('First deployment entered a model slot')
            if db.execute('SELECT count(*) FROM requests WHERE slot IN (?,?)',slots).fetchone()!=(0,):
                raise ValueError('Consumed model identity')
        clone_function(batch.run_pair,{**batch.run_pair.__globals__,'PLAN':PLAN,'RUN':RUN,'ENTRY':Path(__file__).name})()
    else:
        row,=batch.read_json(PLAN/'panel.json')['rows']
        if args.index!=0 or args.condition not in batch.ARMS or args.output!=RUN/args.condition or args.prefix!=Path(row['archived_prefix']):
            parser.error('Unexpected continuation identity')
        clone_function(batch.episode,{**batch.episode.__globals__,'PLAN':PLAN})(args)
