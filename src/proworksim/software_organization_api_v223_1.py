"""Whole-pair admission against existing cash; independently release closed pairs."""
import re
from pathlib import Path
from .software_organization_api_v211 import Ledger as Prior
from .software_organization_api_v204 import Backend,DirectHTTPS,AdmissionStopped
CAP=1_100_000_000_000;PAIR_HOLD=80_000_000_000
class Ledger(Prior):
 def __init__(self,path):
  self.path=Path(path)
  with self.db() as c:
   if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()!=(str(CAP),):raise ValueError('Existing authorized cash authority required')
   c.execute('CREATE TABLE IF NOT EXISTS v223_1_panel(id TEXT PRIMARY KEY,status TEXT)')
   c.execute('CREATE TABLE IF NOT EXISTS v223_1_pairs(task INTEGER PRIMARY KEY,status TEXT,hold INTEGER)')
 def reserve_panel(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v223_1_panel').fetchone():raise ValueError('New batch identity already consumed')
   if c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone() or c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone():raise AdmissionStopped('Prior batches must be settled')
   c.execute('INSERT INTO v223_1_panel VALUES("four-pairs-r1","active")')
 def reserve_pair(self,index):
  if index not in range(4):raise ValueError('Frozen four tasks only')
  with self.db() as c:
   if c.execute('SELECT status FROM v223_1_panel').fetchone()!=('active',):raise AdmissionStopped('No active batch')
   if c.execute('SELECT 1 FROM v223_1_pairs WHERE task=?',(index,)).fetchone():raise ValueError('Pair identity already consumed')
   if self.exposure(c)[1]+PAIR_HOLD>CAP:raise AdmissionStopped('Wait for settled headroom; do not interrupt active work')
   c.execute('INSERT INTO v223_1_pairs VALUES(?,"active",?)',(index,PAIR_HOLD))
 def used(self,c,slot):
  if c.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()!=('closed',):raise ValueError('Predecessor must be settled')
  return c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def reserve_stage(self,slot):
  m=re.fullmatch(r'v223\.1:task-(0[0-3]):(PREFIX|GRAPH|GEN-W0|GEN-W1|W0|W1)',slot)
  if not m:raise ValueError('Frozen stage required')
  task,stage=m.groups();base='v223.1:task-'+task+':'
  with self.db() as c:
   if c.execute('SELECT status FROM v223_1_pairs WHERE task=?',(int(task),)).fetchone()!=('active',):raise AdmissionStopped('No complete pair reservation')
   if c.execute('SELECT 1 FROM block_slots WHERE slot=?',(slot,)).fetchone():raise ValueError('No stage replay')
   if stage=='PREFIX':limit=2_000_000
   else:
    p=self.used(c,base+'PREFIX');h=0 if stage=='GRAPH' else self.used(c,base+'GRAPH')
    limit=80_000 if stage=='GRAPH' else 200_000 if stage.startswith('GEN-') else 5_000_000-p-h-self.used(c,base+'GEN-'+stage)
   if not 0<limit<=5_000_000:raise ValueError('Invalid remaining allocation')
   c.execute('INSERT INTO block_slots VALUES(?,?,?,"pending")',(slot,'v223.1-pair-'+task,limit));return limit
 def exposure(self,c):
  other=c.execute('SELECT s.status,s.token_limit,s.hold,COALESCE(sum(r.cost),0),COALESCE(sum(r.tokens),0) FROM slots s LEFT JOIN requests r ON s.id=r.slot WHERE s.id NOT LIKE "v223.1:%" GROUP BY s.id').fetchall()
  worst=sum(cost if state=='closed' else cost+max(0,limit-tokens)*8000 for state,limit,hold,cost,tokens in other)
  worst+=c.execute('SELECT COALESCE(sum(token_limit),0)*8000 FROM block_slots WHERE status="pending" AND slot NOT LIKE "v223.1:%"').fetchone()[0]
  for task,state,hold in c.execute('SELECT task,status,hold FROM v223_1_pairs'):
   base=f'v223.1:task-{task:02d}:'
   cost=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE slot LIKE ?',(base+'%',)).fetchone()[0]
   if state=='active':
    paid,tokens=c.execute('SELECT COALESCE(sum(cost),0),COALESCE(sum(tokens),0) FROM requests WHERE slot LIKE ? AND status="settled"',(base+'%',)).fetchone()
    common=c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot IN (?,?) AND status="settled"',(base+'PREFIX',base+'GRAPH')).fetchone()[0]
    # P/H is paid once but charged to both 5M logical branches. Only settled
    # usage reduces this bound; in-flight/unknown calls remain inside it.
    worst+=max(cost,paid+max(0,10_000_000-common-tokens)*8000)
   else:worst+=cost
  return worst,worst
 def finish_pair(self,index):
  like=f'v223.1:task-{index:02d}:%'
  with self.db() as c:
   if not c.execute('SELECT 1 FROM v223_1_pairs WHERE task=?',(index,)).fetchone():return False
   if c.execute('SELECT 1 FROM slots WHERE id LIKE ? AND status!="closed"',(like,)).fetchone() or c.execute('SELECT 1 FROM block_slots WHERE slot LIKE ? AND status="pending"',(like,)).fetchone():return False
   c.execute('UPDATE v223_1_pairs SET status="closed" WHERE task=?',(index,));return True
 def active_pairs(self):
  with self.db() as c:return c.execute('SELECT count(*) FROM v223_1_pairs WHERE status="active"').fetchone()[0]
 def finish(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v223_1_pairs WHERE status="active"').fetchone():return False
   c.execute('UPDATE v223_1_panel SET status="closed"');return True
 def snapshot(self):
  with self.db() as c:
   spent=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE status="settled"').fetchone()[0]
   rows=[dict(zip(('status','requests','tokens','cost_CNY_upper'),x)) for x in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v223.1:%" GROUP BY status')]
   pairs=list(c.execute('SELECT task,status,hold/1e9 FROM v223_1_pairs'));worst=self.exposure(c)[1]
  return {'version':'v223.1-complete-pair-cash-r1','cap_CNY':1100,'settled_total_CNY_upper':spent/1e9,'remaining_CNY':(CAP-spent)/1e9,'worst_exposure_CNY':worst/1e9,'requests':rows,'pairs':pairs}
