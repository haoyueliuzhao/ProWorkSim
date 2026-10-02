"""Own the bounded run to termination, then archive a read-only status report.

Only this experiment's two report files are committed, using explicit paths.
No experiment retries, new phases, branch switches or unrelated staged changes.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from proworksim.storage import atomic_write, json_bytes

VERSION = "software-development-finisher-v0.28"


def run(plan, run_root, report_repo, *, publish=False):
    source = Path(__file__).resolve().parents[1]
    state_path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "started_at": time.time(), "status": "supervising",
             "run_root": str(run_root), "plan": str(plan), "report_repository": str(report_repo)}
    atomic_write(state_path, json_bytes(state))
    process = subprocess.run([sys.executable, "-m", "scripts.software_development_v028", "supervise",
                              "--plan", str(plan), "--output", str(run_root)], cwd=source, check=False)
    state["supervisor_exit_code"] = process.returncode
    atomic_write(state_path, json_bytes(state))
    if not (run_root / "plan.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        atomic_write(state_path, json_bytes(state))
        return state
    output = report_repo / "docs/experiments"
    done = subprocess.run([sys.executable, "-m", "scripts.report_software_development_v028",
                           "--run-root", str(run_root), "--output-dir", str(output)],
                          cwd=source, check=False)
    state["report_exit_code"] = done.returncode
    state["status"] = "reported" if done.returncode == 0 else "report_failed"
    if publish and done.returncode == 0:
        paths = ["docs/experiments/software-development-v028.md", "docs/experiments/software-development-v028.json"]
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip()
        if branch != "main":
            state["publish_status"] = "not_published_repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *paths], cwd=report_repo, check=True)
            difference = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=report_repo)
            if difference.returncode == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v0.28 software development trajectories and outcomes", "--", *paths],
                               cwd=report_repo, check=True)
            elif difference.returncode != 0:
                raise RuntimeError("Cannot determine the experiment report change set")
            state["report_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=report_repo, text=True).strip()
            pushes = []
            for attempt in range(3):
                pushed = subprocess.run(["git", "push", "origin", "main"], cwd=report_repo,
                                        text=True, capture_output=True, timeout=90)
                pushes.append({"returncode": pushed.returncode, "stdout": pushed.stdout, "stderr": pushed.stderr})
                if pushed.returncode == 0:
                    break
                if attempt < 2:
                    time.sleep(10)
            state.update(publish_status="pushed" if pushes[-1]["returncode"] == 0 else "push_failed", push_attempts=pushes)
    state["ended_at"] = time.time()
    atomic_write(state_path, json_bytes(state))
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--report-repo", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    result = run(args.plan.resolve(), args.run_root.resolve(), args.report_repo.resolve(), publish=args.publish)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
