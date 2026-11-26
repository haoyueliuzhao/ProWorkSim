"""First prospective expansion and contraction blocks, on a common real SDK checkpoint."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
from pathlib import Path
import sys, time, traceback, json

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa as old
import recover_failure_graph_panel_v246 as account
from proworksim import software_organization_patch_v247 as patch
from proworksim.software_membership_v247 import install, POOL, Profile, INSTRUCTION
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_failure_graph_v246 import FailureProjectGraph
from proworksim.software_organization_v232 import OrganizationExecution as Execution
from jsonschema import ValidationError
from proworksim.software_organization_api_v204 import PrefixComplete
from proworksim.software_sdk_resume_v203_3_4 import (
    save as save_checkpoint,
    restore_runtime,
    restore_world,
    read as read_checkpoint,
)
from proworksim.storage import read_json

M = old.M
ROOT = old.ROOT
RUN = ROOT / "runs/software-benchmark-v248/dynamic-membership-r1"
PLAN = ROOT / "artifacts/software-benchmark-v248/dynamic-membership-r1"
AUTH = account.AUTH
NS = "v248.1"
ARMS = ("K", "O-FIXED", "O-DYNAMIC")
LIMIT = 5_000_000
PREFIX = 1_500_000
BANK = old.baseline.previous.BANK
freeze = old.baseline.previous.previous.freeze
save = old.save


def register():
    bank = read_json(BANK)["rows"]
    rows = [
        dict(
            index=r["index"],
            instance=r["instance_id"],
            initial=2 if j % 2 == 0 else 3,
            base_commit=r["base_commit"],
            configuration=r["configuration"],
        )
        for j, r in enumerate(sorted(bank, key=lambda r: r["index"])[:6])
    ]
    paths = [
        Path(__file__),
        ROOT / "tools/check_membership_v247.py",
        ROOT / "src/proworksim/software_organization_patch_v247.py",
        ROOT / "src/proworksim/software_membership_v247.py",
        ROOT / "src/proworksim/software_role_baseline_runtime_v141.py",
        ROOT / "src/proworksim/software_context_builder_v230.py",
        ROOT / "src/proworksim/software_organization_api_v204.py",
    ]
    spec = dict(
        rows=rows,
        files=[old.reference(p) for p in paths],
        bank=old.reference(BANK),
        authority=old.reference(AUTH),
        arms=ARMS,
        order="Original v217 bank index, alternating 2 and 3 initial workers; first eligible complete block per direction, then review",
        selection="Common ordinary prefix, maximum 1.5M physical tokens or 32 opportunities; observe actual split open leaves or failed public test (expansion), or three real actors with overlapping repository reads or reduced open work after a test (contraction). Never select by score or OSA choice.",
        team_limit=LIMIT,
        stage1_max_branches=6,
        cumulative_cap=400,
        whole_block_peak_nanoyuan=3 * LIMIT * 8000,
        policy="Same P1 model, T1, v245 fair delivery, resources and evidence. K freezes graph. O-FIXED and O-DYNAMIC use their own legal menus at the shared checkpoint and later new events. The later discussion supersedes the earlier O1/O2 common-output design. No C/N.",
    )
    freeze(PLAN / "protocol.json", json.loads(json.dumps(spec)))
    return spec


def slot(i, arm):
    return f"{NS}:{i}:{arm}"


def reserve(i):
    meter = PairedLedger.load(AUTH)
    names = [slot(i, a) for a in ("COMMON", *ARMS)]
    limits = [PREFIX, LIMIT - PREFIX, LIMIT, LIMIT]
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Ledger cap")
        if db.execute("select 1 from block_slots where block_id=?", (slot(i, "block"),)).fetchone():
            return
        paid = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        active = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        if paid + active + held + sum(limits) * 8000 > meter.cap:
            raise ValueError("Full block exceeds available balance")
        db.executemany(
            "insert into block_slots values(?,?,?,'pending')",
            [(n, slot(i, "block"), v) for n, v in zip(names, limits, strict=True)],
        )


def allocate(i, prefix):
    meter = PairedLedger.load(AUTH)
    with meter.db() as db:
        closed = db.execute("select status from slots where id=?", (slot(i, "COMMON"),)).fetchone()
        if closed != ("closed",):
            raise ValueError("Common prefix not settled")
        used = db.execute(
            "select coalesce(sum(tokens),0) from requests where status='settled' and slot=?",
            (slot(i, "COMMON"),),
        ).fetchone()[0]
        if prefix is not None and (used != prefix or not 0 < used < LIMIT):
            raise ValueError("Common-prefix usage mismatch")
        for arm in ARMS:
            if prefix is None:
                db.execute(
                    "update block_slots set status='released' where slot=? and status='pending'",
                    (slot(i, arm),),
                )
            else:
                db.execute(
                    "update block_slots set token_limit=? where slot=? and status='pending'",
                    (LIMIT - used, slot(i, arm)),
                )


class Window(Exception):
    pass


class Signals:
    def __init__(self):
        self.graph = FailureProjectGraph()
        self.actors = set()
        self.readers = {}
        self.test = None

    def observe(self, w, step, o):
        d = o.get("decision") or {}
        resp = o.get("response") or {}
        result = resp.get("result") or {}
        if not resp.get("ok"):
            return {}
        actor = o["worker_id"]
        self.actors.add(actor)
        action = d.get("action")
        args = d.get("arguments") or {}
        if action in {"read_file", "search_file"} and args.get("path"):
            self.readers.setdefault(args["path"], set()).add(actor)
        package = w.dynamic()["active_work"].get(actor)
        leaves = [
            t
            for t, v in w.dynamic()["work"].items()
            if not v["children"] and not w._completion_current(t)
        ]
        if not package and len(leaves) == 1:
            package = leaves[0]
        self.graph.observe(step, o, package)
        facts = {}
        if action == "run_tests" and result.get("executed"):
            self.test = dict(
                passed=result.get("passed"),
                reference=result.get("source_reference"),
                package=package,
                command=resp.get("command_id"),
            )
            if result.get("passed") is False:
                facts = {"test": self.test}
        for node in self.graph.nodes.values():
            if node["state"] == "needs_decision" and node["window"][-1] == resp.get("command_id"):
                facts["incident"] = {k: node[k] for k in ("id", "package", "target_kind", "target")}
                refs = self.graph.decision_evidence(node)
                facts["incident"]["receipts"] = refs
                facts["incident"]["tested_versions"] = [
                    self.graph.reports[c]["source_reference"] for c in refs
                ]
                self.graph.decided([node], dict(observed_opportunity=step))
        if action in {
            "complete_work",
            "complete_evidence",
            "reopen_work",
            "split_work",
            "handoff_patch",
            "integrate_patch",
        }:
            facts["work_event"] = dict(
                tool=action,
                task=package,
                command=resp.get("command_id"),
                conflicts=result.get("conflicts", []),
                patch=result.get("patch_id", args.get("patch_id")),
                reference=result.get("source_reference"),
            )
        return facts

    def qualify(self, w, n):
        work = w.dynamic()["work"]
        leaves = [t for t, v in work.items() if not v["children"] and not w._completion_current(t)]
        if len(self.actors) < n or not leaves:
            return {}
        if n == 2 and (len(leaves) >= 2 or self.test and self.test["passed"] is False):
            return {"workload": dict(open_packages=leaves, last_public_test=self.test)}
        overlaps = sorted(k for k, m in self.readers.items() if len(m) >= 2)
        if n == 3 and (overlaps or len(leaves) <= 2 and self.test):
            # Share only the count of overlapping paths, not private reads or their contents.
            return {
                "workload": dict(
                    open_packages=leaves,
                    overlapping_path_count=len(overlaps),
                    last_public_test=self.test,
                )
            }
        return {}


def generate(case, arm, out):
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
    )
    task = next(r for r in read_json(BANK)["rows"] if r["index"] == case["index"])
    i = case["index"]
    common = arm == "COMMON"
    cp = RUN / str(i) / "COMMON/checkpoint"
    prefix = 0 if common else read_json(cp / "manifest.json")["prefix_tokens"]
    test_calls = 0 if common else read_checkpoint(cp)[0]["public_test_calls"]
    meter = PairedLedger.load(AUTH)
    name = slot(i, arm)
    rt = actor = None
    admitted = False
    metaresult = dict(
        status="technical_unknown",
        instance_id=task["instance_id"],
        arm=arm,
        slot=name,
        started=time.time(),
        prefix_tokens=prefix,
    )
    try:
        meter.admit(name, PREFIX if common else LIMIT - prefix)
        admitted = True
        cfg = read_json(old.checked(task["configuration"]))
        actor = M.Actor(task, out / "actor", resume_test_calls=test_calls)
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
        manifest = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        h = old.digest(manifest.read_bytes())
        counter = M.OfficialDeepSeekCounter(manifest, manifest_sha256=h)
        content, meta = M.load_official_content_counter(manifest, manifest_sha256=h)
        transport = M.DirectHTTPS(M.load_api_key(ROOT / ".env"), timeout_seconds=1800)
        names = {r["function"]["name"] for r in Profile().wire_tools()}
        worker = M.Backend(out / "api", meter, name, counter, transport, names, members=POOL)
        controller = M.Backend(
            out / "osa-api",
            meter,
            name,
            counter,
            transport,
            {"activate_organization"},
            members=POOL,
        )
        ex = Execution(
            worker.post, out / "telemetry", task["instance_id"], name, content_counter=content
        )
        owner = M.native.build_team_owner(
            ex.post,
            organization_id="FREE2",
            slot_id=name,
            condition_id="v248-common-harness",
            folder=out / "model-ledger",
            deadline=deadline,
            identity=dict(policy_version="v247", model="deepseek-flash", thinking=False),
            observation_token_counter=content,
            observation_tokenizer_id=meta["tokenizer_id"],
            require_content_counter=True,
        )
        w = install(prepared, owner)
        initial = (
            INSTRUCTION
            + "\n"
            + cfg["public_task"]["problem_statement"]
            + "\n"
            + M.public_context(cfg, actor.public)
        )
        rt, *_ = M.native.build_runtime(
            owner, prepared, out / "runtime", public_initial_message=initial, deadline=deadline
        )
        if case["initial"] == 3:
            w.bootstrap_three(
                "You are the third initial worker. Inspect the public task, agree on useful work and share evidence."
            )
            rt.sync_members()
        M.native.set_native_limit(rt, PREFIX if common else LIMIT)
        ex.runtime = rt
        ex.bind_recorder(rt)
        actor.bind_deadline(rt.deadline)
        signals = Signals()
        seen = set()
        osa_tokens = 0
        decision_records = []

        def propose(facts):
            nonlocal osa_tokens
            state = patch.public_state(w, rt, facts, arm)
            key = state["decision_key"]
            if key in seen:
                return
            request = patch.wire(state)
            estimate = counter.measure(request)["prompt_tokens"] + request["max_tokens"]
            if estimate > rt.team_budget.snapshot()["available_tokens"]:
                return
            seen.add(key)
            dest = out / "decisions" / f"{rt.opportunities:04d}"
            save(dest / "state.json", state)
            payload = dict(
                team_slot_id=name,
                request_id=name + ":osa:" + key,
                member_id=POOL[0],
                usage_id="agent",
                wire=request,
            )
            body = controller.post("/chat/completions", payload)
            used = body["usage"]["total_tokens"]
            osa_tokens += used
            rt.team_budget.native_allocation = LIMIT - osa_tokens
            try:
                (call,) = body["choices"][0]["message"].get("tool_calls") or []
                if call["function"]["name"] != "activate_organization":
                    raise ValueError("wrong tool")
                p = json.loads(call["function"]["arguments"])
                save(dest / "proposal.json", p)
                rec = patch.apply(w, rt, state, p)
                ex.current["graph"] = w.control()["version"]
            except (ValueError, KeyError, TypeError, ValidationError) as e:
                rec = dict(status="rejected", error=str(e)[:700])

            decision_records.append({**rec, "tokens": used, "opportunity": rt.opportunities})
            save(dest / "decision.json", decision_records[-1])

        if common:
            for m in rt.labels:
                rt.policies[m].conversation.send_message(
                    f"Initial active team size {case['initial']}. Begin the original issue. Share public findings, coordinate naturally and deliver explicitly."
                )
        else:
            restore_world(prepared, cp)
            rt.sync_members()
            proof = restore_runtime(prepared, rt, cp)
            actor.bind_deadline(rt.deadline)
            w.freeze_worker_graph()
            facts = read_json(cp.parent / "eligibility.json")
            save(
                out / "fork.json",
                dict(
                    proof=proof,
                    graph=patch.snapshot(w),
                    eligibility=facts,
                    initial_size=len(w.live_members()),
                ),
            )
            if arm != "K":
                propose(facts)

        def observe(o):
            M.after_opportunity(actor, out / "transport-fault.json")
            facts = signals.observe(w, rt.opportunities, o)
            if common:
                if not w.protocol()["terminal"]:
                    evidence = signals.qualify(w, case["initial"])
                    if evidence and any(
                        any(
                            x["operation"] == ("JOIN" if case["initial"] == 2 else "RETIRE")
                            for x in c["operations"]
                        )
                        for c in patch.public_state(w, rt, evidence, "O-DYNAMIC")[
                            "candidates"
                        ].values()
                    ):
                        save_checkpoint(
                            prepared,
                            rt,
                            cp,
                            control_state={"direction": case["initial"], "evidence": evidence},
                        )
                        save(out / "eligibility.json", evidence)
                        raise Window
                if rt.opportunities >= 32:
                    raise Window
            elif (
                arm != "K"
                and not w.protocol()["terminal"]
                and facts
                and ("incident" in facts or "work_event" in facts)
            ):
                propose(facts)
            save(
                out / "progress.json",
                dict(
                    opportunity=rt.opportunities,
                    osa_tokens=osa_tokens,
                    actual=owner.adapter.ledger.actual,
                    active=w.organization_active_members(),
                ),
            )

        try:
            end = M.native.run_fragment(prepared, rt, on_opportunity=observe)
        except Window:
            end = None
        if end is not None:
            save(out / "boundary.json", end)
            if end.get("execution_integrity_failure"):
                raise RuntimeError(str(end["execution_integrity_failure"]))
        if common:
            metaresult.update(
                status="qualified" if (cp / "manifest.json").is_file() else "no_eligible_state",
                tokens=owner.adapter.ledger.actual,
            )
        else:
            M.native.close_runtime(rt)
            rt = None
            save(
                out / "candidate-lock.json",
                M.native.lock_fixed_candidates(prepared, out / "closure", sdk_closed=True),
            )
            metaresult.update(
                status="closed",
                termination=end["termination_class"],
                logical_tokens=owner.adapter.ledger.actual + osa_tokens,
                decisions=decision_records,
                osa_tokens=osa_tokens,
                final_members=w.live_members(),
            )
    except Exception as e:
        metaresult.update(error=repr(e), traceback=traceback.format_exc())
    finally:
        for fn in (
            ([lambda: M.native.close_runtime(rt)] if rt else [])
            + ([actor.close] if actor else [])
            + ([lambda: meter.close(name)] if admitted else [])
        ):
            try:
                fn()
            except Exception as e:
                metaresult.setdefault("cleanup_errors", []).append(repr(e))
        save(out / "result.json", dict(metaresult, finished=time.time()))


def branch(case, arm):
    i = case["index"]
    dest = RUN / str(i) / arm
    result = account.batch.old.pre.isolated(
        Path(__file__).resolve(), ["--index", i, "--arm", arm], dest, "result.json"
    )
    scores = {}
    if result["status"] == "closed":
        for kind in ("code", "delivery"):
            receipt = account.batch.old.pre.isolated(
                ROOT / "tools/score_project_relations_v217_1.py",
                ["--index", i, "--kind", kind, "--episode", dest],
                dest.parent / (arm + "-" + kind),
                "receipt.json",
            )
            scores[kind] = {k: receipt.get(k) for k in ("status", "resolved", "error")}
    return dict(
        status=result["status"],
        scores=scores,
        error=result.get("error"),
        tokens=result.get("logical_tokens"),
        decisions=result.get("decisions"),
    )


def run(spec):
    (RUN / "tmp").mkdir(exist_ok=True, parents=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finished = set()
        for case in spec["rows"]:
            n = case["initial"]
            i = case["index"]
            base = RUN / str(i)
            if n in finished:
                continue
            base.mkdir(exist_ok=True)
            account.batch.old.pre.check_images(
                dict(roster=[dict(configuration=case["configuration"])])
            )
            try:
                reserve(i)
            except ValueError as e:
                if str(e) != "Full block exceeds available balance":
                    raise
                save(RUN / "cash-boundary.json", dict(index=i, required_CNY=120))
                break
            common = branch(case, "COMMON")
            if common["status"] != "qualified":
                allocate(i, None)
                save(base / "block.json", dict(common=common, arms={}))
                if common["status"] == "technical_unknown":
                    break
                continue
            allocate(i, read_json(base / "COMMON/checkpoint/manifest.json")["prefix_tokens"])
            with ThreadPoolExecutor(3) as pool:
                arms = dict(zip(ARMS, pool.map(lambda a: branch(case, a), ARMS), strict=True))
            save(base / "block.json", dict(common=common, arms=arms))
            finished.add(n)
            if any(a["status"] != "closed" for a in arms.values()):
                break


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--index", type=int)
    p.add_argument("--arm", choices=("COMMON", *ARMS))
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        register()
    else:
        spec = read_json(PLAN / "protocol.json")
        for f in spec["files"]:
            old.checked(f)
        old.checked(spec["bank"])
        old.checked(spec["authority"])
        if args.output:
            case = next(r for r in spec["rows"] if r["index"] == args.index)
            if args.output.resolve() != RUN / str(args.index) / args.arm:
                raise ValueError("Foreign branch")
            generate(case, args.arm, args.output)
        else:
            run(spec)
