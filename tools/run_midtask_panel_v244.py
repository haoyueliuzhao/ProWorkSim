"""A fixed-progress decision opportunity, using the existing v243 policy and ordinary worker harness."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
from pathlib import Path
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as ordinary
from prepare_midtask_panel_v244 import ROOT
from prepare_osa_states_v236 import evidence
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_graph_budget_v229 import WindowLedger
from proworksim.software_graph_controller_v228 import menu, PROJECT
from proworksim.software_prefix_resume_v243_2 import release_on_ordinary_entry
from proworksim.software_review_handoff_v243_1 import Execution
from proworksim.software_three_graph_v240 import build
from proworksim.storage import read_json, digest, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v244/midtask15-r1"
RUN = ROOT / "runs/software-benchmark-v244/midtask15-r1"
AUTH = RUN / "authority.json"
ARMS = ("KEEP", "OSA")
NS = "v244"
pre = ordinary.pairs.previous.prior
save = ordinary.save


def decision(execution, rt, arm, case, out):
    world = rt.prepared.world
    observer = rt.fixed_spec["delivery_member"]
    # Both arms take the same authorized, read-only delivery-readiness view at the fork.
    view = world._action_delivery_readiness(observer, PROJECT)
    rid = digest(json_bytes([case["checkpoint"], observer, "delivery_readiness", view]))
    receipt = dict(
        command_id=rid, tool="delivery_readiness", actor_id=observer, opportunity=rt.opportunities
    )
    work = world.dynamic()["work"]
    targets = sorted(t for t, w in work.items() if not w["children"])
    node = dict(
        anomaly_id="scheduled-" + rid[:16],
        anomaly_type="scheduled_review",
        subject=None,
        affected_work=targets,
        evidence_refs=[receipt],
    )
    frozen = menu(world, node, observer)
    public = evidence(
        dict(
            decision=dict(action="delivery_readiness", arguments={}),
            response=dict(ok=True, result=view),
        )
    )
    row = dict(
        instance=case["instance"],
        id=rid,
        reference_type="UNKNOWN",
        observer=observer,
        graph=frozen["graph"],
        options=frozen["options"],
        targets=targets,
        work_status={
            t: dict(
                completed=bool(work[t].get("completion_current")),
                authors=work[t].get("authors", []),
            )
            for t in targets
        },
        evidence={"E1": public},
        provenance=dict(commands=[rid], checkpoint=case["checkpoint"]),
        available_tokens=rt.team_budget.snapshot()["available_tokens"],
    )
    _, nodes, routes = build(row)
    if not routes:
        raise ValueError("No feasible continuation route at the scheduled decision")
    row["probe_id"] = sorted(nodes)[0]
    execution.record = row
    save(
        out / "decision-input.json",
        dict(row=row, view=view, checkpoint=case["checkpoint"], routes=routes),
    )
    if arm in ARMS and isinstance(execution, Execution):
        prepared = read_json(PLAN / "decision-preflight.json")["rows"]
        expected = next(r for r in prepared if r["checkpoint"] == case["checkpoint"])
        if digest((out / "decision-input.json").read_bytes()) != expected["input_identity"]:
            raise ValueError("Live decision inputs differ from the registered common checkpoint")
    active, info = execution.decide(node, observer, frozen, arm)
    save(out / "decision.json", dict(info=info, active=active, checkpoint=case["checkpoint"]))


def generate(case, task, arm, out):
    class PanelExecution(Execution):
        def __init__(self, post, folder, episode, slot, *, content_counter):
            transport = post.__self__
            controller = None
            if arm == "OSA":
                controller = ordinary.M.Backend(
                    out / "osa-api",
                    transport.ledger,
                    slot,
                    transport.counter,
                    transport.transport,
                    {"activate_organization"},
                ).post
            super().__init__(
                post,
                folder,
                episode,
                slot,
                content_counter=content_counter,
                controller_backend=controller,
            )

        def attach(self, rt):
            super().attach(rt)
            release_on_ordinary_entry(rt, out / "passive-captures")
            decision(self, rt, arm, case, out)

    # The old generator looks up its execution class through its versioned launcher.
    # Override that dependency on the local call only; historical modules stay immutable.
    launcher = SimpleNamespace(
        paired=SimpleNamespace(
            prior=SimpleNamespace(paired=SimpleNamespace(EvidenceFollowupExecution=PanelExecution))
        )
    )

    def fragment(prepared, rt, *, registration, **kwargs):
        return ordinary.run_worker_fragment(prepared, rt, source="paired-" + arm, **kwargs)

    fn = clone_function(
        ordinary.generate,
        {
            **ordinary.generate.__globals__,
            "AUTH": AUTH,
            "native": launcher,
            "run_worker_fragment": fragment,
        },
    )
    fn(dict(task=task, case=case, slot=f"{NS}:{case['index']}:{arm}", limit=5_000_000), out)


def register_account():
    a = dict(
        scope="independent",
        ledger=str(RUN / "ledger.sqlite"),
        account_cap_CNY=190,
        stage_cap_CNY=190,
        cap_nanoyuan=190_000_000_000,
    )
    ordinary.pairs.previous.freeze(AUTH, a)
    if not Path(a["ledger"]).exists():
        WindowLedger.create_independent(a)
    return a


def run_pair(case, task):
    base = RUN / str(case["index"])
    base.mkdir(exist_ok=True)

    def run(arm):
        dest = base / arm
        r = pre.isolated(Path(__file__).resolve(), [], dest, "result.json")
        scores = {}
        if r["status"] == "closed":
            for kind in ("code", "delivery"):
                rec = pre.isolated(
                    ROOT / "tools/score_project_relations_v217_1.py",
                    ["--index", case["index"], "--kind", kind, "--episode", dest],
                    base / (arm + "-" + kind),
                    "receipt.json",
                )
                scores[kind] = {k: rec.get(k) for k in ("status", "resolved", "error")}
        return dict(status=r["status"], error=r.get("error"), scores=scores)

    with ThreadPoolExecutor(2) as pool:
        results = dict(zip(ARMS, pool.map(run, ARMS)))
    save(base / "completed.json", results)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run-independent-190", action="store_true")
    args = parser.parse_args()
    (RUN / "tmp").mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    roster = read_json(PLAN / "roster.json")["roster"]
    tasks = {
        t["index"]: t
        for t in read_json(
            ordinary.ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json"
        )["rows"]
    }
    frozen = PLAN / "protocol.json"
    if args.register:
        files = [
            Path(__file__),
            Path(ordinary.__file__),
            ROOT / "tools/prepare_midtask_panel_v244.py",
            ROOT / "src/proworksim/software_review_handoff_v243_1.py",
            ROOT / "src/proworksim/software_event_orders_v243.py",
            ROOT / "src/proworksim/software_commitment_prompt_v240_4.py",
            ROOT / "tools/score_project_relations_v217_1.py",
        ]
        ordinary.pairs.previous.freeze(
            frozen,
            dict(
                roster=reference(PLAN / "roster.json"),
                preflight=reference(PLAN / "decision-preflight.json"),
                files=[reference(f) for f in files],
                arms=list(ARMS),
                decision="One scheduled opportunity at original saved prefix. Same managed public readiness view. KEEP activates incumbent allocation. OSA uses current v243 policy and may change, keep, abstain or fall back. No post-treatment selection.",
                budget="Separate 190 CNY account if confirmed. Reserve both continuations before dispatch. Hold unsettled usage; no cash from the previous experiment.",
            ),
        )
        return
    spec = read_json(frozen)
    for f in [spec["roster"], spec["preflight"], *spec["files"]]:
        checked(f)
    if args.output:
        out = args.output.resolve()
        case = next(c for c in roster if out.parent == RUN / str(c["index"]) and out.name in ARMS)
        return generate(case, tasks[case["index"]], out.name, out)
    if not args.run_independent_190:
        parser.error("Select funded execution mode")
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        authority = register_account()
        queue = [c for c in roster if not (RUN / str(c["index"]) / "completed.json").exists()]
        active = {}
        with ThreadPoolExecutor(2) as pool:
            while queue or active:
                while queue and len(active) < 2:
                    case = queue[0]
                    index = case["index"]
                    remaining = 5_000_000 - case["prefix"]
                    pre.check_images(
                        dict(roster=[dict(configuration=tasks[index]["configuration"])])
                    )
                    try:
                        pre.paired.reserve(
                            AUTH,
                            dict(
                                case=str(index),
                                account_cap_nanoyuan=authority["cap_nanoyuan"],
                                arm_limit=remaining,
                                worst_pair_nanoyuan=remaining * 16000,
                            ),
                            namespace=NS,
                            block=f"{NS}:{index}",
                        )
                    except ValueError as exc:
                        if str(exc) != "Insufficient funds for this complete pair":
                            raise
                        if active:
                            break
                        save(
                            RUN / "cash-boundary.json",
                            dict(
                                index=index,
                                remaining_roster=[c["index"] for c in queue],
                                required_nanoyuan=remaining * 16000,
                            ),
                        )
                        return
                    queue.pop(0)
                    active[pool.submit(run_pair, case, tasks[index])] = index
                if active:
                    finished, _ = wait(active, return_when=FIRST_COMPLETED)
                    for job in finished:
                        index = active.pop(job)
                        try:
                            print(index, job.result(), flush=True)
                        except Exception as exc:
                            save(RUN / str(index) / "coordinator-error.json", dict(error=repr(exc)))


if __name__ == "__main__":
    main()
