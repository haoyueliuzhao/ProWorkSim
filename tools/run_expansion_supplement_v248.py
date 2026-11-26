"""One newly registered expansion recruitment window; do not replace any prior prefix."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dynamic_panel_v248_2 as repair
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json

first = repair.first
RUN = repair.ROOT / "runs/software-benchmark-v248/expansion-supplement-r1"
PLAN = repair.ROOT / "artifacts/software-benchmark-v248/expansion-supplement-r1"
NS = "v248.5"
PREFIX = 3_500_000
WINDOW = 80


def slot(i, a):
    return f"{NS}:{i}:{a}"


def register():
    spec = read_json(first.PLAN / "protocol.json")
    maximum = max(r["index"] for r in spec["rows"])
    for r in sorted(read_json(first.BANK)["rows"], key=lambda v: v["index"]):
        if r["index"] <= maximum:
            continue
        folders = sorted(
            (repair.ROOT / "runs/software-benchmark-v217").glob(
                f"*/task-{r['index']:02d}/PREFIX/dynamic-final.json"
            )
        )
        if len(folders) != 1:
            continue
        graph = read_json(folders[0])["work"]
        leaves = [
            k
            for k, v in graph.items()
            if not v["children"] and not v["completion"] and not v.get("depends_on")
        ]
        if len(leaves) >= 2:
            break
    else:
        raise ValueError("No candidate")
    case = dict(
        index=r["index"],
        instance=r["instance_id"],
        initial=2,
        base_commit=r["base_commit"],
        configuration=r["configuration"],
    )
    first.freeze(
        PLAN / "protocol.json",
        dict(
            case=case,
            parent=first.old.reference(first.PLAN / "protocol.json"),
            recruitment_only=first.old.reference(folders[0]),
            historical_open_independent_packages=leaves,
            rule="First index beyond the original six with at least two pending independent leaves in an archived predecision graph. No score selection. Fresh prospective prefix only; historical material never enters the model. Up to 80 actions or 3.5M common tokens. Require a genuinely eligible current graph under the original criterion; otherwise stop. One new candidate, first expansion block only.",
            source=first.old.reference(Path(__file__)),
            revision=first.old.reference(repair.PLAN / "protocol.json"),
            prefix_limit=PREFIX,
            window=WINDOW,
            cash_cap=400,
        ),
    )


def generate(case, arm, out):
    module = SimpleNamespace(
        **{
            **vars(first.M),
            "Actor": repair.Actor,
            "substrate": SimpleNamespace(
                **{**vars(first.M.substrate), "prepare_case": repair.prepare_case}
            ),
        }
    )
    source = inspect.getsource(first.generate)
    # The launch protocol pins this historical function; vary just its recruitment horizon.
    assert source.count("if rt.opportunities >= 32:") == 1
    scope = {
        **vars(first),
        "M": module,
        "RUN": RUN,
        "slot": slot,
        "PREFIX": PREFIX,
        "WINDOW": WINDOW,
    }
    exec(
        compile(
            source.replace("if rt.opportunities >= 32:", "if rt.opportunities >= WINDOW:"),
            __file__ + ":longer-common-window",
            "exec",
        ),
        scope,
    )
    scope["generate"](case, arm, out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--index", type=int)
    p.add_argument("--arm", choices=("COMMON", *first.ARMS))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.freeze:
        register()
    else:
        s = read_json(PLAN / "protocol.json")
        for k in ("source", "parent", "revision"):
            first.old.checked(s[k])
        case = s["case"]
        i = case["index"]
        if a.output:
            if a.index != i or a.output.resolve() != RUN / str(i) / a.arm:
                raise ValueError("Wrong slot")
            generate(case, a.arm, a.output)
        else:
            (RUN / "tmp").mkdir(exist_ok=True, parents=True)
            os.environ["TMPDIR"] = str(RUN / "tmp")
            with (RUN / "coordinator.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                ns = {**vars(first), "RUN": RUN, "slot": slot, "NS": NS, "PREFIX": PREFIX}
                reserve = clone_function(first.reserve, ns)
                allocate = clone_function(first.allocate, ns)
                branch = clone_function(
                    repair.branch, {**vars(repair), "RUN": RUN, "__file__": __file__}
                )
                reserve(i)
                c = branch(case, "COMMON")
                arms = {}
                if c["status"] == "qualified":
                    allocate(
                        i,
                        read_json(RUN / str(i) / "COMMON/checkpoint/manifest.json")[
                            "prefix_tokens"
                        ],
                    )
                    with ThreadPoolExecutor(3) as pool:
                        arms = dict(
                            zip(
                                first.ARMS,
                                pool.map(lambda b: branch(case, b), first.ARMS),
                                strict=True,
                            )
                        )
                else:
                    allocate(i, None)
                first.save(RUN / str(i) / "block.json", dict(common=c, arms=arms))
