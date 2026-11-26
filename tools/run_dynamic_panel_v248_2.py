"""v248 public test pool repair. Replay interrupted SDK responses before permitting new billing."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import argparse
import fcntl
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dynamic_panel_v248 as first
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_graph_controller_v228 import PROJECT
from proworksim.storage import read_json

ROOT = first.ROOT
NEW = "v248.2"
RUN = ROOT / "runs/software-benchmark-v248/dynamic-membership-r2"
PLAN = ROOT / "artifacts/software-benchmark-v248/dynamic-membership-r2"
old = first.old


class Actor(first.M.Actor):
    dynamic_test_pool = True

    def test(self, *, files, entry_metadata, request):
        if (
            self.world.scheduled_member != request["actor_id"]
            or request["actor_id"] not in self.world.live_members()
        ):
            raise ValueError("Public test must be issued by the scheduled live member")
        return super().test(files=files, entry_metadata=entry_metadata, request=request)


def prepare_case(*args, **kwargs):
    prepared = first.M.substrate.prepare_case(*args, **kwargs)
    kwargs["public_test_callback"].__self__.world = prepared.world
    return prepared


def actor_control():
    i = 1
    task = next(x for x in read_json(first.BANK)["rows"] if x["index"] == i)
    out = RUN / "actor-control"
    out.mkdir(exist_ok=False, parents=True)
    act = Actor(task, out / "actor")
    try:
        act.start()
        original = read_json(first.RUN / "1/K/public-test-rpc/test-0001/request.json")
        assert (
            original["actor_id"] == "member_003"
            and original["tree_sha256"] == act.baseline["tree"]["tree_sha256"]
        )
        dl = first.M.DispatchDeadline(soft_seconds=300, hard_seconds=420)
        act.bind_deadline(dl)
        q = {**original, "hard_deadline_monotonic": dl.hard_at}
        act.world = SimpleNamespace(
            scheduled_member="member_003",
            live_members=lambda: ["member_001", "member_002", "member_003"],
        )
        result = act.test(
            files=act.baseline["files"], entry_metadata=act.baseline["entry_metadata"], request=q
        )
        assert result["execution"]["actor_id"] == "member_003" and result["execution"].get(
            "command_executed", True
        )
        act.world.scheduled_member = "member_001"
        try:
            act.test(
                files=act.baseline["files"],
                entry_metadata=act.baseline["entry_metadata"],
                request=q,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Unscheduled tester")
        first.save(
            PLAN / "actor-control.json",
            dict(
                actor=q["actor_id"],
                selection=q["public_test_selection"],
                outcome=result.get("passed"),
                execution=result["execution"],
                hidden_evaluation=False,
                model_calls=0,
            ),
        )
    finally:
        act.close()


def register():
    plan = read_json(first.PLAN / "protocol.json")
    tasks = []
    for arm in first.ARMS:
        dest = first.RUN / "1" / arm
        r = read_json(dest / "result.json")
        if r["status"] == "closed":
            continue
        fault = read_json(dest / "transport-fault.json")
        assert "Selected tests lost their role" in str(fault)
        tape = []
        for p in [*dest.glob("api/*/usage.json"), *dest.glob("osa-api/*/usage.json")]:
            rq = p.with_name("request.json")
            record = read_json(rq)
            tape.append(
                dict(
                    t=record["time"],
                    request=old.reference(rq),
                    response=old.reference(p.with_name("response.json")),
                    usage=old.reference(p),
                    kind=p.parents[1].name,
                )
            )
        tape.sort(key=lambda x: x["t"])
        tests = sorted(dest.glob("public-test-rpc/test-*/request.json"))
        failed = read_json(tests[-1])
        assert failed["actor_id"] == "member_003"
        tasks.append(
            dict(
                arm=arm,
                tape=tape,
                test=old.reference(tests[-1]),
                before=old.reference(dest / "result.json"),
            )
        )
    first.freeze(
        PLAN / "protocol.json",
        dict(
            parent=old.reference(first.PLAN / "protocol.json"),
            rows=plan["rows"],
            recovery=tasks,
            files=[
                old.reference(p)
                for p in (
                    Path(__file__),
                    ROOT / "src/proworksim/software_benchmark_managed_actor_v203_2_3_r5.py",
                    ROOT / "src/proworksim/software_delegation_actor_v203_3_3_r2.py",
                )
            ],
            scope="Same SymPy checkpoint; preserve the scored O-FIXED arm. Failed branches must reproduce all paid request wires before dispatching new work, with the previously rejected third-member test actually executed. Continue original expansion recruitment after repair.",
        ),
    )
    return tasks


def resume_slot(i, a):
    return f"{NEW}:{i}:{a}"


def block_reserve(recoveries):
    meter = first.PairedLedger.load(first.AUTH)
    with meter.db() as db:
        prefix = read_json(first.RUN / "1/COMMON/checkpoint/manifest.json")["prefix_tokens"]
        limits = {
            resume_slot(1, r["arm"]): first.LIMIT
            - prefix
            - sum(read_json(old.checked(v["usage"]))["total_tokens"] for v in r["tape"])
            for r in recoveries
        }
        existing = dict(
            db.execute(
                "select slot,token_limit from block_slots where block_id=?", (NEW + ":repair",)
            )
        )
        if existing:
            if existing != limits:
                raise ValueError("Recovery exposure changed")
            return
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Account limit")
        used = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        holds = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        waiting = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        if used + holds + waiting + sum(limits.values()) * 8000 > meter.cap:
            raise ValueError("Insufficient funds for both unfinished arms")
        db.executemany(
            "insert into block_slots values(?,?,?,'pending')",
            [(k, NEW + ":repair", v) for k, v in limits.items()],
        )


def generate(case, arm, out, spec):
    i = case["index"]
    recovered = i == 1
    logical = first.slot(i, arm) if recovered else resume_slot(i, arm)
    physical = resume_slot(i, arm)
    record = next((r for r in spec["recovery"] if r["arm"] == arm), {}) if recovered else {}
    tape = record.get("tape", [])
    pos = 0
    tested = False
    real = first.PairedLedger.load(first.AUTH)
    used = sum(read_json(old.checked(x["usage"]))["total_tokens"] for x in tape)

    class Account:
        def admit(self, slot, limit):
            if slot != logical:
                raise ValueError("Unexpected slot")
            real.admit(physical, limit - used)

        def close(self, slot):
            real.close(physical)

    class RepairActor(Actor):
        def test(self, **kwargs):
            nonlocal tested
            result = super().test(**kwargs)
            if record and pos == len(tape):
                prior = read_json(old.checked(record["test"]))
                q = kwargs["request"]
                if all(
                    q[k] == prior[k]
                    for k in (
                        "actor_id",
                        "source_reference",
                        "public_test_selection",
                        "tree_sha256",
                        "call_index",
                    )
                ):
                    tested = True
            return result

    def backend(folder, meter, slot, counter, transport, names, **kwargs):
        delegate = first.M.Backend(folder, real, physical, counter, transport, names, **kwargs)

        def post(route, payload):
            nonlocal pos
            payload_live = {**payload, "team_slot_id": physical}
            if route != "/chat/completions":
                return delegate.post(route, payload_live)
            if pos < len(tape):
                item = tape[pos]
                actual = payload["wire"]
                saved = read_json(old.checked(item["request"]))["payload"]
                same = json.loads(json.dumps(actual)) == saved["wire"]
                if (
                    not same
                    or item["kind"] != folder.name
                    or any(saved[k] != payload[k] for k in ("member_id", "usage_id", "request_id"))
                ):
                    first.save(
                        out / "replay-mismatch.json",
                        dict(position=pos, expected=item["request"], actual=payload),
                    )
                    raise ValueError("Historical request mismatch; no replacement sampling")
                pos += 1
                first.save(out / "replay.json", dict(replayed=pos, expected=len(tape), new_cost=0))
                return read_json(old.checked(item["response"]))
            if record and not tested:
                raise ValueError("Third-member public test has not been recovered")
            return delegate.post(route, payload_live)

        return SimpleNamespace(post=post)

    module = SimpleNamespace(
        **{
            **vars(first.M),
            "Actor": RepairActor,
            "Backend": backend,
            "substrate": SimpleNamespace(
                **{**vars(first.M.substrate), "prepare_case": prepare_case}
            ),
        }
    )
    fn = clone_function(
        first.generate,
        {
            **vars(first),
            "M": module,
            "RUN": first.RUN if recovered else RUN,
            "slot": lambda index, a: logical,
            "PairedLedger": SimpleNamespace(load=lambda _: Account()),
        },
    )
    fn(case, arm, out)


def branch(case, arm):
    i = case["index"]
    dest = RUN / str(i) / arm
    dest.parent.mkdir(exist_ok=True, parents=True)
    result = first.account.batch.old.pre.isolated(
        Path(__file__).resolve(), ["--index", i, "--arm", arm], dest, "result.json"
    )
    scores = {}
    if result["status"] == "closed":
        for kind in ("code", "delivery"):
            score = first.account.batch.old.pre.isolated(
                ROOT / "tools/score_project_relations_v217_1.py",
                ["--index", i, "--kind", kind, "--episode", dest],
                dest.parent / (arm + "-" + kind),
                "receipt.json",
            )
            scores[kind] = {k: score.get(k) for k in ("status", "resolved", "error")}
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
        block_reserve(spec["recovery"])
        case = next(r for r in spec["rows"] if r["index"] == 1)
        arms = [r["arm"] for r in spec["recovery"]]
        with ThreadPoolExecutor(len(arms)) as pool:
            values = dict(zip(arms, pool.map(lambda a: branch(case, a), arms), strict=True))
        first.save(RUN / "1/recovery.json", values)
        # Failure to reproduce an old request does not prevent the independent expansion block.
        ns = {**vars(first), "NS": NEW, "RUN": RUN, "slot": resume_slot}
        reserve = clone_function(first.reserve, ns)
        allocate = clone_function(first.allocate, ns)
        for case in spec["rows"]:
            i = case["index"]
            if case["initial"] != 2 or i == 0:
                continue
            first.account.batch.old.pre.check_images(
                dict(roster=[dict(configuration=case["configuration"])])
            )
            reserve(i)
            common = branch(case, "COMMON")
            dest = RUN / str(i)
            if common["status"] != "qualified":
                allocate(i, None)
                first.save(dest / "block.json", dict(common=common, arms={}))
                if common["status"] == "technical_unknown":
                    return
                continue
            allocate(i, read_json(dest / "COMMON/checkpoint/manifest.json")["prefix_tokens"])
            with ThreadPoolExecutor(3) as pool:
                values = dict(
                    zip(first.ARMS, pool.map(lambda a: branch(case, a), first.ARMS), strict=True)
                )
            first.save(dest / "block.json", dict(common=common, arms=values))
            return


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--control", action="store_true")
    p.add_argument("--index", type=int)
    p.add_argument("--arm", choices=("COMMON", *first.ARMS))
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        register()
    elif args.control:
        actor_control()
    else:
        spec = read_json(PLAN / "protocol.json")
        old.checked(spec["parent"])
        for f in spec["files"]:
            old.checked(f)
        if args.output:
            if args.output.resolve() != RUN / str(args.index) / args.arm:
                raise ValueError("Foreign path")
            generate(
                next(r for r in spec["rows"] if r["index"] == args.index),
                args.arm,
                args.output,
                spec,
            )
        else:
            if not (PLAN / "actor-control.json").exists():
                raise ValueError("Missing real three-member test control")
            run(spec)
