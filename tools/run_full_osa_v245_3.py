"""Complete fresh OSA episodes from the official base, funded by the existing v245 ledger."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_fair_pairs_v245 as previous
import run_ordinary_successor_v243_2 as ordinary
from prepare_osa_states_v236 import evidence
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_event_orders_v243 import orders, wire
from proworksim.software_fair_delivery_v245 import Execution, NOTICE
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_graph_controller_v228 import menu, PROJECT
from proworksim.software_three_graph_v240 import build
from proworksim.storage import read_json, digest, json_bytes

ROOT = previous.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v245-3/full-osa12-r1"
RUN = ROOT / "runs/software-benchmark-v245-3/full-osa12-r1"
BANK = ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json"
AUTH = previous.AUTH
LIMIT = 5_000_000
NS = "v245.3"
save = previous.save
pre = previous.prior.pre
M = ordinary.M


def decision(ex, rt, task, out, counter):
    w = rt.prepared.world
    who = rt.fixed_spec["delivery_member"]
    view = w._action_delivery_readiness(who, PROJECT)
    rid = digest(json_bytes([ex.trace.branch, rt.opportunities, view]))
    ev = evidence(
        dict(
            decision=dict(action="delivery_readiness", arguments={}),
            response=dict(ok=True, result=view),
        )
    )
    work = w.dynamic()["work"]
    # Observe current work only. Prefer open packages, keeping a bounded controller wire.
    targets = sorted(
        (k for k, v in work.items() if not v["children"]),
        key=lambda k: (bool(work[k]["completion"]), k),
    )
    while targets:
        node = dict(
            anomaly_id="scheduled-" + rid[:16],
            anomaly_type="scheduled_review",
            subject=None,
            affected_work=list(targets),
            evidence_refs=[
                dict(
                    command_id=rid,
                    tool="delivery_readiness",
                    actor_id=who,
                    opportunity=rt.opportunities,
                )
            ],
        )
        frozen = menu(w, node, who)
        row = dict(
            instance=task["instance_id"],
            id=rid,
            reference_type="UNKNOWN",
            observer=who,
            graph=frozen["graph"],
            options=frozen["options"],
            targets=list(targets),
            work_status={
                k: dict(completed=w._completion_current(k), authors=work[k]["authors"])
                for k in targets
            },
            evidence={"E1": ev},
            provenance=dict(commands=[rid], origin="live_current_episode"),
            available_tokens=rt.team_budget.snapshot()["available_tokens"],
        )
        _, nodes, routes = build(row)
        if routes:
            row["probe_id"] = sorted(nodes)[0]
            request = wire(row, orders(row))
            if counter.measure(request)["prompt_tokens"] + request["max_tokens"] <= min(
                8192, row["available_tokens"]
            ):
                ex.record = row
                save(
                    out / "decision-input.json",
                    dict(row=row, view=view, routes=routes, opportunity=rt.opportunities),
                )
                active, info = ex.decide(node, who, frozen, "OSA")
                save(
                    out / "decision.json",
                    dict(active=active, info=info, opportunity=rt.opportunities),
                )
                return info["osa_tokens"]
        targets.pop()
    return None


def generate(task, out):
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    meter = PairedLedger.load(AUTH)
    slot = f"{NS}:{task['index']}:OSA"
    res = dict(
        status="preparing",
        instance_id=task["instance_id"],
        slot=slot,
        started=time.time(),
        prefix_tokens=0,
        checkpoint_parent=None,
    )
    rt = actor = None
    admitted = False
    try:
        meter.admit(slot, LIMIT)
        admitted = True
        cfg = read_json(checked(task["configuration"]))
        actor = M.Actor(task, out / "actor", resume_test_calls=0)
        actor.start()
        deadline = M.DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        prepared = M.substrate.prepare_case(
            out / "actor/source-manifest.json",
            out / "prepared",
            organization_id="FREE2",
            public_test_callback=actor.test,
            deadline=deadline,
            public_test_entry=actor.entry,
        )
        M.natural.attach(prepared, [r["id"] for r in task["requirements"]], condition="G")
        prepared.world.__class__ = M.ControlledWorld
        tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        sha = digest(tok.read_bytes())
        counter = M.OfficialDeepSeekCounter(tok, manifest_sha256=sha)
        content, meta = M.load_official_content_counter(tok, manifest_sha256=sha)
        names = {
            t["function"]["name"]
            for m in ("member_001", "member_002")
            for t in M.native.member_wire_tools("FREE2", m)
        }
        transport = M.DirectHTTPS(M.load_api_key(ROOT / ".env"), timeout_seconds=1800)
        worker = M.Backend(out / "api", meter, slot, counter, transport, names)
        controller = M.Backend(
            out / "osa-api", meter, slot, counter, transport, {"activate_organization"}
        )
        ex = Execution(
            worker.post,
            out / "telemetry",
            task["instance_id"],
            slot,
            content_counter=content,
            controller_backend=controller.post,
        )
        owner = M.native.build_team_owner(
            ex.post,
            organization_id="FREE2",
            slot_id=slot,
            condition_id="full-task-osa",
            folder=out / "model-ledger",
            deadline=deadline,
            identity=dict(policy_version=M.native.VERSION, model="deepseek-flash", thinking=False),
            observation_token_counter=content,
            observation_tokenizer_id=meta["tokenizer_id"],
            require_content_counter=True,
        )
        initial = (
            NOTICE
            + "\nTwo actual workers. Solve this issue from its original repository using the managed tools; allocate work as useful and explicitly deliver the final candidate.\n"
            + cfg["public_task"]["problem_statement"]
            + "\n"
            + M.public_context(cfg, actor.public)
        )
        rt, _, _ = M.native.build_runtime(
            owner, prepared, out / "runtime", deadline=deadline, public_initial_message=initial
        )
        M.native.set_native_limit(rt, LIMIT)
        ex.attach(rt)
        actor.bind_deadline(rt.deadline)
        w = rt.prepared.world
        _, _, baseline = w._bundle("member_001", baseline=True)
        for m in rt.labels:
            _, _, current = w._bundle(m)
            assert all(current[k] == baseline[k] for k in ("files", "entry_metadata"))
        assert (
            owner.adapter.ledger.actual == 0
            and rt.opportunities == 0
            and not w._software()["patches"]
        )
        save(
            out / "fresh-start.json",
            dict(
                instance=task["instance_id"],
                base_commit=task["base_commit"],
                original_tree=reference(out / "actor/initial-tree.json"),
                initial_opportunities=0,
                initial_model_tokens=0,
                prior_patch_count=0,
                history_restored=False,
                roles=list(rt.labels),
            ),
        )
        for m in rt.labels:
            rt.policies[m].conversation.send_message(
                "Begin work now. You may split the issue into work packages using the public scope IDs if useful. "
                + str(task["requirements"])
                + ". No pause is required. Continue through testing and explicit submission."
            )
        cost = None

        def observe(o):
            nonlocal cost
            M.after_opportunity(actor, out / "transport-fault.json")
            if cost is None and not w.protocol()["terminal"] and rt.opportunities >= 12:
                cost = decision(ex, rt, task, out, counter)
            save(
                out / "progress.json",
                dict(
                    opportunity=rt.opportunities,
                    worker_tokens=owner.adapter.ledger.actual,
                    osa_tokens=cost,
                    actor=o.get("worker_id"),
                ),
            )

        boundary = M.native.run_fragment(prepared, rt, on_opportunity=observe)
        save(out / "boundary.json", boundary)
        if boundary["execution_integrity_failure"]:
            raise RuntimeError(str(boundary["execution_integrity_failure"]))
        M.native.close_runtime(rt)
        rt = None
        save(
            out / "candidate-lock.json",
            M.native.lock_fixed_candidates(prepared, out / "closure", sdk_closed=True),
        )
        res.update(
            status="closed",
            osa_tokens=cost or 0,
            osa_called=cost is not None,
            termination=boundary["termination_class"],
            logical_tokens=owner.adapter.ledger.actual + (cost or 0),
        )
    except Exception as exc:
        res.update(status="technical_unknown", error=repr(exc), traceback=traceback.format_exc())
    finally:
        for fn in (
            ([lambda: M.native.close_runtime(rt)] if rt else [])
            + ([actor.close] if actor else [])
            + ([lambda: meter.close(slot)] if admitted else [])
        ):
            try:
                fn()
            except Exception as exc:
                res.setdefault("cleanup_errors", []).append(repr(exc))
        save(out / "result.json", dict(res, finished=time.time()))


def process(case, task):
    base = RUN / str(case["index"])
    base.mkdir(exist_ok=True)
    dest = base / "OSA"
    r = pre.isolated(Path(__file__).resolve(), [], dest, "result.json")
    scores = {}
    if r["status"] == "closed":
        for k in ("code", "delivery"):
            s = pre.isolated(
                ROOT / "tools/score_project_relations_v217_1.py",
                ["--index", case["index"], "--kind", k, "--episode", dest],
                base / ("OSA-" + k),
                "receipt.json",
            )
            scores[k] = dict(status=s["status"], resolved=s.get("resolved"))
    done = dict(status=r["status"], scores=scores, error=r.get("error"))
    save(base / "completed.json", done)
    return done


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    spec = read_json(PLAN / "protocol.json")
    roster = read_json(checked(spec["roster"]))["roster"]
    for f in spec["files"]:
        checked(f)
    tasks = {t["index"]: t for t in read_json(checked(spec["bank"]))["rows"]}
    (RUN / "tmp").mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    if args.output:
        path = args.output.resolve()
        case = next(c for c in roster if path == RUN / str(c["index"]) / "OSA")
        return generate(tasks[case["index"]], path)
    reserve = clone_function(
        pre.paired.reserve, {**pre.paired.reserve.__globals__, "ARMS": ("OSA",)}
    )
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        queue = [c for c in roster if not (RUN / str(c["index"]) / "completed.json").exists()]
        active = {}
        with ThreadPoolExecutor(3) as pool:
            while queue or active:
                while queue and len(active) < 3:
                    case = queue[0]
                    i = case["index"]
                    pre.check_images(dict(roster=[dict(configuration=tasks[i]["configuration"])]))
                    try:
                        reserve(
                            AUTH,
                            dict(
                                case=str(i),
                                account_cap_nanoyuan=150_000_000_000,
                                arm_limit=LIMIT,
                                worst_pair_nanoyuan=LIMIT * 8000,
                            ),
                            namespace=NS,
                            block=f"{NS}:{i}",
                        )
                    except ValueError as exc:
                        if str(exc) != "Insufficient funds for this complete pair":
                            raise
                        if active:
                            break
                        save(
                            RUN / "cash-boundary.json",
                            dict(remaining=[c["index"] for c in queue], required_CNY=40),
                        )
                        return
                    queue.pop(0)
                    active[pool.submit(process, case, tasks[i])] = i
                if active:
                    finished, _ = wait(active, return_when=FIRST_COMPLETED)
                    for f in finished:
                        i = active.pop(f)
                        print(i, f.result(), flush=True)


if __name__ == "__main__":
    main()
