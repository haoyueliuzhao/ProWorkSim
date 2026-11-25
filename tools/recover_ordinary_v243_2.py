"""Verify the paid natural suffix off-line before continuing from the exact material world."""

import argparse
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sys
import subprocess
import fcntl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as old
from proworksim.software_prefix_resume_v243_2 import resume_stage_limited_members
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json, json_bytes, digest
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import PairedLedger

RUN = old.RUN / "recovery"
PAID = old.RUN / "ordinary"
PLAN = old.PLAN / "recovery.json"


def prepare():
    spec = read_json(old.PLAN / "protocol.json")
    result = read_json(PAID / "result.json")
    boundary = read_json(PAID / "boundary.json")
    stage = old.ROOT / spec["case"]["source"] / "runtime/experience.jsonl"
    events = []
    for line in stage.open():
        if '"model_boundary_error"' in line:
            e = json.loads(line)
            if e["kind"] == "model_boundary_error":
                p = e["payload"]
                b = p["team_budget"]
                events.append(
                    dict(
                        kind=e["kind"],
                        sequence=e["sequence"],
                        worker_id=e["worker_id"],
                        payload={
                            **p,
                            "team_budget": {k: v for k, v in b.items() if k != "records"},
                        },
                    )
                )
    tape = []
    for f in (PAID / "api").glob("*/response.json"):
        q = f.with_name("request.json")
        u = f.with_name("usage.json")
        tape.append(
            dict(
                time=read_json(q)["time"],
                request=reference(q),
                response=reference(f),
                usage=reference(u),
            )
        )
    tape.sort(key=lambda t: t["time"])
    limit = spec["limit"] - result["logical_tokens"]
    assert (
        len(tape)
        and sum(read_json(checked(t["usage"]))["total_tokens"] for t in tape)
        == result["logical_tokens"] - spec["case"]["prefix"]
    )
    assert boundary["role_stops"] == {"member_001": "team_budget_exhausted"}
    old.pairs.previous.freeze(
        PLAN,
        dict(
            case=spec["case"],
            events=events,
            tape=tape,
            earlier=reference(PAID / "result.json"),
            boundary=reference(PAID / "boundary.json"),
            limit=limit,
            new_slot=spec["slot"] + "-r1",
            shared_cap=spec["cap"],
            rule="Reuse all paid responses. Require matching member, request identity and model-visible content; verify the settled actions, material world and prefix-inclusive account before any new call. Release only a stop tied to the old 2M prefix allocation. Close and grade both locked endpoints; post-repair calls alone are billed.",
        ),
    )
    print("paid tape length", len(tape), "remaining", limit)


def restore_time_metadata(prepared, original, outcomes):
    # Only elapsed wall time and the hashes of transitions that embed it may differ.
    replay = prepared.world.store.load()
    actions = {
        r["response"]["action_id"] for r in outcomes if (r.get("response") or {}).get("action_id")
    }
    commands = {
        r["response"]["command_id"] for r in outcomes if (r.get("response") or {}).get("command_id")
    }
    count = 0
    for left, right in zip(replay["interactions"], original["interactions"], strict=True):
        if left["action_id"] not in actions or left["action_id"] != right["action_id"]:
            continue
        if left.get("wall_seconds") != right.get("wall_seconds"):
            left["wall_seconds"] = right["wall_seconds"]
            count += 1
        if "state_digests" in (left.get("transition") or {}):
            left["transition"]["state_digests"] = right["transition"]["state_digests"]
    for cmd in commands:
        l = replay["operation_commits"][cmd]["receipt"]
        r = original["operation_commits"][cmd]["receipt"]
        if "state_digests" in l:
            l["state_digests"] = r["state_digests"]
    if replay != original:
        raise ValueError("Non-timing world fields diverged")
    with prepared.world.store.lock():
        prepared.world.store.save(original)
        prepared.world.state = prepared.world.store.load()
    if prepared.world.state != original:
        raise ValueError("Archived world was not restored exactly")
    return count


def execute(out, spec, cfg):
    real = PairedLedger.load(old.AUTH)
    remaining = cfg["limit"]
    slot = cfg["new_slot"]
    source = read_json(checked(cfg["boundary"]))
    first_count = len(cfg["tape"])
    stream = [*cfg["tape"], *cfg.get("additional_tape", [])]
    state = {"position": 0, "live": False, "admitted": False}

    class Account:
        path = real.path

        def admit(self, historical, limit):
            if historical != spec["slot"] or limit != 5000000 - cfg["case"]["prefix"]:
                raise ValueError("Unexpected logical slot")

        def close(self, historical):
            if state["admitted"]:
                real.close(slot)

    def account(_):
        return Account()

    def backend(path, meter, historical, counter, transport, names):
        fresh = old.M.Backend(path, real, slot, counter, transport, names)

        def post(route, payload):
            if route != "/chat/completions":
                return fresh.post(route, payload)
            if state["live"] and state["position"] == len(stream):
                if not state.get("test_recovered", not cfg.get("additional_tape")):
                    raise ValueError("Previous test action has not returned a trusted receipt")
                return fresh.post(route, {**payload, "team_slot_id": slot})
            i = state["position"]
            if i >= len(stream):
                raise ValueError("Attempted unregistered historical generation")
            item = stream[i]
            record = read_json(checked(item["request"]))["payload"]
            actual = json.loads(json.dumps(payload["wire"]))
            if any(record[k] != payload[k] for k in ("member_id", "usage_id", "request_id")):
                raise ValueError("Tape request identity differs")
            if actual != record["wire"]:
                old.save(
                    out / "wire-difference.json",
                    dict(index=i, expected=item["request"], actual=actual),
                )
                raise ValueError("Model-visible historical request differs at " + str(i))
            state["position"] += 1
            return read_json(checked(item["response"]))

        return SimpleNamespace(post=post)

    def fragment(prepared, rt, **kw):
        recorded = old.M.native.run_fragment(prepared, rt)
        if (
            state["position"] != first_count
            or recorded["opportunities"] != source["opportunities"]
            or rt.owner.adapter.ledger.actual
            != read_json(checked(cfg["earlier"]))["logical_tokens"]
        ):
            raise ValueError("Historical boundary or charged tokens differ")
        for i, (left, right) in enumerate(
            zip(recorded["outcomes"], source["outcomes"], strict=True)
        ):
            if left != right:
                old.save(
                    out / "outcome-difference.json", dict(index=i, actual=left, expected=right)
                )
                raise ValueError("Historical action or receipt differs at " + str(i))
        original = read_json(PAID / "prepared/world/control/state.json")
        if cfg.get("restore_recorded_timing"):
            restore_time_metadata(prepared, original, recorded["outcomes"])
            old_receipt = read_json(PAID / "restore.json")["remaining_time_at_resume"]
            old_result = read_json(PAID / "result.json")
            elapsed = max(
                rt.deadline.clock() - rt.deadline.started,
                old_receipt["elapsed"] + old_result["finished"] - old_result["started"],
            )
            dr = source["deadline_receipt"]
            old.M.resume.reset_clock(
                rt,
                prepared,
                dict(
                    elapsed=elapsed,
                    soft_remaining=dr["soft_seconds"] - elapsed,
                    hard_remaining=dr["hard_seconds"] - elapsed,
                ),
            )
        if cfg.get("additional_tape"):
            state["actor"].bind_deadline(rt.deadline)
        if prepared.world.store.load() != original:
            raise ValueError("Material world differs after replay")
        if rt.stopped != source["role_stops"] or rt.schedule.snapshot() != source["schedule"]:
            raise ValueError("Restored schedule differs")
        repairs = resume_stage_limited_members(rt, cfg["events"])
        if not repairs:
            raise ValueError("No specifically proven prefix stop can be released")
        real.admit(slot, remaining)
        state.update(live=True, admitted=True)
        old.save(
            out / "verified-resume.json",
            dict(
                replayed=first_count,
                replayed_opportunities=len(recorded["outcomes"]),
                unchanged_world=digest(json_bytes(original)),
                new_charges_at_gate=0,
                released=repairs,
                used_at_gate=rt.owner.adapter.ledger.actual,
            ),
        )
        before = source["opportunities"] - len(source["outcomes"])
        suffix = [dict(ordinal=i, outcome=o) for i, o in enumerate(source["outcomes"], before + 1)]
        kw["history"] = [*kw["history"], *suffix]
        if cfg.get("additional_tape"):
            original_callback = kw["on_opportunity"]
            recorded_actions = cfg["additional_receipts"]

            def repaired_action(o):
                ordinal = rt.opportunities - source["opportunities"]
                if 1 <= ordinal <= len(recorded_actions):
                    original_action = recorded_actions[ordinal - 1]
                    if (
                        o.get("response") != original_action["response"]
                        or o.get("worker_id") != original_action["member"]
                        or o.get("decision", {}).get("model_tool_call_id")
                        != original_action["call"]
                    ):
                        raise ValueError("Prior post-resume action/receipt differs")
                elif not state.get("test_recovered"):
                    v = (o.get("response") or {}).get("result") or {}
                    if (
                        state["position"] != len(stream)
                        or o.get("decision", {}).get("model_tool_call_id") != cfg["last_tool_call"]
                        or not v.get("executed")
                        or rt.owner.adapter.ledger.actual != 5000000 - remaining
                    ):
                        raise ValueError(
                            "Interrupted public-test action did not close on the same request"
                        )
                    state["test_recovered"] = True
                    old.save(
                        out / "verified-test-recovery.json",
                        dict(
                            historical_wires=len(stream),
                            verified_post_repair_actions=len(recorded_actions),
                            original_tool_call=cfg["last_tool_call"],
                            public_test_passed=v.get("passed"),
                            executed=True,
                            at=rt.opportunities,
                            logical_tokens=rt.owner.adapter.ledger.actual,
                            new_provider_calls=0,
                        ),
                    )
                original_callback(o)

            kw["on_opportunity"] = repaired_action
        final = old.run_worker_fragment(prepared, rt, **kw)
        if state["position"] != len(stream) or (
            cfg.get("additional_tape") and not state.get("test_recovered")
        ):
            raise ValueError("Continuation ended before the registered recovery boundary")
        return final

    def actor_factory(*args, **kwargs):
        obj = old.M.Actor(*args, **kwargs)
        state["actor"] = obj
        return obj

    mod = SimpleNamespace(**{**vars(old.M), "Backend": backend, "Actor": actor_factory})
    fn = clone_function(
        old.generate,
        {
            **old.generate.__globals__,
            "M": mod,
            "PairedLedger": SimpleNamespace(load=account),
            "run_worker_fragment": fragment,
        },
    )
    try:
        fn(spec, out)
    finally:
        if (out / "result.json").exists():
            r = read_json(out / "result.json")
            old.save(
                out / "result.json",
                {
                    **r,
                    "slot": slot,
                    "logical_parent_slot": spec["slot"],
                    "replay_count": state["position"],
                    "historical_usage": 5000000 - remaining,
                },
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--clock-adjusted", action="store_true")
    p.add_argument("--rpc-adjusted", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    global RUN, PLAN
    child_args = []
    if a.rpc_adjusted:
        original = read_json(old.PLAN / "recovery-clock.json")
        previous = old.RUN / "recovery-clock" / "ordinary"
        RUN = old.RUN / "recovery-rpc"
        PLAN = old.PLAN / "recovery-rpc.json"
        child_args = ["--rpc-adjusted"]
        if a.freeze:
            fault = read_json(previous / "transport-fault.json")
            if fault["reason"].get("message") != "Callback/RPC deadline mismatch":
                raise ValueError("Unexpected transport fault")
            extra = []
            for f in (previous / "api").glob("*/response.json"):
                req = f.with_name("request.json")
                extra.append(
                    dict(
                        time=read_json(req)["time"],
                        request=reference(req),
                        response=reference(f),
                        usage=reference(f.with_name("usage.json")),
                    )
                )
            extra.sort(key=lambda r: r["time"])
            calls = [
                read_json(checked(x["response"]))["choices"][0]["message"]["tool_calls"][0]
                for x in extra
            ]
            assert calls[-1]["function"]["name"] == "run_tests"
            ids = [a["id"] for a in calls]
            prior = []
            for line in (previous / "runtime/experience.jsonl").open("rb"):
                if b'"tool_call"' not in line:
                    continue
                ev = json.loads(line)
                if (
                    ev["kind"] == "tool_call"
                    and ev["payload"].get("model_tool_call_id") in ids[:-1]
                ):
                    payload = ev["payload"]
                    prior.append(
                        dict(
                            call=payload["model_tool_call_id"],
                            response=payload["response"],
                            member=ev["worker_id"],
                        )
                    )
            assert [x["call"] for x in prior] == ids[:-1]
            costs = sum(read_json(checked(x["usage"]))["total_tokens"] for x in extra)
            old.pairs.previous.freeze(
                PLAN,
                {
                    **original,
                    "new_slot": original["new_slot"].removesuffix("r2") + "r3",
                    "limit": original["limit"] - costs,
                    "additional_tape": extra,
                    "additional_receipts": prior,
                    "last_tool_call": ids[-1],
                    "fault": reference(previous / "transport-fault.json"),
                    "reason": "Rebind the actor deadline after SDK clock restoration. Replay both committed segments, require all completed receipts, then execute exactly the original failed public-test call. No fresh model sampling or billing before the corrected native test returns.",
                },
            )
            return
    elif a.clock_adjusted:
        base = read_json(PLAN)
        prev = read_json(RUN / "ordinary/result.json")
        if prev.get("error") != "ValueError('Material world differs after replay')" or prev.get(
            "replay_count"
        ) != len(base["tape"]):
            raise ValueError("Unexpected first replay status")
        RUN = old.RUN / "recovery-clock"
        PLAN = old.PLAN / "recovery-clock.json"
        child_args = ["--clock-adjusted"]
        if a.freeze:
            old.pairs.previous.freeze(
                PLAN,
                dict(
                    **{**base, "new_slot": base["new_slot"].removesuffix("r1") + "r2"},
                    restore_recorded_timing=True,
                    reason="All 12 wires, responses and 11 action receipts matched in R1. Restore only archived wall_seconds and the associated derived hashes for these commands. All remaining state must match and original bytes are loaded before live dispatch.",
                ),
            )
            return
    elif a.freeze:
        return prepare()
    spec = read_json(old.PLAN / "protocol.json")
    cfg = read_json(PLAN)
    dest = RUN / "ordinary"
    if a.output:
        if a.output != dest:
            raise ValueError("Foreign replay path")
        return execute(dest, spec, cfg)
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meter = PairedLedger.load(old.AUTH)
        slot = cfg["new_slot"]
        reserve = clone_function(
            old.pairs.previous.prior.paired.reserve,
            {**old.pairs.previous.prior.paired.reserve.__globals__, "ARMS": (slot.split(":")[-1],)},
        )
        reserve(
            old.AUTH,
            dict(
                case=slot.split(":")[1],
                arm_limit=cfg["limit"],
                worst_pair_nanoyuan=cfg["limit"] * 8000,
                account_cap_nanoyuan=spec["cap"],
            ),
            namespace="v243.2",
            block=slot,
        )
        os.environ["TMPDIR"] = str(old.RUN / "tmp")
        result = old.pairs.previous.prior.isolated(
            Path(__file__).resolve(), child_args, dest, "result.json"
        )
        scores = {}
        if result["status"] == "closed":
            for k in ("code", "delivery"):
                scores[k] = old.pairs.previous.prior.isolated(
                    old.ROOT / "tools/score_project_relations_v217_1.py",
                    ["--index", spec["case"]["index"], "--kind", k, "--episode", dest],
                    RUN / k,
                    "receipt.json",
                ).get("resolved")
        else:
            with meter.db() as db:
                db.execute(
                    "update block_slots set status='released' where slot=? and status='pending'",
                    (slot,),
                )
        old.save(
            RUN / "completed.json",
            dict(status=result["status"], scores=scores, error=result.get("error")),
        )
        if result["status"] == "closed":
            cmd, env = old.launch_spec([str(old.ROOT / "tools/drain_event_pairs_v243.py")])
            subprocess.run(cmd, cwd=old.ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
