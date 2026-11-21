"""Prepare first, then atomically admit every candidate; retain 100 CNY for confirmation."""
import re
from pathlib import Path
from .software_organization_api_v211 import Ledger as Prior
from .software_organization_api_v204 import Backend,DirectHTTPS,AdmissionStopped,PrefixComplete
CAP=1_100_000_000_000;STAGE_CAP=1_000_000_000_000
class Ledger(Prior):
 def __init__(self,path):
  self.path=Path(path)
  with self.db() as c:
   if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()!=(str(CAP),):raise ValueError('Existing 1100 authority required')
   c.execute('CREATE TABLE IF NOT EXISTS v224_batch(id TEXT PRIMARY KEY,status TEXT)')
   c.execute('CREATE TABLE IF NOT EXISTS v224_blocks(id TEXT PRIMARY KEY,status TEXT,token_limit INTEGER,slots TEXT)')
 def reserve_batch(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v224_batch').fetchone():raise ValueError('Batch identity consumed')
   if c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone() or c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone():raise AdmissionStopped('Previous work must be quiescent')
   c.execute('INSERT INTO v224_batch VALUES("development4-r1","active")')
 def _slots(self,i):return [f'v224:task-{i:02d}:'+s for s in ('PREFIX','GRAPH','GENERATOR')]
 def reserve_prep(self,i):
  import json
  if i not in range(4):raise ValueError('Frozen tasks only')
  with self.db() as c:
   if c.execute('SELECT status FROM v224_batch').fetchone()!=('active',):raise AdmissionStopped('No active batch')
   key=f'prep-{i}'
   if c.execute('SELECT 1 FROM v224_blocks WHERE id=?',(key,)).fetchone():raise ValueError('No replay')
   if self.exposure(c)[1]+2_280_000*8000>STAGE_CAP:raise AdmissionStopped('Preparation awaits settled cash')
   c.execute('INSERT INTO v224_blocks VALUES(?,"active",?,?)',(key,2_280_000,json.dumps(self._slots(i))))
 def used(self,c,slot):
  if c.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()!=('closed',):raise ValueError('Predecessor must be settled')
  return c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def reserve_stage(self,slot):
  m=re.fullmatch(r'v224:task-(0[0-3]):(PREFIX|GRAPH|GENERATOR)',slot)
  if not m:raise ValueError('Only preparation stages are reserved here')
  i,stage=m.groups();base='v224:task-'+i+':'
  with self.db() as c:
   if c.execute('SELECT status FROM v224_blocks WHERE id=?',('prep-'+str(int(i)),)).fetchone()!=('active',):raise AdmissionStopped('Preparation not admitted')
   if c.execute('SELECT 1 FROM block_slots WHERE slot=?',(slot,)).fetchone():raise ValueError('No replay')
   if stage!='PREFIX':self.used(c,base+'PREFIX')
   if stage=='GENERATOR':self.used(c,base+'GRAPH')
   n={'PREFIX':2_000_000,'GRAPH':80_000,'GENERATOR':200_000}[stage];c.execute('INSERT INTO block_slots VALUES(?,?,?,"pending")',(slot,'v224-prep-'+i,n));return n
 def stage_remaining(self,slot):
  with self.db() as c:
   row=c.execute('SELECT token_limit,status FROM slots WHERE id=?',(slot,)).fetchone()
   if row is None or row[1]!='active':raise ValueError('Unadmitted stage')
   if c.execute('SELECT 1 FROM requests WHERE slot=? AND status NOT IN ("settled","http_error")',(slot,)).fetchone():raise ValueError('Uncertain request cannot be repeated')
   return row[0]-c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def reserve_panel(self,i,labels,remaining):
  import json
  if not labels or set(labels)-{'KEEP','C1','C2'} or 'KEEP' not in labels or len(set(labels))!=len(labels):raise ValueError('Frozen complete candidate support')
  with self.db() as c:
   actual=sum(self.used(c,s) for s in self._slots(i));assert remaining==5_000_000-actual
   if c.execute('SELECT status FROM v224_blocks WHERE id=?',(f'prep-{i}',)).fetchone()!=('closed',):raise ValueError('Close preparation before panel admission')
   key=f'panel-{i}';slots=[f'v224:task-{i:02d}:'+z for z in labels]
   if c.execute('SELECT 1 FROM v224_blocks WHERE id=?',(key,)).fetchone():raise ValueError('No candidate replay')
   if self.exposure(c)[1]+len(slots)*remaining*8000>STAGE_CAP:raise AdmissionStopped('Whole candidate panel awaits cash')
   c.execute('INSERT INTO v224_blocks VALUES(?,"active",?,?)',(key,len(slots)*remaining,json.dumps(slots)))
   c.executemany('INSERT INTO block_slots VALUES(?,?,?,"pending")',[(s,key,remaining) for s in slots])
 def finish_block(self,key):
  import json
  with self.db() as c:
   row=c.execute('SELECT slots FROM v224_blocks WHERE id=?',(key,)).fetchone()
   if not row:return False
   for s in json.loads(row[0]):
    if c.execute('SELECT 1 FROM slots WHERE id=? AND status!="closed"',(s,)).fetchone() or c.execute('SELECT 1 FROM block_slots WHERE slot=? AND status="pending"',(s,)).fetchone():return False
   c.execute('UPDATE v224_blocks SET status="closed" WHERE id=?',(key,));return True
 def exposure(self,c):
  import json
  other=c.execute('SELECT s.status,s.token_limit,COALESCE(sum(r.cost),0),COALESCE(sum(r.tokens),0) FROM slots s LEFT JOIN requests r ON r.slot=s.id WHERE s.id NOT LIKE "v224:%" GROUP BY s.id').fetchall()
  value=sum(cost if st=='closed' else cost+max(0,n-t)*8000 for st,n,cost,t in other)
  value+=c.execute('SELECT COALESCE(sum(token_limit),0)*8000 FROM block_slots WHERE status="pending" AND slot NOT LIKE "v224:%"').fetchone()[0]
  for state,limit,encoded in c.execute('SELECT status,token_limit,slots FROM v224_blocks'):
   slots=json.loads(encoded);q=','.join('?' for _ in slots);rows=c.execute('SELECT status,cost,tokens FROM requests WHERE slot IN ('+q+')',slots).fetchall();cost=sum(x[1] for x in rows);paid=sum(x[1] for x in rows if x[0]=='settled');tokens=sum(x[2] for x in rows if x[0]=='settled')
   value+=max(cost,paid+max(0,limit-tokens)*8000) if state=='active' else cost
  return value,value
 def finish(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v224_blocks WHERE status="active"').fetchone():return False
   c.execute('UPDATE v224_batch SET status="closed"');return True
 def snapshot(self):
  with self.db() as c:
   paid=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE status="settled"').fetchone()[0];worst=self.exposure(c)[1];rows=list(c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v224:%" GROUP BY status'))
  return {'version':'v224-prepare-and-complete-panels-r1','cap_CNY':1100,'stage_cumulative_cash_ceiling_CNY':1000,'confirmation_preserved_CNY':100,'settled_total_CNY_upper':paid/1e9,'remaining_global_CNY':(CAP-paid)/1e9,'worst_exposure_CNY':worst/1e9,'requests':rows}
