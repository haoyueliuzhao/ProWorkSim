"""No-network SDK admission control for the v247 lifecycle and structured OSA wire."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json, os, subprocess, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa as live
from run_offline_scorer_v096 import launch_spec
from proworksim.software_membership_v247 import POOL, install
from proworksim.software_organization_patch_v247 import (
    public_state,
    apply,
    op,
    sha,
    wire,
    validate,
    candidate,
)
from proworksim.software_fixed_organization_clone_v131 import clone_function


def answer(state, key, action="CHANGE"):
    c = state["candidates"].get(key)
    ops = c["operations"] if c else []
    add = [x["member"] for x in ops if x["operation"] in {"JOIN", "RESUME"}]
    remove = [x["member"] for x in ops if x["operation"] in {"RETIRE", "PAUSE"}]
    size = sum(s == "live" for s in state["organization_graph"]["members"].values())
    return dict(
        assessment=dict(
            anomaly_type="UNKNOWN",
            evidence_refs=list(state["project_graph"]),
            current_organization_blocker="inspect open work",
        ),
        decision=dict(action=action, candidate_id=key, reason="test public package coverage"),
        membership_decision=dict(
            action=next(
                (
                    {
                        "JOIN": "ADD_MEMBER",
                        "RETIRE": "RETIRE_MEMBER",
                        "PAUSE": "PAUSE_MEMBER",
                        "RESUME": "RESUME_MEMBER",
                    }[x["operation"]]
                    for x in ops
                    if x["dimension"] == "D0"
                ),
                "KEEP_SIZE",
            ),
            current_active_members=size,
            proposed_active_members=size + len(add) - len(remove),
            members_to_activate=add,
            members_to_retire=remove,
        ),
        organization_patch=dict(
            base_graph_version=state["organization_graph"]["version"],
            base_hash=state["base_hash"],
            target_graph_version=state["organization_graph"]["version"] + len(ops),
            operations=ops,
        ),
        expected_contribution={
            k: (c.get(k, "observable in test") if c else "none")
            for k in (
                "producer",
                "consumer",
                "artifact",
                "intended_use",
                "verification",
                "failure_condition",
            )
        },
        execution_plan=dict(
            immediate_action=dict(
                actor=c["producer"] if c else "none",
                action="inspect assignment",
                expected_artifact=c["artifact"] if c else "none",
            ),
            subsequent_actions=["return artifact"],
            preconditions=["active session"],
        ),
        resource_plan=dict(
            team_token_limit=5000000,
            reserved_worker_actions=[x["member"] for x in ops if x["operation"] == "TURN"],
            coordination_cost=dict(
                estimated_input_tokens=200, estimated_output_tokens=100, reason="one handoff"
            ),
        ),
        reevaluation=dict(trigger="new public result", required_evidence=["receipt"]),
    )


def exercise(root, source=None):
    sys.path.insert(0, str(live.ROOT / "tests"))
    import test_role_baseline_world_v141 as fixture

    def local(args, **kwargs):
        cmd, kwargs["env"] = launch_spec(args[1:], inherited=kwargs["env"])
        return subprocess.run(cmd, **kwargs)

    prep = clone_function(
        fixture.prepare, {**fixture.prepare.__globals__, "subprocess": SimpleNamespace(run=local)}
    )
    os.environ.update(
        OH_PERSISTENCE_DIR=str(root / "sdk"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        HF_HUB_OFFLINE="1",
        OPENHANDS_SUPPRESS_BANNER="1",
    )
    prepared, *_ = prep(root / "fixture")
    M = live.M
    M.natural.attach(prepared, ["behavior", "regression"], condition="G")
    deadline = M.DispatchDeadline(soft_seconds=240, hard_seconds=300)
    prepared.source_provider.runner.hard_at = deadline.hard_at
    manifest = live.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    h = live.digest(manifest.read_bytes())
    counter = M.OfficialDeepSeekCounter(manifest, manifest_sha256=h)
    content, meta = M.load_official_content_counter(manifest, manifest_sha256=h)
    count = M.Backend(root / "count", None, "cpu", counter, None, set())
    plan = [
        ("begin_work", dict(task_id="work_root")),
        ("write_file", dict(path="sample.py", text="value = 2\n")),
        ("run_tests", {}),
        ("fix_patch", dict(task_ids=["work_root"], message="fixture patch")),
        ("handoff_patch", dict(patch_id="patch-1", to_member=POOL[0], message="adopt output")),
    ]
    seen = []
    calls = []
    adopted = []

    def worker(route, payload):
        if route.startswith("/tokenize"):
            return count.post(route, payload)
        m = payload["member_id"]
        calls.append(m)
        ident = f"sdk-{len(calls)}"
        tool, args = plan.pop(0) if m == POOL[2] and plan else ("read_file", dict(path="sample.py"))
        if m == POOL[0] and not plan and not adopted:
            tool, args = "integrate_patch", dict(patch_id="patch-1")
        return dict(
            id=ident,
            model="deepseek-flash",
            object="chat.completion",
            created=0,
            choices=[
                dict(
                    index=0,
                    finish_reason="tool_calls",
                    message=dict(
                        role="assistant",
                        content=None,
                        tool_calls=[
                            dict(
                                id=ident,
                                type="function",
                                function=dict(name=tool, arguments=json.dumps(args)),
                            )
                        ],
                    ),
                )
            ],
            usage=dict(
                prompt_tokens=256,
                completion_tokens=25,
                total_tokens=281,
                prompt_cache_hit_tokens=0,
                prompt_cache_miss_tokens=256,
            ),
        )

    from proworksim.software_organization_v232 import OrganizationExecution

    execution = OrganizationExecution(
        worker, root / "telemetry", "fixture", "cpu", content_counter=content
    )
    owner = M.native.build_team_owner(
        execution.post,
        organization_id="FREE2",
        slot_id="cpu",
        condition_id="control",
        folder=root / "ledger",
        deadline=deadline,
        identity=dict(policy_version="v247", model="scripted", thinking=False),
        observation_token_counter=content,
        observation_tokenizer_id=meta["tokenizer_id"],
    )
    w = install(prepared, owner)
    rt, *_ = M.native.build_runtime(
        owner,
        prepared,
        root / "runtime",
        public_initial_message="Public task: update sample.py and publish.",
        deadline=deadline,
    )
    M.native.set_native_limit(rt, 5000000)
    execution.runtime = rt
    execution.bind_recorder(rt)

    if source is not None:
        from proworksim import software_sdk_resume_v203_3_4 as resume

        w.bootstrap_three("fresh process restore")
        rt.sync_members()
        resume.restore_world(prepared, source)
        rt.sync_members()
        restored = resume.restore_runtime(prepared, rt, source)
        assert (
            len(rt.policies) == 3
            and w._software()["patches"]["patch-1"]["author"] == POOL[2]
            and not calls
        )
        result = dict(
            tokens=restored["prefix_tokens"],
            ids=[str(rt.policies[m].conversation.id) for m in POOL],
        )
        M.native.close_runtime(rt)
        return result

    def state(arm="O-DYNAMIC"):
        return public_state(w, rt, {"E1": {"work_package": "work_root"}}, arm)

    s = state()
    assert len(rt.policies) == 2
    fixed = state("O-FIXED")
    assert all(
        o["dimension"] != "D0" for c in fixed["candidates"].values() for o in c["operations"]
    )

    def rejected(fn):
        try:
            fn()
        except ValueError:
            return
        raise AssertionError("Expected refusal")

    def control(ops, p=POOL[0], q=POOL[1]):
        return candidate(ops, p, q, "public product")

    rejected(
        lambda: validate(
            w,
            rt,
            "O-FIXED",
            control([op("OWNER", member="member_004", task="work_root", role="implement")]),
        )
    )
    rejected(
        lambda: validate(
            w,
            rt,
            "O-FIXED",
            control([op("VERIFY", member=POOL[0], task="work_root", role="verify")]),
        )
    )
    low = SimpleNamespace(
        team_budget=SimpleNamespace(
            snapshot=lambda: dict(
                available_tokens=100, held_tokens=0, remaining_attempts=5, remaining_decisions=5
            )
        )
    )
    rejected(lambda: validate(w, low, "O-FIXED", control([op("TURN", member=POOL[0])])))
    keep = answer(s, "none", "KEEP")
    assert apply(w, rt, s, keep)["version_after"] == 0
    stale = deepcopy(s)
    stale["decision_key"] = "stale"
    stale["base_hash"] = "old"
    rejected(lambda: apply(w, rt, stale, answer(stale, "none", "KEEP")))
    # Exercise a native split and merge in a separate zero-provider control before the paid design.
    from proworksim.software_organization_patch_v247 import execute_operation

    with w.store.lock():
        w.state = w.store.load()
        kids = [dict(task_id=t, scope=[t], description=t) for t in ("behavior", "regression")]
        for operation in [
            op("SPLIT", member=POOL[0], task="work_root", children=kids),
            op("MERGE", member=POOL[0], task="work_root"),
        ]:
            validate(w, rt, "O-FIXED", control([operation]))
            execute_operation(w, operation, "local control")
        assert w.dynamic()["work"]["work_root"]["children"] == []
        w.store.save(w.state)
    s = public_state(w, rt, {"E2": {"control": "restored root scope"}}, "O-DYNAMIC")
    key = next(
        k
        for k, c in s["candidates"].items()
        if c["operations"][0]["operation"] == "JOIN" and c["operations"][1]["operation"] == "OWNER"
    )
    proposal = answer(s, key)
    rec = apply(w, rt, s, proposal)
    assert (
        rec["status"] == "CHANGE"
        and len(rt.policies) == 3
        and len({str(p.conversation.id) for p in rt.policies.values()}) == 3
    )
    assert apply(w, rt, s, proposal) == rec

    class Done(Exception):
        pass

    def observe(o):
        r = o.get("response") or {}
        tool = (o.get("decision") or {}).get("action")
        if tool:
            assert r.get("ok"), (tool, r.get("error"))
            seen.append([o["worker_id"], tool])
        if tool == "integrate_patch" and r.get("ok"):
            adopted.append(r["result"])
            raise Done

    try:
        result = M.native.run_fragment(prepared, rt, on_opportunity=observe)
        assert not plan, (
            result.get("execution_integrity_failure"),
            result.get("terminal_details"),
            result.get("termination_class"),
            calls,
            seen,
            result.get("outcomes", [])[-1:],
        )
    except Done:
        pass
    assert not plan
    assert (
        [POOL[2], "handoff_patch"] in seen
        and seen[-1] == [POOL[0], "integrate_patch"]
        and not adopted[0].get("conflicts")
    )
    from proworksim import software_sdk_resume_v203_3_4 as resume

    cp = root / "three-checkpoint"
    resume.save(prepared, rt, cp, control_state={"source": "scripted"})
    cmd, env = launch_spec([str(Path(__file__).resolve()), "--restore", str(cp)])
    proof = json.loads(subprocess.check_output(cmd, env=env, text=True).splitlines()[-1])
    assert proof["tokens"] == owner.adapter.ledger.actual and proof["ids"] == [
        str(rt.policies[m].conversation.id) for m in POOL
    ]

    s = state()
    key = next(
        k
        for k, c in s["candidates"].items()
        if any(o["operation"] == "RETIRE" and o["member"] == POOL[2] for o in c["operations"])
    )
    rec2 = apply(w, rt, s, answer(s, key))
    assert rec2["status"] == "CHANGE" and rt.stopped[POOL[2]] == "retired"
    assert all(rt.select_next()["member"] != POOL[2] for _ in range(4))
    assert (
        w._software()["patches"]["patch-1"]["author"] == POOL[2]
        and rt.team_budget.snapshot()["limits"]["max_total_tokens"] == 5000000
    )
    assert w._task("work_root")["owner"] == POOL[0]
    # Inject a failure after a real first operation and verify the graph is not reported
    # as wholly activated. A subsequent proposal must bind the observed new graph.
    from proworksim import software_organization_patch_v247 as patches
    from unittest.mock import patch

    st = public_state(w, rt, {"E3": {"test": "partial-control"}}, "O-FIXED")
    key = next(k for k, c in st["candidates"].items() if c["operations"][0]["operation"] == "ROLE")
    proposal = answer(st, key)
    real = patches.execute_operation

    def interrupted(world, x, reason):
        if x["operation"] == "LINK":
            raise ValueError("injected after first commit")
        return real(world, x, reason)

    with patch.object(patches, "execute_operation", interrupted):
        partial = apply(w, rt, st, proposal)
    assert partial["status"] == "partial" and len(partial["completed"]) == 1
    assert apply(w, rt, st, proposal) == partial
    fresh = public_state(w, rt, {"E3": {"test": "partial-control"}}, "O-FIXED")
    assert fresh["base_hash"] == partial["after"] and fresh["decision_key"] != st["decision_key"]
    apply(w, rt, fresh, answer(fresh, "none", "ABSTAIN"))
    assert rt.policies[POOL[2]].directory != rt.policies[POOL[0]].directory
    assert w._software()["registry"][POOL[2]]["private_history_copied"] is False
    M.native.close_runtime(rt)
    locked = M.native.lock_fixed_candidates(prepared, root / "closed", sdk_closed=True)
    assert live.read_json(Path(locked["path"]))["terminal_code"]
    return dict(
        versions=[rec["version_after"], rec2["version_after"]],
        third_steps=[t for m, t in seen if m == POOL[2]],
        actual_sdk_dispatches=len(calls),
        recipient_integrated=True,
        retirement_stops_dispatch=True,
        partial_committed_steps=1,
        candidate_export=True,
        restored_sdk_sessions=3,
        restore_calls=0,
        retained_patch_author=POOL[2],
        logical_tokens=owner.adapter.ledger.actual,
        paid_calls=0,
    )


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        print(
            json.dumps(
                exercise(Path(tmp), Path(sys.argv[2]) if sys.argv[1:2] == ["--restore"] else None)
            )
        )
