"""One 320-CNY envelope for four complete L/G pairs; no cash cut of started work.

Every logical branch includes its common prefix and its own generator. The
prefix is physically paid once. Stage allocations are derived from settled
usage, never from estimates or a renewed five-million-token allowance.
"""
import re
from pathlib import Path
from .software_organization_api_v211 import Ledger as Prior
from .software_organization_api_v204 import Backend,DirectHTTPS,AdmissionStopped
CAP=1_100_000_000_000
ENVELOPE=320_000_000_000
class Ledger(Prior):
 def __init__(self,path):
  self.path=Path(path)
  with self.db() as c:
   if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()!=(str(CAP),):raise ValueError('Existing authorized 1100 ledger required')
   c.execute('CREATE TABLE IF NOT EXISTS v222_panel(id TEXT PRIMARY KEY,status TEXT,hold INTEGER)')
 def reserve_panel(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v222_panel').fetchone():raise ValueError('Panel identity already consumed')
   if c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone() or c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone():raise AdmissionStopped('Prior work must be quiescent')
   if Prior.exposure(self,c)[1]+ENVELOPE>CAP:raise AdmissionStopped('Insufficient complete-pair envelope')
   c.execute('INSERT INTO v222_panel VALUES("four-pairs-r1","active",?)',(ENVELOPE,))
 def used(self,c,slot):
  if c.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()!=('closed',):raise ValueError('Predecessor not settled and closed')
  return c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def reserve_stage(self,slot):
  match=re.fullmatch(r'v222:task-(0[0-3]):(PREFIX|GEN-L|GEN-G|L|G)',slot)
  if not match:raise ValueError('Not one of the frozen four paired identities')
  task,stage=match.groups();base='v222:task-'+task+':'
  with self.db() as c:
   if c.execute('SELECT status FROM v222_panel').fetchone()!=('active',):raise AdmissionStopped('No panel authorization')
   if c.execute('SELECT 1 FROM block_slots WHERE slot=?',(slot,)).fetchone():raise ValueError('Consumed identity: no replay')
   if stage=='PREFIX':limit=2_000_000
   else:
    prefix=self.used(c,base+'PREFIX')
    limit=200_000 if stage.startswith('GEN-') else 5_000_000-prefix-self.used(c,base+'GEN-'+stage)
   if not 0<limit<=5_000_000:raise ValueError('Invalid remaining task allowance')
   c.execute('INSERT INTO block_slots VALUES(?,?,?,"pending")',(slot,'v222-four-pairs',limit))
   return limit
 def exposure(self,c):
  # Full batch envelope already includes each of its stage holds.
  rows=c.execute('SELECT s.status,s.token_limit,s.hold,COALESCE(sum(r.cost),0),COALESCE(sum(r.tokens),0) FROM slots s LEFT JOIN requests r ON s.id=r.slot WHERE s.id NOT LIKE "v222:%" GROUP BY s.id').fetchall()
  estimated=sum(cost if status=='closed' else max(hold,cost) for status,limit,hold,cost,tokens in rows)
  worst=sum(cost if status=='closed' else cost+max(0,limit-tokens)*8000 for status,limit,hold,cost,tokens in rows)
  pending=c.execute('SELECT COALESCE(sum(token_limit),0)*8000 FROM block_slots WHERE status="pending" AND slot NOT LIKE "v222:%"').fetchone()[0]
  cash=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE slot LIKE "v222:%"').fetchone()[0]
  panel=c.execute('SELECT status,hold FROM v222_panel').fetchone();hold=max(cash,panel[1]) if panel and panel[0]=='active' else cash
  return estimated+pending+hold,worst+pending+hold
 def finish(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM slots WHERE id LIKE "v222:%" AND status!="closed"').fetchone():return False
   if c.execute('SELECT 1 FROM block_slots WHERE slot LIKE "v222:%" AND status="pending"').fetchone():return False
   c.execute('UPDATE v222_panel SET status="closed"');return True
 def snapshot(self):
  with self.db() as c:
   spent=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE status="settled"').fetchone()[0]
   rows=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v222:%" GROUP BY status')]
   panel=c.execute('SELECT status,hold/1e9 FROM v222_panel').fetchone();worst=self.exposure(c)[1]
  return {'version':'v222-full-pair-envelope-r1','cap_CNY':1100,'settled_total_CNY_upper':spent/1e9,'remaining_CNY':(CAP-spent)/1e9,'worst_exposure_CNY':worst/1e9,'v222_requests':rows,'v222_envelope':panel}
