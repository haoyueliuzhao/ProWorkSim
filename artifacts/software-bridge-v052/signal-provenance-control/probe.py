"""One new child signals only its own probe parent; no external PID input."""
import json
import os
from pathlib import Path
import signal
import time

ROOT = Path(__file__).resolve().parent
PARENT_PID = os.getpid()
received = []
def save(name, value):
    path = ROOT / name
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
def on_term(signum, frame):
    received.append({"signal": signum, "receiver_pid": os.getpid(), "received_at": time.time()})
signal.signal(signal.SIGTERM, on_term)
parent_cgroup = Path("/proc/self/cgroup").read_text()
child_pid = os.fork()
if child_pid == 0:
    own_pid, actual_parent = os.getpid(), os.getppid()
    if actual_parent != PARENT_PID or own_pid == PARENT_PID:
        os._exit(71)
    save("sender.json", {"sender_pid": own_pid, "sender_uid": os.getuid(), "receiver_pid": PARENT_PID,
        "actual_parent_pid": actual_parent, "signal": signal.SIGTERM, "planned_send_count": 1,
        "cgroup": Path("/proc/self/cgroup").read_text(), "at": time.time()})
    os.kill(PARENT_PID, signal.SIGTERM)
    os._exit(0)
waited_pid, status = os.waitpid(child_pid, 0)
child_exit = os.waitstatus_to_exitcode(status)
result = {"receiver_pid": PARENT_PID, "receiver_uid": os.getuid(), "new_child_pid": child_pid,
    "waited_pid": waited_pid, "child_exit_code": child_exit, "received": received,
    "cgroup": parent_cgroup, "new_process_only": True,
    "passed": len(received) == 1 and received[0]["signal"] == signal.SIGTERM and child_exit == 0}
save("receiver.json", result)
print(json.dumps(result), flush=True)
raise SystemExit(0 if result["passed"] else 72)
