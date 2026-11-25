"""Run the first two admitted, same-checkpoint KEEP/OSA pairs with frozen v240.4 responses."""

import argparse
import fcntl
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_repaired_osa_pair_v233 as paired
import run_commitment_prompt_v240_4 as prompt
from run_three_graph_v240 import PLAN as PREFLIGHT, sources, policy
from run_offline_scorer_v096 import launch_spec
from proworksim.software_context_panel_v231 import DESIGN, ROOT, PairedLedger, panel_row
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v241/paired-r1"
RUN = ROOT / "runs/software-benchmark-v241/paired-r1"
NS = "v241.1"
ARMS = ("KEEP", "OSA")
save = paired.save


def prepare():
    results = read_json(prompt.PLAN / "results.json")
    if results["pilot_thresholds"]["TEXT"] is not True:
        raise ValueError("Decision gate did not pass")
    states = read_json(DESIGN)["states"]
    rows = {s["id"]: s for s in sources()}
    oldrefs = read_json(PREFLIGHT / "references.json")
    roster = []
    for check in [a for a in read_json(PREFLIGHT / "worker-preflight.json") if a["eligible"]][:2]:
        sid = check["id"]
        row = rows[sid]
        state = states[check["index"]]
        manifest = read_json(ROOT / state["source_prefix"] / "checkpoint/manifest.json")
        (record,) = [
            r
            for r in results["records"]
            if r["site"] == sid and r["arm"] == "TEXT" and r["repeat"] == 1
        ]
        row = {**row, "probe_id": oldrefs[sid]["probe_id"]}
        body = read_json(checked(record["response"]))
        d = policy.parse(row, body)
        c = policy.compile_decision(row, d)
        expected = policy.dispatch(row, c, policy.base.apply_patch(row, c["patch"]))
        menu = read_json(ROOT / row["provenance"]["registered_menu"])
        menu = menu.get("menu", menu)
        commands = dict(zip(row["evidence"], row["provenance"]["commands"]))
        assert (
            record["valid"]
            and expected == record["binding"]
            and menu["graph"] == row["graph"]
            and menu["options"] == row["options"]
        )
        assert (
            manifest["identity"] == state["checkpoint"] == check["checkpoint"]
            and check["initial_budget"]
            == row["available_tokens"]
            == 5000000 - state["shared_prefix_usage"]
        )
        assert {commands[k] for k in d["basis"]} <= {
            v["command_id"] for v in menu["evidence"].values()
        }
        task = panel_row(state)
        roster.append(
            dict(
                **check,
                case=state["case"],
                probe=row["probe_id"],
                decision=record["response"],
                osa_tokens=record["input"] + record["output"],
                first_action=expected,
                option=c["patch"]["option"],
                configuration=task["configuration"],
                score_script=task["scorer_script"],
                score_index=task["source_index"],
            )
        )
    assert [r["id"] for r in roster] == ["q07", "q03"]
    return dict(
        roster=roster,
        cap=230000000000,
        block_hold=sum(r["pair_hold_nanoyuan"] for r in roster),
        opening_available=results["balance_nanoyuan"] - results["held_nanoyuan"],
        files=[
            reference(x)
            for x in [
                Path(__file__),
                Path(paired.episode_module.__file__),
                Path(policy.__file__),
                Path(prompt.__file__),
                prompt.PLAN / "results.json",
                PREFLIGHT / "worker-preflight.json",
                DESIGN,
            ]
        ],
        protocol="First batch only: two matched, independent two-worker branches per checkpoint. KEEP uses native incumbent roles; OSA activates the first registered decision from the admitted prompt, debits its archived usage logically only once, and tells the assigned worker its ordered first action and remaining evidence-backed obligations. Rejection is recorded with incumbent fallback. Same T1 context, tools, budget, scorer; no hidden feedback or second decision generation. Score final tree and final legal submission separately. Record actor opportunity, source-backed diagnosis, delivery and adoption, anomaly resolution, duration and actual usage. No outcome resampling or C/N update.",
    )


class Replay(paired.EvidenceFollowupExecution):
    def decide(self, node, observer, frozen, arm):
        item = self.binding
        row = next(r for r in sources() if r["id"] == item["id"])
        row = {**row, "probe_id": item["probe"]}
        if (
            frozen["graph"] != row["graph"]
            or frozen["options"] != row["options"]
            or observer != row["observer"]
            or self.runtime.team_budget.snapshot()["available_tokens"] != item["initial_budget"]
        ):
            raise ValueError("Working state does not match registered decision")
        if arm == "KEEP":
            return super().decide(node, observer, frozen, arm)
        d = policy.parse(row, read_json(checked(item["decision"])))
        c = policy.compile_decision(row, d)
        commands = dict(zip(row["evidence"], row["provenance"]["commands"]))
        allowed = {ev["command_id"]: k for k, ev in frozen["evidence"].items()}
        self.native_limit -= item["osa_tokens"]
        self.runtime.team_budget.native_allocation = self.native_limit
        choice = dict(
            option=c["patch"]["option"],
            evidence=[allowed[commands[k]] for k in d["basis"]],
            reason=d["reason"],
        )
        active = self.activate(node, observer, frozen, choice)
        rejected = active if active.get("activated") is False else None
        binding = None
        if rejected:
            active = self.activate(
                node,
                observer,
                frozen,
                dict(
                    option="K",
                    evidence=choice["evidence"],
                    reason="Retain organization after activation rejection",
                ),
            )
        else:
            binding = policy.dispatch(row, c, active["after"])
            import json

            self.runtime.policies[binding["actor"]].conversation.send_message(
                "Work under the activated organization. First action: "
                + json.dumps(binding)
                + ". Outstanding commitments: "
                + json.dumps(c["effective"])
                + ". Completion evidence: "
                + c["execution"]["completion_evidence"]
                + ". Reassess when: "
                + d["reconsider_after"]
                + "."
            )
        return active, dict(
            source="frozen_v240.4_first_response",
            proposal=d,
            option=choice["option"],
            osa_tokens=item["osa_tokens"],
            first_action=binding,
            activation_rejection=rejected,
            expected_graph=policy.base.apply_patch(row, c["patch"]),
            obligations=c["effective"],
            graph_patch=c["patch"],
            new_controller_calls=0,
        )


def reserve(meter, spec):
    expected = {
        NS + ":" + r["case"] + ":" + arm: r["initial_budget"]
        for r in spec["roster"]
        for arm in ARMS
    }
    with meter.db() as db:
        cap = db.execute("select value from meta where key='cap'").fetchone()[0]
        if int(cap) != meter.cap or meter.cap != spec["cap"]:
            raise ValueError("Cash limit differs")
        existing = dict(
            db.execute("select slot,token_limit from block_slots where block_id=?", (NS,))
        )
        if existing:
            if existing != expected:
                raise ValueError("Conflicting block")
            return
        spent = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        if spent + held + pending + spec["block_hold"] > meter.cap:
            raise ValueError("Insufficient cash for both pairs")
        db.executemany(
            "insert into block_slots values(?,?,?,'pending')",
            [(s, NS, b) for s, b in expected.items()],
        )


def isolated(script, args, out, receipt):
    if (out / receipt).is_file():
        return read_json(out / receipt)
    log = out.with_suffix(".log")
    if log.exists() or out.exists():
        return {"status": "technical_unknown", "error": "Prior attempt needs reconciliation"}
    command, env = launch_spec([str(script), *map(str, args), "--output", str(out)])
    with log.open("xb") as stream:
        code = subprocess.run(
            command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT
        ).returncode
    return (
        read_json(out / receipt)
        if (out / receipt).exists()
        else {"status": "technical_unknown", "returncode": code}
    )


def branch(item, arm):
    case = RUN / item["case"]
    case.mkdir(exist_ok=True)
    dest = case / arm
    result = isolated(Path(__file__).resolve(), ["--arm", arm], dest, "result.json")
    scores = {}
    if result["status"] == "closed":
        for kind in ("code", "delivery"):
            r = isolated(
                ROOT / "tools" / item["score_script"],
                ["--index", item["score_index"], "--kind", kind, "--episode", dest],
                case / (arm + "-" + kind),
                "receipt.json",
            )
            scores[kind] = {k: r.get(k) for k in ("status", "resolved", "error")}
    return {
        "result": {
            k: result.get(k) for k in ("status", "termination", "option", "logical_tokens", "error")
        },
        "scores": scores,
    }


def check_images(spec):
    import docker, shutil

    for item in spec["roster"]:
        cfg = read_json(checked(item["configuration"]))
        s = cfg["scorer_request_base"]
        with closing(
            docker.DockerClient(
                base_url="unix://" + str(Path(s["docker_socket"]).resolve()), timeout=12
            )
        ) as client:
            mapping = read_json(checked(s["baseline_mapping"]))
            for image in [mapping["actor_image_id"], s["image"]["image_id"]]:
                client.images.get(image)
            if shutil.disk_usage(client.info()["DockerRootDir"]).free < 16 * 1024**3:
                raise ValueError("Low space for four isolated environments")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--arm", choices=ARMS)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    dest = PLAN / "protocol.json"
    if args.freeze:
        spec = prepare()
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Frozen protocol differs")
        save(dest, spec)
        return
    spec = read_json(dest)
    for f in spec["files"]:
        checked(f)
    if args.arm:
        (item,) = [r for r in spec["roster"] if r["case"] == args.output.parent.name]
        if args.output != RUN / item["case"] / args.arm:
            raise ValueError("Invalid path")

        class Bound(Replay):
            pass

        Bound.binding = item
        fn = paired.episode_module.episode
        paired.clone_function(fn, {**fn.__globals__, "RUN": RUN, "OrganizationExecution": Bound})(
            item["index"],
            args.arm,
            args.output,
            False,
            slot_namespace=NS,
            expected_case=item["case"],
        )
        return
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (RUN / "tmp").mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(RUN / "tmp")
        check_images(spec)
        auth = read_json(prompt.RUN / "authority.json")
        auth.update(
            scope="two v241 KEEP/OSA matched pairs",
            available_on_approval_nanoyuan=spec["opening_available"],
        )
        save(RUN / "authority.json", auth)
        reserve(PairedLedger.load(RUN / "authority.json"), spec)
        records = {}
        with ThreadPoolExecutor(4) as pool:
            jobs = {
                pool.submit(branch, r, arm): r["case"] + "/" + arm
                for r in spec["roster"]
                for arm in ARMS
            }
            for f in as_completed(jobs):
                try:
                    records[jobs[f]] = f.result()
                except Exception as exc:
                    records[jobs[f]] = {"status": "technical_unknown", "error": repr(exc)}
                save(RUN / "progress.json", records)
        save(RUN / "completed.json", records)


if __name__ == "__main__":
    main()
