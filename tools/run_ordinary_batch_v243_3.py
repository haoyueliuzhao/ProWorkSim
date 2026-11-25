"""Complete the next ordinary tasks from the frozen roster, prioritizing captured pairs between jobs."""

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as ordinary
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_api_v204 import AdmissionStopped
from proworksim.storage import read_json

ROOT = ordinary.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v243-3/ordinary-batch-r1"
RUN = ROOT / "runs/software-benchmark-v243-3/ordinary-batch-r1"
SPEC = PLAN / "protocol.json"
NS = "v243.3"


def register():
    prior = read_json(ordinary.PLAN / "protocol.json")
    done = read_json(ordinary.PLAN / "closeout.json")
    assert done["stages"]["resumed"]["status"] == "closed"
    bank = read_json(ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json")[
        "rows"
    ]
    selected = [c for c in prior["pool"] if c["index"] > prior["case"]["index"]][:2]
    jobs = []
    for case in selected:
        row = next(
            r for r in bank if r["index"] == case["index"] and r["instance_id"] == case["instance"]
        )
        name = case["instance"].split("__")[-1]
        jobs.append(
            dict(
                case=case,
                task=row,
                limit=prior["limit"],
                cap=prior["cap"],
                name=name,
                slot=NS + ":" + name + ":ordinary",
            )
        )
    ordinary.pairs.previous.freeze(
        SPEC,
        dict(
            jobs=jobs,
            parent=reference(ordinary.PLAN / "protocol.json"),
            opening_available=done["available"],
            cap=prior["cap"],
            files=[
                reference(f)
                for f in (
                    Path(__file__),
                    Path(ordinary.__file__),
                    ROOT / "src/proworksim/organization_harness.py",
                    ROOT / "src/proworksim/software_prefix_resume_v243_2.py",
                    ROOT / "src/proworksim/software_registration_bridge_v242.py",
                    ROOT / "src/proworksim/software_event_intake_v243.py",
                    ROOT / "tools/drain_event_pairs_v243.py",
                )
            ],
            design="Next two distinct ordinary completions by frozen v217 index after Django-12663. Independent of scores or anomaly incidence. End at task closure/budget, lock and officially score code and delivery. Drain all eligible natural events at entry and between tasks. Preserve v243 quotas and whole-pair reservation, fixed two workers and 5M logical tokens. No substitute, extra paid observation, membership change or C/N update.",
        ),
    )
    print([(j["name"], (j["limit"] - j["case"]["prefix"]) * 8000) for j in jobs])


def drain():
    command, env = ordinary.launch_spec([str(ROOT / "tools/drain_event_pairs_v243.py")])
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--register", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.register:
        return register()
    spec = read_json(SPEC)
    for f in spec["files"]:
        checked(f)
    if a.output is not None:
        (job,) = [j for j in spec["jobs"] if a.output == RUN / j["name"] / "ordinary"]
        return ordinary.generate(job, a.output)
    RUN.mkdir(parents=True, exist_ok=True)
    pre = ordinary.pairs.previous.prior
    reserve = clone_function(
        pre.paired.reserve, {**pre.paired.reserve.__globals__, "ARMS": ("ordinary",)}
    )
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        drain()
        (RUN / "tmp").mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(RUN / "tmp")
        progress = {}
        for job in spec["jobs"]:
            name = job["name"]
            base = RUN / name
            out = base / "ordinary"
            base.mkdir(exist_ok=True)
            if not (out / "result.json").exists():
                pre.check_images({"roster": [{"configuration": job["task"]["configuration"]}]})
                lim = job["limit"] - job["case"]["prefix"]
                try:
                    reserve(
                        ordinary.AUTH,
                        dict(
                            case=name,
                            account_cap_nanoyuan=job["cap"],
                            arm_limit=lim,
                            worst_pair_nanoyuan=lim * 8000,
                        ),
                        namespace=NS,
                        block=job["slot"],
                    )
                except (ValueError, AdmissionStopped) as exc:
                    if (
                        isinstance(exc, ValueError)
                        and str(exc) != "Insufficient funds for this complete pair"
                    ):
                        raise
                    progress[name] = dict(status="deferred_cash", worst_nanoyuan=lim * 8000)
                    ordinary.save(RUN / "progress.json", progress)
                    continue
            res = pre.isolated(Path(__file__).resolve(), [], out, "result.json")
            scores = {}
            if res["status"] == "closed":
                for k in ("code", "delivery"):
                    r = pre.isolated(
                        ROOT / "tools/score_project_relations_v217_1.py",
                        ["--index", job["case"]["index"], "--kind", k, "--episode", out],
                        base / k,
                        "receipt.json",
                    )
                    scores[k] = dict(status=r.get("status"), resolved=r.get("resolved"))
            progress[name] = dict(status=res["status"], scores=scores, error=res.get("error"))
            ordinary.save(RUN / "progress.json", progress)
            print(name, progress[name], flush=True)
            drain()
        ordinary.save(RUN / "completed.json", progress)


if __name__ == "__main__":
    main()
