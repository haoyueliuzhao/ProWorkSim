"""Prospective natural checkpoint recruitment. The original prefix is an anchor, never the anomaly."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_multitype_worker_v242 as paired
from inventory_multitype_v242 import PLAN, RUN, ROOT, save, history
from prepare_osa_states_v236 import evidence
from run_offline_scorer_v096 import launch_spec
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_graph_controller_v228 import menu
from proworksim.software_graph_evidence_v228_1 import explain
from proworksim import software_three_graph_v240 as contract
from proworksim.storage import read_json

M = paired.prior.paired.episode_module
CANDIDATES = [
    ("A2", "v216/target-repair6-r1/r2-task-02", 216, 2),
    ("A3", "v217/selection28-r1/task-04", 217, 4),
    ("A2", "v216/target-repair6-r1/r2-task-04", 216, 4),
    ("A1", "v217/confirmation-resume-r1/task-29", 217, 29),
    ("A1", "v216/mechanism6-r1/task-00", 216, 0),
]


class StopPrefix(Exception):
    pass


def design():
    candidates = []
    for kind, anchor, v, i in CANDIDATES:
        path = ROOT / "runs" / ("software-benchmark-" + anchor) / "PREFIX"
        manifest = read_json(path / "checkpoint/manifest.json")
        (task,) = [
            r
            for r in read_json(
                ROOT / f"artifacts/software-benchmark-v{v}/protocol-r1/candidate-tasks.json"
            )["rows"]
            if r["index"] == i
        ]
        case = task["instance_id"].split("__")[1]
        scorer = (
            "score_real_adaptation_v216.py" if v == 216 else "score_project_relations_v217_1.py"
        )
        assert read_json(path / "result.json")["instance_id"] == task["instance_id"]
        candidates.append(
            dict(
                case=case,
                kind=kind,
                source=str(path.relative_to(ROOT)),
                checkpoint=manifest["identity"],
                prefix=manifest["prefix_tokens"],
                task=task,
                score_script=scorer,
                score_index=i,
            )
        )
    return dict(
        candidates=candidates,
        files=[
            reference(Path(__file__)),
            reference(Path(paired.__file__)),
            reference(Path(paired.mechanism.__file__)),
            reference(Path(M.__file__)),
            reference(Path(contract.__file__)),
        ],
        method="Anchors selected for historical occurrence of the named problem, not by model scores. One fresh natural trajectory per anchor, no injected obstacle or tool action. Stop at first authorized target receipt with mutable affected work and >=8 full call envelopes remaining, else close on insufficient remaining capacity, terminal, or 45 new opportunities. No force-change. Register planning data and original worker-visible receipts before branching. Reserve full worst-case common-prefix plus both arms, then convert pending reservation at actual prefix cost. First wave max two closed pairs including the A4 development case. Review pair receipts before admitting subsequent wave. No participation by v241 Sphinx or Astropy-14182.",
    )


def reserve_capture(c, meter):
    case = c["case"]
    limit = 5000000 - c["prefix"]
    block = "v242:recruit:" + case
    expected = {block + ":COMMON": limit, block + ":PAIR-HOLD": limit}
    with meter.db() as db:
        old = dict(
            db.execute("select slot,token_limit from block_slots where block_id=?", (block,))
        )
        if old:
            if old != expected:
                raise ValueError("Conflicting capture identity")
            return True
        if int(db.execute("select value from meta where key='cap'").fetchone()[0]) != 230000000000:
            raise ValueError("Wrong cash ledger")
        spent = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        if spent + held + pending + 2 * limit * 8000 > meter.cap:
            return False
        db.executemany(
            "insert into block_slots values(?,?,?,'pending')",
            [(s, block, b) for s, b in expected.items()],
        )
    return True


def convert(c, meter, res):
    key = "v242:recruit:" + c["case"]
    slot = key + ":COMMON"
    hold = key + ":PAIR-HOLD"
    with meter.db() as db:
        status = db.execute("select status from block_slots where slot=?", (hold,)).fetchone()
        if status == ("released",):
            return
        if status != ("pending",):
            raise ValueError("Missing complete-pair reservation")
        if db.execute("select status from slots where id=?", (slot,)).fetchone() != ("closed",):
            raise ValueError("Unsettled prefix")
        used = db.execute(
            "select coalesce(sum(tokens),0) from requests where slot=? and status='settled'",
            (slot,),
        ).fetchone()[0]
        db.execute("update block_slots set status='released' where slot=?", (hold,))
        if res["status"] == "point_ready":
            n = res["available"]
            assert n == 5000000 - c["prefix"] - used
            db.executemany(
                "insert into block_slots values(?,?,?,'pending')",
                [
                    (paired.NS + ":" + c["case"] + ":" + a, paired.NS + ":" + c["case"], n)
                    for a in paired.prior.ARMS
                ],
            )


def capture(c, out):
    out.mkdir(parents=True, exist_ok=False)
    # SDK files and temporary data are isolated per capture process.
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    slot = "v242:recruit:" + c["case"] + ":COMMON"
    meter = PairedLedger.load(RUN / "authority.json")
    meters = False
    rt = actor = None
    found = None
    seen = []
    result = dict(
        case=c["case"],
        instance_id=c["task"]["instance_id"],
        kind=c["kind"],
        status="preparing",
        started=time.time(),
        slot=slot,
    )
    try:
        point = ROOT / c["source"] / "checkpoint"
        M.resume.register_persistence_types()
        saved, proof = M.resume.read(point)
        if proof["identity"] != c["checkpoint"] or proof["prefix_tokens"] != c["prefix"]:
            raise ValueError("Checkpoint mismatch")
        row = c["task"]
        cfg = read_json(checked(row["configuration"]))
        deadline = M.DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        meter.admit(slot, 5000000 - c["prefix"])
        meters = True
        actor = M.Actor(row, out / "actor", resume_test_calls=saved["public_test_calls"])
        actor.start()
        prepared = M.substrate.prepare_case(
            out / "actor/source-manifest.json",
            out / "prepared",
            organization_id="FREE2",
            public_test_callback=actor.test,
            deadline=deadline,
            public_test_entry=actor.entry,
        )
        M.natural.attach(prepared, [r["id"] for r in row["requirements"]], condition="G")
        M.resume.restore_world(prepared, point)
        world = prepared.world
        world.__class__ = M.ControlledWorld
        tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        sha = M.digest(tok.read_bytes())
        counter = M.OfficialDeepSeekCounter(tok, manifest_sha256=sha)
        content, meta = M.load_official_content_counter(tok, manifest_sha256=sha)
        names = {
            t["function"]["name"]
            for m in ("member_001", "member_002")
            for t in M.native.member_wire_tools("FREE2", m)
        }
        backend = M.Backend(
            out / "api",
            meter,
            slot,
            counter,
            M.DirectHTTPS(M.load_api_key(ROOT / ".env"), timeout_seconds=1800),
            names,
        )
        execution = paired.prior.paired.EvidenceFollowupExecution(
            backend.post, out / "telemetry", row["instance_id"], slot, content_counter=content
        )
        owner = M.native.build_team_owner(
            execution.post,
            organization_id="FREE2",
            slot_id=slot,
            condition_id="v242-common",
            folder=out / "model-ledger",
            deadline=deadline,
            identity={
                "policy_version": M.native.VERSION,
                "model": "deepseek-flash",
                "thinking": False,
            },
            observation_token_counter=content,
            observation_tokenizer_id=meta["tokenizer_id"],
            require_content_counter=True,
        )
        initial = (
            M.native.CONTRACT
            + "\n"
            + cfg["public_task"]["problem_statement"]
            + "\n"
            + M.public_context(cfg, actor.public)
        )
        rt, _, _ = M.native.build_runtime(
            owner, prepared, out / "runtime", deadline=deadline, public_initial_message=initial
        )
        save(out / "restore.json", M.resume.restore_runtime(prepared, rt, point))
        M.native.enter_continuation(rt)
        M.native.set_native_limit(rt, 5000000)
        execution.attach(rt)
        actor.bind_deadline(rt.deadline)
        start = rt.opportunities
        graphs = {m: AnomalyGraph(m) for m in ("member_001", "member_002")}
        # Carry true prefix receipts in the monitor, while requiring new trigger evidence after restoration.
        seed_history = history(ROOT / c["source"])
        for h in seed_history:
            for mon in graphs.values():
                mon.observe(h["ordinal"], h["outcome"])

        def step(o):
            nonlocal found
            M.after_opportunity(actor, out / "transport-fault.json")
            i = rt.opportunities
            seen.append(dict(ordinal=i, outcome=o))
            who = o.get("worker_id")
            if who not in graphs:
                return
            mon = graphs[who]
            mon.observe(i, o)
            available = rt.team_budget.snapshot()["available_tokens"]
            save(out / "progress.json", dict(opportunity=i, available=available, kind=c["kind"]))
            if world.protocol()["terminal"]:
                return
            if available < 8 * paired.mechanism.CALL_BOUND:
                raise StopPrefix()
            for n in mon.nodes.values():
                if (
                    n["anomaly_type"] != c["kind"]
                    or n["status"] not in ("OPEN", "ACTIVE", "REOPENED")
                    or not n["affected_work"]
                    or max(x["opportunity"] for x in n["evidence_refs"]) != i
                ):
                    continue
                frozen = menu(world, n, who)
                if not any(not frozen["graph"]["work"][k]["children"] for k in n["affected_work"]):
                    continue
                found = (n, who)
                raise StopPrefix()
            if i - start >= 45:
                raise StopPrefix()

        try:
            boundary = M.native.run_fragment(prepared, rt, on_opportunity=step)
            save(out / "boundary.json", boundary)
            if boundary["execution_integrity_failure"]:
                raise ValueError(str(boundary["execution_integrity_failure"]))
        except StopPrefix:
            pass
        log = [*seed_history, *seen]
        save(out / "observations.json", log)
        if found:
            n, who = found
            n = explain(n, log, who)
            frozen = menu(world, n, who)
            proof = M.resume.save(
                prepared,
                rt,
                out / "checkpoint",
                control_state={"node": n, "ordinal": rt.opportunities, "observer": who},
            )
            idx = {
                o["outcome"]["response"]["command_id"]: o
                for o in log
                if o["outcome"].get("response", {}).get("command_id")
            }
            evidence_rows = [idx[e["command_id"]] for e in n["evidence_refs"]]
            targets = [k for k in n["affected_work"] if not frozen["graph"]["work"][k]["children"]]
            dyn = world.dynamic()
            avail = rt.team_budget.snapshot()["available_tokens"]
            sample = dict(
                id=c["case"],
                instance=row["instance_id"],
                reference_type=c["kind"],
                observer=who,
                targets=targets,
                graph=frozen["graph"],
                options=frozen["options"],
                work_status={
                    k: dict(
                        completed=bool(dyn["work"][k].get("completion_current")),
                        authors=dyn["work"][k].get("authors", []),
                    )
                    for k in targets
                },
                evidence={f"E{i}": evidence(h["outcome"]) for i, h in enumerate(evidence_rows, 1)},
                available_tokens=avail,
                provenance=dict(
                    commands=[h["outcome"]["response"]["command_id"] for h in evidence_rows],
                    ordinals=[h["ordinal"] for h in evidence_rows],
                    source=str((out / "observations.json").relative_to(ROOT)),
                    checkpoint=proof["identity"],
                ),
            )
            _, ob, routes = contract.build(sample)
            sample["probe_id"] = sorted(ob)[0]
            if not routes:
                raise ValueError("Captured state has no executable route")
            assert avail == 5000000 - proof["prefix_tokens"]
            specitem = dict(
                case=c["case"],
                instance=row["instance_id"],
                kind=c["kind"],
                row=sample,
                task=row,
                checkpoint=proof["identity"],
                initial_budget=avail,
                pair_hold_nanoyuan=2 * avail * 8000,
                configuration=row["configuration"],
                score_script=c["score_script"],
                score_index=c["score_index"],
                state=dict(
                    case=c["case"],
                    source_prefix=str(out.relative_to(ROOT)),
                    checkpoint=proof["identity"],
                    shared_prefix_usage=proof["prefix_tokens"],
                ),
            )
            save(out / "registered-state.json", specitem)
            result.update(status="point_ready", checkpoint=proof["identity"], available=avail)
        else:
            result.update(status="no_qualifying_state", new_opportunities=rt.opportunities - start)
    except Exception as e:
        import traceback

        result.update(status="technical_unknown", error=repr(e), traceback=traceback.format_exc())
    finally:
        for cleanup in (
            ([lambda: M.native.close_runtime(rt)] if rt else [])
            + ([lambda: actor.close()] if actor else [])
            + ([lambda: meter.close(slot)] if meters else [])
        ):
            try:
                cleanup()
            except Exception as e:
                result.setdefault("cleanup_errors", []).append(repr(e))
        result["finished"] = time.time()
        save(out / "result.json", result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--case")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    protocol = PLAN / "recruitment.json"
    if a.freeze:
        paired.freeze(protocol, design())
        return
    spec = read_json(protocol)
    for f in spec["files"]:
        checked(f)
    (c,) = [c for c in spec["candidates"] if c["case"] == a.case]
    folder = RUN / "recruitment" / c["case"]
    out = folder / "COMMON"
    if a.output:
        if a.output != out:
            raise ValueError("Foreign prefix")
        capture(c, out)
        return
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meter = PairedLedger.load(RUN / "authority.json")
        if not reserve_capture(c, meter):
            save(
                folder / "admission.json",
                dict(status="deferred_cash", worst_pair_nanoyuan=(5000000 - c["prefix"]) * 16000),
            )
            return
        os.environ["TMPDIR"] = str(RUN / "tmp")
        res = paired.prior.isolated(
            Path(__file__).resolve(), ["--case", a.case], out, "result.json"
        )
        convert(c, meter, res)
        if res["status"] == "point_ready":
            item = read_json(out / "registered-state.json")
            trial = paired.spec_for(item)
            trial["files"].extend([reference(protocol), reference(out / "registered-state.json")])
            paired.freeze(PLAN / c["case"] / "protocol.json", trial)
        save(folder / "admission.json", res)


if __name__ == "__main__":
    main()
