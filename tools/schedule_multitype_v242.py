"""Sequential cash admission and asynchronous scoring within each pair; gaps stay gaps."""

from pathlib import Path
import fcntl
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recruit_multitype_v242 as recruit
from run_offline_scorer_v096 import launch_spec
from inventory_multitype_v242 import PLAN, RUN, ROOT, read_json, save


def call(script, *args):
    cmd, env = launch_spec([str(ROOT / "tools" / script), *args])
    return subprocess.run(cmd, env=env, cwd=ROOT).returncode


def main():
    os.environ["TMPDIR"] = str(RUN / "tmp")
    with (RUN / "recruitment-schedule.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = []
        for c in read_json(PLAN / "recruitment.json")["candidates"]:
            case = c["case"]
            status = call("recruit_multitype_v242.py", "--case", case)
            receipt = RUN / "recruitment" / case / "admission.json"
            record = dict(
                case=case,
                prefix_status=read_json(receipt)["status"]
                if receipt.exists()
                else "technical_unknown",
                returncode=status,
            )
            rows.append(record)
            save(RUN / "recruitment-progress.json", rows)
            if record["prefix_status"] == "point_ready":
                record["pair_returncode"] = call("run_multitype_worker_v242.py", "--case", case)
                record["pair"] = (
                    read_json(RUN / case / "completed.json")
                    if (RUN / case / "completed.json").exists()
                    else None
                )
                record["review_returncode"] = call("analyze_multitype_v242.py")
                save(RUN / "recruitment-progress.json", rows)
        save(RUN / "recruitment-completed.json", rows)


if __name__ == "__main__":
    main()
