"""Run a fully reserved pair from a natural decision checkpoint."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import argparse
import fcntl
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_three_graph_worker_v241 as prior
from inventory_multitype_v242 import PLAN, RUN, save
from proworksim.software_multitype_execution_v242 import Execution, envelope
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json
from proworksim import software_multitype_execution_v242 as mechanism

ROOT = prior.ROOT
NS = "v242.1"


def freeze(path, data):
    if path.exists() and read_json(path) != data:
        raise ValueError("Frozen material differs: " + str(path))
    save(path, data)


def existing():
    state = read_json(prior.DESIGN)["states"][2]
    task = prior.panel_row(state)
    row = next(r for r in prior.sources() if r["id"] == "q11")
    row = {**row, "probe_id": read_json(prior.PREFLIGHT / "references.json")["q11"]["probe_id"]}
    saved = read_json(ROOT / state["source_prefix"] / "checkpoint/manifest.json")
    assert (
        state["checkpoint"] == saved["identity"] == row["provenance"]["checkpoint"]
        and saved["prefix_tokens"] == 5000000 - row["available_tokens"]
    )
    return dict(
        case=state["case"],
        instance=row["instance"],
        kind="A4",
        row=row,
        task=task,
        state=state,
        configuration=task["configuration"],
        checkpoint=state["checkpoint"],
        initial_budget=row["available_tokens"],
        pair_hold_nanoyuan=2 * row["available_tokens"] * 8000,
        score_script=task["scorer_script"],
        score_index=task["source_index"],
    )


def spec_for(item):
    files = [
        reference(f)
        for f in (
            Path(__file__),
            Path(mechanism.__file__),
            Path(mechanism.prompt.__file__),
            Path(prior.paired.episode_module.__file__),
            ROOT / "tools/analyze_multitype_v242.py",
            ROOT / "src/proworksim/software_anomaly_lifecycle_v242.py",
        )
    ]
    return dict(
        roster=[item],
        cap=230000000000,
        block_hold=item["pair_hold_nanoyuan"],
        files=files,
        protocol="Fresh v240.4 OSA within OSA slot; same saved state, 5M inclusive, T1/two workers. No forced changes. Freeze sources before calls, use complete-pair upper-price admission. No C/N updates. No official feedback to workers. Matched official code and delivery endpoints; anomaly state via subsequent observer-visible public receipts, including same-version, same-node evidence. Historical development only.",
    )


def run_branch(item, arm, out):
    class Bound(Execution):
        record = item["row"]

    fn = prior.paired.episode_module.episode
    # A new prefix supplies its original task row and the same immutable checkpoint to both arms.
    design = out.parent / "design.json"
    parents = fn.__globals__
    from proworksim import software_sdk_resume_v203_3_4 as resume

    def read_point(point):
        saved, proof = resume.read(point)
        if "observer" not in saved["control_state"]:
            if proof["identity"] != item["checkpoint"]:
                raise ValueError("Wrong legacy boundary")
            saved = {
                **saved,
                "control_state": {**saved["control_state"], "observer": item["row"]["observer"]},
            }
        return saved, proof

    prior.paired.clone_function(
        fn,
        {
            **parents,
            "RUN": RUN,
            "DESIGN": design,
            "panel_row": lambda _: item["task"],
            "OrganizationExecution": Bound,
            "resume": SimpleNamespace(**{**vars(resume), "read": read_point}),
        },
    )(0, arm, out, False, slot_namespace=NS, expected_case=item["case"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--case", default="SymPy-19954")
    p.add_argument("--arm", choices=prior.ARMS)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    case = a.output.parent.name if a.arm else a.case
    path = PLAN / case / "protocol.json"
    if a.freeze:
        freeze(path, spec_for(existing()))
        return
    spec = read_json(path)
    (item,) = spec["roster"]
    for f in spec["files"]:
        checked(f)
    folder = RUN / case
    if a.arm:
        if a.output.resolve() != folder / a.arm:
            raise ValueError("Wrong branch output")
        run_branch(item, a.arm, a.output)
        return
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (folder / "completed.json").exists():
            return
        prior.check_images(spec)
        (RUN / "tmp").mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(RUN / "tmp")
        auth = read_json(prior.RUN / "authority.json")
        auth.update(scope="v242 multi-type whole pair reservation")
        save(RUN / "authority.json", auth)
        meter = prior.PairedLedger.load(RUN / "authority.json")
        prior.paired.reserve(
            RUN / "authority.json",
            dict(
                case=case,
                account_cap_nanoyuan=spec["cap"],
                arm_limit=item["initial_budget"],
                worst_pair_nanoyuan=item["pair_hold_nanoyuan"],
            ),
            namespace=NS,
            block=NS + ":" + case,
        )
        freeze(folder / "design.json", dict(states=[item["state"]], logical_team_tokens=5000000))

        def branch(arm):
            dest = folder / arm
            result = prior.isolated(Path(__file__).resolve(), ["--arm", arm], dest, "result.json")
            scores = {}
            if result["status"] == "closed":
                for k in ("code", "delivery"):
                    r = prior.isolated(
                        ROOT / "tools" / item["score_script"],
                        ["--index", item["score_index"], "--kind", k, "--episode", dest],
                        folder / (arm + "-" + k),
                        "receipt.json",
                    )
                    scores[k] = {key: r.get(key) for key in ("status", "resolved", "error")}
            return dict(status=result["status"], error=result.get("error"), scores=scores)

        with ThreadPoolExecutor(2) as pool:
            out = dict(zip(prior.ARMS, pool.map(branch, prior.ARMS)))
        save(folder / "completed.json", out)


if __name__ == "__main__":
    main()
