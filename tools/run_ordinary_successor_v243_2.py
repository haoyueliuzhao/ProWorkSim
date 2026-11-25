"""Finish a scoreable ordinary two-worker task; event collection never sets its end point."""

import argparse
import fcntl
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recruit_multitype_v242 as native
import run_event_pairs_v243 as pairs
from inventory_multitype_v242 import history, read_json, save, ROOT
from proworksim import software_registration_bridge_v242 as bridge
from proworksim.organization_harness import run_worker_fragment
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_fixed_organization_clone_v131 import clone_function
from run_offline_scorer_v096 import launch_spec
import subprocess

PLAN = ROOT / "artifacts/software-benchmark-v243-2/ordinary-r1"
RUN = ROOT / "runs/software-benchmark-v243-2/ordinary-r1"
SRC = ROOT / "runs/software-benchmark-v217"
AUTH = pairs.RUN / "authority.json"
M = native.M


def design():
    bank = read_json(ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json")[
        "rows"
    ]
    eligible = []
    for task in sorted(bank, key=lambda row: row["index"]):
        key = "task-%02d" % task["index"]
        archives = sorted(SRC.glob("*/" + key + "/PREFIX/result.json"))
        if any(
            p.parent.name not in ("PREFIX", "GENERATOR")
            for p in SRC.glob("*/" + key + "/*/result.json")
        ):
            continue
        for f in archives:
            p = f.parent
            if (
                read_json(f).get("status") != "no_eligible_decision_state"
                or not (p / "checkpoint/manifest.json").is_file()
            ):
                continue
            proof = read_json(p / "checkpoint/manifest.json")
            eligible.append(
                dict(
                    index=task["index"],
                    instance=task["instance_id"],
                    source=str(p.relative_to(ROOT)),
                    checkpoint=proof["identity"],
                    prefix=proof["prefix_tokens"],
                )
            )
            break
    case = eligible[0]
    task = next(t for t in bank if t["index"] == case["index"])
    spec = dict(
        case=case,
        task=task,
        pool=eligible,
        limit=5000000,
        cap=230000000000,
        slot="v243.2:" + case["instance"].split("__")[-1] + ":ordinary",
        rule="Smallest original index among v217 tasks with a restorable, previously unbranched prefix and no recorded successor arm. One normal completion, scored whether or not any anomaly occurs. No alternate task and no prompt telling workers to induce an event. Original v243 two-sided admission and existing priority/type quotas apply separately to new passive captures. No C/N or membership change.",
        files=[
            reference(Path(__file__)),
            reference(Path(bridge.__file__)),
            reference(ROOT / "src/proworksim/software_event_intake_v243.py"),
            reference(ROOT / "tools/drain_event_pairs_v243.py"),
        ],
    )
    pairs.previous.freeze(PLAN / "protocol.json", spec)
    print(case)


def generate(spec, out):
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    meter = PairedLedger.load(AUTH)
    row = spec["task"]
    c = spec["case"]
    slot = spec["slot"]
    rt = actor = None
    admitted = False
    res = dict(status="preparing", instance_id=row["instance_id"], started=time.time(), slot=slot)
    try:
        point = ROOT / c["source"] / "checkpoint"
        M.resume.register_persistence_types()
        saved, proof = M.resume.read(point)
        assert proof["identity"] == c["checkpoint"] and proof["prefix_tokens"] == c["prefix"]
        cfg = read_json(checked(row["configuration"]))
        deadline = M.DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        meter.admit(slot, spec["limit"] - c["prefix"])
        admitted = True
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
        prepared.world.__class__ = M.ControlledWorld
        tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        sha = M.digest(tok.read_bytes())
        counter = M.OfficialDeepSeekCounter(tok, manifest_sha256=sha)
        content, meta = M.load_official_content_counter(tok, manifest_sha256=sha)
        names = {
            t["function"]["name"]
            for m in ("member_001", "member_002")
            for t in M.native.member_wire_tools("FREE2", m)
        }
        transport = M.Backend(
            out / "api",
            meter,
            slot,
            counter,
            M.DirectHTTPS(M.load_api_key(ROOT / ".env"), timeout_seconds=1800),
            names,
        )
        execution = native.paired.prior.paired.EvidenceFollowupExecution(
            transport.post, out / "telemetry", row["instance_id"], slot, content_counter=content
        )
        owner = M.native.build_team_owner(
            execution.post,
            organization_id="FREE2",
            slot_id=slot,
            condition_id="ordinary",
            folder=out / "model-ledger",
            deadline=deadline,
            identity=dict(policy_version=M.native.VERSION, model="deepseek-flash", thinking=False),
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
        save(out / "restore.json", bridge.restore(prepared, rt, point))
        M.native.enter_continuation(rt)
        M.native.set_native_limit(rt, spec["limit"])
        execution.attach(rt)
        actor.bind_deadline(rt.deadline)
        start = rt.opportunities

        def observe(o):
            M.after_opportunity(actor, out / "transport-fault.json")
            save(
                out / "progress.json",
                dict(
                    ordinal=rt.opportunities,
                    added=rt.opportunities - start,
                    logical=owner.adapter.ledger.actual,
                    worker=o.get("worker_id"),
                ),
            )

        seed = [r for r in history(point.parent) if r["ordinal"] <= start]
        reg = dict(
            panel="v217",
            instance=row["instance_id"],
            index=row["index"],
            job_root=str(out),
            ledger=str(meter.path),
        )
        result = run_worker_fragment(
            prepared,
            rt,
            folder=out / "passive-captures",
            history=seed,
            registration=reg,
            on_opportunity=observe,
        )
        save(out / "boundary.json", result)
        if result["execution_integrity_failure"]:
            raise RuntimeError(str(result["execution_integrity_failure"]))
        M.native.close_runtime(rt)
        rt = None
        save(
            out / "candidate-lock.json",
            M.native.lock_fixed_candidates(prepared, out / "closure", sdk_closed=True),
        )
        res.update(
            status="closed",
            logical_tokens=owner.adapter.ledger.actual,
            prefix_tokens=c["prefix"],
            termination=result["termination_class"],
            initial_ordinal=start,
        )
    except Exception as exc:
        res.update(status="technical_unknown", error=repr(exc), traceback=traceback.format_exc())
    finally:
        for close in (
            ([lambda: M.native.close_runtime(rt)] if rt else [])
            + ([lambda: actor.close()] if actor else [])
            + ([lambda: meter.close(slot)] if admitted else [])
        ):
            try:
                close()
            except Exception as exc:
                res.setdefault("cleanup_errors", []).append(repr(exc))
        save(out / "result.json", dict(**res, finished=time.time()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--register", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.register:
        return design()
    spec = read_json(PLAN / "protocol.json")
    for f in spec["files"]:
        checked(f)
    out = RUN / "ordinary"
    if a.output:
        if a.output != out:
            raise ValueError("Unregistered work directory")
        return generate(spec, out)
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pre = pairs.previous.prior
        if not (out / "result.json").is_file():
            pre.check_images({"roster": [{"configuration": spec["task"]["configuration"]}]})
            reserve = clone_function(
                pre.paired.reserve, {**pre.paired.reserve.__globals__, "ARMS": ("ordinary",)}
            )
            cash = (spec["limit"] - spec["case"]["prefix"]) * 8000
            reserve(
                AUTH,
                dict(
                    case=spec["slot"].split(":")[1],
                    account_cap_nanoyuan=spec["cap"],
                    arm_limit=cash // 8000,
                    worst_pair_nanoyuan=cash,
                ),
                namespace="v243.2",
                block=spec["slot"],
            )
        (RUN / "tmp").mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(RUN / "tmp")
        result = pre.isolated(Path(__file__).resolve(), [], out, "result.json")
        scores = {}
        if result["status"] == "closed":
            for k in ("code", "delivery"):
                scores[k] = pre.isolated(
                    ROOT / "tools/score_project_relations_v217_1.py",
                    ["--index", spec["case"]["index"], "--kind", k, "--episode", out],
                    RUN / k,
                    "receipt.json",
                ).get("resolved")
        save(
            RUN / "completed.json",
            dict(status=result["status"], scores=scores, error=result.get("error")),
        )
        if result["status"] == "closed":
            cmd, env = launch_spec([str(ROOT / "tools/drain_event_pairs_v243.py")])
            subprocess.run(cmd, cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
