"""Record a separately scheduled ordinary task, before its workspace or model calls exist."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_fair_pairs_v245 import ROOT, freeze
from proworksim.software_fair_intake_v245 import BANK, EXPOSED
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json


def register(task, job, account):
    source = task.resolve(strict=True)
    row = read_json(source)
    iid = row["instance_id"]
    if iid in {r["instance"] for r in read_json(EXPOSED)["roster"]}:
        raise ValueError("Previously exposed v244 task")
    base = job.resolve()
    if not base.is_relative_to(ROOT / "runs") or base.exists():
        raise ValueError("Expected new ordinary workspace")
    authority = account.resolve(strict=True)
    ledger = Path(read_json(authority)["ledger"]).resolve(strict=True)
    if (
        not ledger.is_relative_to(ROOT / "runs")
        or ledger == ROOT / "runs/software-benchmark-v245/fair-regression-r1/ledger.sqlite"
    ):
        raise ValueError("Ordinary eval must have its own separately authorized funding")
    registry = BANK / "ordinary-registrations"
    registry.mkdir(parents=True, exist_ok=True)
    with (registry / "registration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = [read_json(f) for f in registry.glob("*.json")]
        if any(r["instance"] == iid or Path(r["job_root"]) == base for r in existing):
            raise ValueError("Duplicate prospective identity")
        n = 1 + max([0, *[r["registration_sequence"] for r in existing]])
        path = registry / f"{n:06d}.json"
        freeze(
            path,
            dict(
                source="ordinary",
                registration_sequence=n,
                instance=iid,
                job_root=str(base),
                task=reference(source),
                ledger=str(ledger),
                authority=reference(authority),
            ),
        )
    return path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("task", "job", "account"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    print(register(a.task, a.job, a.account))
