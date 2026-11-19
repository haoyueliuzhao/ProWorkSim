"""Exercise exact adoption refresh against the real non-reentrant capacity lock."""
import ast,threading
from pathlib import Path
from proworksim.software_organization_capacity_v212 import Capacity

def test_existing_running_child_refresh_does_not_nest_lock():
 source=Path('tools/run_streaming_confirmation_v217_2_r2.py').read_text()
 tree=ast.parse(source);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
 refresh=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='refresh')
 cap=Capacity(lambda:None);cap.leases['inherited:/episode']={'starting':True}
 scope={'cap':cap,'inherited':{'/episode':{'pid':1}},'same_alive':lambda p:True,'read':lambda p:{'status':'running'},'Path':Path}
 exec(compile(ast.Module(body=[refresh],type_ignores=[]),'<exact-refresh>','exec'),scope)
 t=threading.Thread(target=scope['refresh'],daemon=True);t.start();t.join(1)
 assert not t.is_alive();assert cap.leases['inherited:/episode']['starting'] is False
 scope['same_alive']=lambda p:False;scope['refresh']();assert not cap.leases
