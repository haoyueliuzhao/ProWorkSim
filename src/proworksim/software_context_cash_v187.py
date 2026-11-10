"""Append an explicit50-CNY amendment without rewriting historical policy/usage."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from .software_benchmark_candidates_v054 import checked,reference

VERSION='v187-context-pilot-add50-same-ledger-r1'
AMENDMENT='v187-user-add50-20261110'
BASE=250_000_000_000
ADDED=50_000_000_000
CAP=BASE+ADDED
ROOT=Path(__file__).resolve().parents[2]
LEDGER=ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'
AUTHORITY=ROOT/'artifacts/software-benchmark-v187/cash-amendment-r1/user-approval.json'

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def authority(ref,path):
    value=json.loads(checked(ref).read_bytes())
    if (value.get('approved') is not True or value.get('amendment_id')!=AMENDMENT
        or value.get('previous_cap_nanoyuan')!=BASE or value.get('added_nanoyuan')!=ADDED
        or value.get('effective_cap_nanoyuan')!=CAP
        or Path(value.get('ledger','')).resolve()!=Path(path).resolve()):
        raise ValueError('Budget amendment differs from the explicit50-CNY authorization')
    return value

def register(path=LEDGER,authority_ref=None):
    path=Path(path).resolve();ref=authority_ref or reference(AUTHORITY);authority(ref,path)
    with sqlite3.connect(path,timeout=60) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if not row or json.loads(row[0])['cap_nanoyuan']!=BASE:raise ValueError('Historical base policy changed')
        policy_sha=hashlib.sha256(row[0].encode()).hexdigest()
        db.execute('CREATE TABLE IF NOT EXISTS cash_amendments_v187('
            'amendment_id TEXT PRIMARY KEY,previous_cap INTEGER,added INTEGER,effective_cap INTEGER,'
            'authority TEXT,base_policy_sha256 TEXT,applied REAL)')
        prior=db.execute('SELECT previous_cap,added,effective_cap,authority,base_policy_sha256 FROM cash_amendments_v187 WHERE amendment_id=?',(AMENDMENT,)).fetchone()
        expected=(BASE,ADDED,CAP,canonical(ref),policy_sha)
        if prior and prior!=expected:raise ValueError('An existing budget amendment cannot be changed or duplicated')
        if not prior:db.execute('INSERT INTO cash_amendments_v187 VALUES(?,?,?,?,?,?,?)',(AMENDMENT,*expected,time.time()))
        db.commit()
    return {'version':VERSION,'amendment_id':AMENDMENT,'registered':True,'already_registered':bool(prior),
        'base_cap_CNY':250,'added_CNY':50,'effective_cap_CNY':300,'authority':ref,
        'historical_policy_sha256':policy_sha,'old_policy_and_request_rows_rewritten':False}

def effective_cap(db,authority_ref=None):
    ref=authority_ref or reference(AUTHORITY)
    row=db.execute('SELECT previous_cap,added,effective_cap,authority,base_policy_sha256 FROM cash_amendments_v187 WHERE amendment_id=?',(AMENDMENT,)).fetchone()
    policy=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
    if (row is None or policy is None or tuple(row)!=(BASE,ADDED,CAP,canonical(ref),hashlib.sha256(policy[0].encode()).hexdigest())):
        raise ValueError('No exact authorized300-CNY admission amendment')
    return CAP
