"""Continue only zero-call old-registry recruitment failures, preserving the original anchor."""

from pathlib import Path
from types import SimpleNamespace
import argparse
import fcntl
import os
import sys
import subprocess
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recruit_multitype_v242 as previous
import run_multitype_worker_v242 as paired
from inventory_multitype_v242 import PLAN, RUN, ROOT, read_json, save
from proworksim import software_registration_bridge_v242 as bridge
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_benchmark_candidates_v054 import reference, checked
from run_offline_scorer_v096 import launch_spec


def cmd(script, *args):
    c, env = launch_spec([str(ROOT / "tools" / script), *args])
    return subprocess.run(c, env=env, cwd=ROOT).returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case")
    p.add_argument("--output", type=Path)
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    cfg = PLAN / "registration-revision.json"
    if a.freeze:
        paired.freeze(
            cfg,
            dict(
                files=[
                    reference(Path(__file__)),
                    reference(Path(bridge.__file__)),
                    reference(PLAN / "recruitment.json"),
                ],
                method="Only before a new common-prefix model call; match each historical tool by semantic name and argument schema, retain its registration identity, add only the three installed public tools in the current SDK order. The original world, prior SDK events, ledger, private role history and source checkpoint are immutable. Both paired branches restore the same newly captured current-schema state. No second attempt if any historical worker generation was sent.",
            ),
        )
        return
    for f in read_json(cfg)["files"]:
        checked(f)
    c0 = read_json(PLAN / "recruitment.json")["candidates"]
    if a.case:
        (c,) = [x for x in c0 if x["case"] + "-r2" == a.case]
        c = {**c, "case": a.case}
        if a.output != RUN / "recruitment" / a.case / "COMMON":
            raise ValueError("Wrong capture root")
        module = SimpleNamespace(
            **{
                **vars(previous.M),
                "resume": SimpleNamespace(
                    **{**vars(previous.M.resume), "restore_runtime": bridge.restore}
                ),
            }
        )
        fn = previous.capture
        paired.prior.paired.clone_function(fn, {**fn.__globals__, "M": module})(c, a.output)
        return
    os.environ["TMPDIR"] = str(RUN / "tmp")
    meter = PairedLedger.load(RUN / "authority.json")
    records = []
    with (RUN / "registration-recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for old in c0:
            case = old["case"]
            receipt = RUN / "recruitment" / case / "admission.json"
            if not receipt.exists() or "zip() argument 2 is longer" not in str(
                read_json(receipt).get("error", "")
            ):
                continue
            with meter.db() as db:
                n = db.execute(
                    "select count(*) from requests where slot=?",
                    ("v242:recruit:" + case + ":COMMON",),
                ).fetchone()[0]
                if n:
                    continue
            c = {**old, "case": case + "-r2"}
            folder = RUN / "recruitment" / c["case"]
            folder.mkdir(parents=True, exist_ok=True)
            if not previous.reserve_capture(c, meter):
                records.append(
                    dict(
                        case=c["case"],
                        status="deferred_cash",
                        worst=(5000000 - c["prefix"]) * 16000,
                    )
                )
                save(RUN / "registration-recruitment-progress.json", records)
                continue
            out = folder / "COMMON"
            res = paired.prior.isolated(
                Path(__file__).resolve(), ["--case", c["case"]], out, "result.json"
            )
            previous.convert(c, meter, res)
            save(folder / "admission.json", res)
            rec = dict(case=c["case"], status=res["status"], error=res.get("error"))
            records.append(rec)
            save(RUN / "registration-recruitment-progress.json", records)
            if res["status"] == "point_ready":
                item = read_json(out / "registered-state.json")
                spec = paired.spec_for(item)
                spec["files"].extend([reference(cfg), reference(out / "registered-state.json")])
                paired.freeze(PLAN / c["case"] / "protocol.json", spec)
                rec["pair_exit"] = cmd("run_multitype_worker_v242.py", "--case", c["case"])
                rec["review_exit"] = cmd("report_successors_v242.py")
                save(RUN / "registration-recruitment-progress.json", records)
        save(RUN / "registration-recruitment-completed.json", records)


if __name__ == "__main__":
    main()
