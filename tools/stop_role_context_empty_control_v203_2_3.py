"""SIGTERM only the owned, identified Requests empty scorer; use its cleanup."""
import json
import os
from pathlib import Path
import signal

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT/'runs/software-benchmark-v203-2-3/role-context-pilot12-r1/grading/control-psf__requests-1766-empty/request.json'
OUT = ROOT/'artifacts/software-benchmark-v203-2-3/grading-preparation-authorization-r1/empty-stop-intent.json'


def main():
    if os.getuid() == 0 or OUT.exists():
        raise PermissionError('One ordinary-user stop of the exact owned empty control only')
    matches=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid != os.getuid():continue
            args=(path/'cmdline').read_bytes().split(b'\0')
            if bytes(REQUEST) not in args or b'-c' not in args:continue
            if not any(b"PWS_V20323_PREPARATION_GRADING" in arg and b"runpy.run_module" in arg for arg in args):continue
            status=(path/'status').read_text()
            parent=int(next(line for line in status.splitlines() if line.startswith('PPid:')).split()[1])
            parent_args=(Path('/proc')/str(parent)/'cmdline').read_bytes().split(b'\0')
            if not any(arg.endswith(b'tools/recover_role_context_pregrading_bootstrap_v203_2_3.py') for arg in parent_args):continue
            pid=int(path.name)
            if os.getpgid(pid)!=pid:continue
            matches.append((pid,args,parent))
        except (OSError,StopIteration,ValueError):continue
    if len(matches)!=1:raise PermissionError('The exact owned scorer process is not unique')
    pid,args,parent=matches[0]
    value={'pid':pid,'parent_pid':parent,'uid':os.getuid(),'request':str(REQUEST),
           'command':[arg.decode() for arg in args if arg], 'signal':'SIGTERM',
           'reason':'Gold control proved zero-payload repeated upstream connection failure; stop redundant empty test',
           'use_existing_scorer_finally_cleanup':True,'other_processes_touched':False,
           'caller':'root agent explicitly authorized this controlled stop'}
    OUT.write_text(json.dumps(value,indent=2)+'\n')
    if (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')!=args:
        raise PermissionError('Process identity changed before signaling')
    os.kill(pid,signal.SIGTERM)
    print(json.dumps({'SIGTERM_sent_to_owned_scorer':pid,'cleanup_not_yet_claimed':True}))


if __name__=='__main__':main()
