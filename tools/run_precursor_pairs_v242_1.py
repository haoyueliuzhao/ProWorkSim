"""Prospectively capture new v242 states after a precursor already visible at an archived anchor."""

import argparse
from collections import defaultdict
import fcntl
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recruit_multitype_v242 as previous
import run_multitype_worker_v242 as paired
from inventory_multitype_v242 import ROOT, history, save, read_json
from proworksim.software_anomaly_graph_v226 import AnomalyGraph, EDITS
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim import software_registration_bridge_v242 as registry

PLAN = ROOT / "artifacts/software-benchmark-v242-1/precursors-r1"
RUN = ROOT / "runs/software-benchmark-v242-1/precursors-r1"
LIMIT = 16
TRIAL = PLAN / "protocol.json"
clone = paired.prior.paired.clone_function


def indicators(r):
    graphs = {m: AnomalyGraph(m) for m in ("member_001", "member_002")}
    edits = defaultdict(dict)
    dependencies = {}
    for h in history(ROOT / r["source"]):
        i, o = h["ordinal"], h["outcome"]
        who = o.get("worker_id")
        if i > r["ordinal"] or who not in graphs:
            continue
        graphs[who].observe(i, o)
        a = o.get("decision") or {}
        resp = o.get("response") or {}
        if not resp.get("ok"):
            continue
        args = a.get("arguments") or {}
        if a.get("action") in EDITS:
            for path in (resp.get("result") or {}).get("paths") or [args.get("path")]:
                if path:
                    edits[who][path] = i
        if a.get("action") == "change_dependency":
            key = args["task_id"], args["depends_on"]
            if args.get("operation") == "add":
                dependencies[key] = i
            elif args.get("operation") == "remove":
                dependencies.pop(key, None)
    refs = []
    for g in graphs.values():
        for (task, target), failures in g.failures.items():
            if task and len(failures) == 1:
                _, test = next(iter(failures.values()))
                refs.append(
                    dict(
                        kind="A1",
                        ordinal=test["opportunity"],
                        actor=g.observer,
                        task=task,
                        target=target,
                        command=test["command_id"],
                    )
                )
    for (task, parent), i in dependencies.items():
        refs.append(dict(kind="A2", ordinal=i, task=task, upstream=parent))
    for path in edits["member_001"].keys() & edits["member_002"].keys():
        refs.append(dict(kind="A3", ordinal=max(e[path] for e in edits.values()), path=path))
    return refs


def register():
    old = read_json(paired.PLAN / "recruitment.json")["candidates"]
    used = {c["task"]["instance_id"] for c in old} | {
        "astropy__astropy-14182",
        "sphinx-doc__sphinx-9591",
        "sympy__sympy-19954",
    }
    roster = read_json(ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json")[
        "rows"
    ]
    lookup = {r["instance_id"]: r for r in roster}
    screened = []
    for r in read_json(paired.PLAN / "checkpoint-inventory.json")["records"]:
        if "/software-benchmark-v217/" not in r["source"] or r["instance"] in used:
            continue
        refs = indicators(r)
        screened.append(
            dict(
                instance=r["instance"],
                source=r["source"],
                checkpoint=r["checkpoint"],
                prefix=r["prefix_tokens"],
                ordinal=r["ordinal"],
                indicators=refs,
            )
        )
    qualified = []
    for r in screened:
        for kind in ("A2", "A3", "A1"):
            markers = [m for m in r["indicators"] if m["kind"] == kind]
            if markers and r["prefix"] + 8 * paired.mechanism.CALL_BOUND < 5000000:
                # Priority to uncovered dependency/integration. Within type: freshest evidence.
                qualified.append(
                    (
                        ("A2", "A3", "A1").index(kind),
                        r["ordinal"] - max(m["ordinal"] for m in markers),
                        r["instance"],
                        r["source"],
                        kind,
                        r,
                    )
                )
    chosen = []
    repos = set()
    for _, gap, _, _, kind, r in sorted(qualified, key=lambda x: x[:4]):
        row = lookup[r["instance"]]
        if row["repo"] in repos:
            continue
        repos.add(row["repo"])
        chosen.append(
            dict(
                case="p242b-" + r["instance"].split("__")[-1],
                kind=kind,
                checkpoint=r["checkpoint"],
                source=r["source"],
                prefix=r["prefix"],
                task=row,
                score_index=row["index"],
                score_script="score_project_relations_v217_1.py",
                anchor_ordinal=r["ordinal"],
                precursor_age=gap,
            )
        )
        if len(chosen) == 2:
            break
    paired.freeze(
        TRIAL,
        dict(
            candidates=chosen,
            screening=screened,
            max_new_opportunities=LIMIT,
            method="Two distinct repositories maximum, oldest-source lexicographic tiebreak after type priority and precursor freshness. Only native v217 task/scorer registry. No prior v241/v242 tasks, no future receipts or grades. A single failed target, declared upstream dependency or two members editing the same path selects a window only. Live capture still requires the original v242 native anomaly receipts and sufficient remaining budget. Up to 16 fresh opportunities per anchor. No added instructions. Full pair worst-price admission before recruitment, same 5M logical share per arm; no repeat of paid calls. No personnel or C/N changes.",
            files=[
                reference(Path(__file__)),
                reference(Path(previous.__file__)),
                reference(Path(registry.__file__)),
                reference(Path(paired.__file__)),
                reference(Path(paired.mechanism.__file__)),
            ],
        ),
    )
    print([(c["case"], c["kind"], c["precursor_age"]) for c in chosen], flush=True)


def capture(c, dest):
    native = previous.M.native

    def limited(prepared, runtime, *, on_opportunity):
        start = runtime.opportunities

        def observe(o):
            on_opportunity(o)
            if not prepared.world.protocol()["terminal"] and runtime.opportunities - start >= LIMIT:
                raise previous.StopPrefix()

        return native.run_fragment(prepared, runtime, on_opportunity=observe)

    m = SimpleNamespace(
        **{
            **vars(previous.M),
            "resume": SimpleNamespace(
                **{**vars(previous.M.resume), "restore_runtime": registry.restore}
            ),
            "native": SimpleNamespace(**{**vars(native), "run_fragment": limited}),
        }
    )
    clone(previous.capture, {**previous.capture.__globals__, "M": m, "RUN": RUN})(c, dest)


def pair():
    branch = clone(paired.run_branch, {**paired.run_branch.__globals__, "RUN": RUN})
    clone(
        paired.main,
        {
            **paired.main.__globals__,
            "RUN": RUN,
            "PLAN": PLAN,
            "__file__": __file__,
            "run_branch": branch,
        },
    )()


def run(candidates):
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "tmp").mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    paired.freeze(RUN / "authority.json", read_json(paired.RUN / "authority.json"))
    meter = PairedLedger.load(RUN / "authority.json")
    with (RUN / "schedule.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for c in candidates:
            folder = RUN / "recruitment" / c["case"]
            folder.mkdir(parents=True, exist_ok=True)
            status = folder / "admission.json"
            if status.is_file():
                res = read_json(status)
            else:
                if not previous.reserve_capture(c, meter):
                    save(status, dict(status="deferred_cash"))
                    continue
                res = paired.prior.isolated(
                    Path(__file__).resolve(),
                    ["--capture", c["case"]],
                    folder / "COMMON",
                    "result.json",
                )
                previous.convert(c, meter, res)
                save(status, res)
            if res["status"] == "point_ready":
                item = read_json(folder / "COMMON/registered-state.json")
                spec = paired.spec_for(item)
                spec["files"].extend(
                    [reference(TRIAL), reference(folder / "COMMON/registered-state.json")]
                )
                paired.freeze(PLAN / c["case"] / "protocol.json", spec)
                import subprocess
                from run_offline_scorer_v096 import launch_spec

                command, env = launch_spec([str(Path(__file__).resolve()), "--case", c["case"]])
                subprocess.run(command, cwd=ROOT, env=env, check=True)
            print(c["case"], res["status"], flush=True)
        save(
            RUN / "completed.json",
            {
                c["case"]: read_json(RUN / "recruitment" / c["case"] / "admission.json")["status"]
                for c in candidates
            },
        )


if __name__ == "__main__":
    if "--register" in sys.argv:
        register()
    else:
        spec = read_json(TRIAL)
        for f in spec["files"]:
            checked(f)
        if "--arm" in sys.argv or "--case" in sys.argv:
            pair()
        else:
            p = argparse.ArgumentParser()
            p.add_argument("--capture")
            p.add_argument("--output", type=Path)
            args = p.parse_args()
            if args.capture:
                (c,) = [r for r in spec["candidates"] if r["case"] == args.capture]
                if args.output != RUN / "recruitment" / args.capture / "COMMON":
                    raise ValueError("Invalid capture destination")
                capture(c, args.output)
            else:
                run(spec["candidates"])
