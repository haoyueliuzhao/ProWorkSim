"""Historical request-boundary replay and offline SDK graph-activation control."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa as live
from run_offline_scorer_v096 import launch_spec
from proworksim.software_failure_graph_v246 import FailureProjectGraph
from proworksim.software_fixed_organization_clone_v131 import clone_function


def replay(episode):
    graph = FailureProjectGraph()
    triggers = []
    for i, o in enumerate(live.read_json(episode / "boundary.json")["outcomes"], 1):
        graph.observe(i, o, "work_root")
        for n in graph.nodes.values():
            if n["state"] == "needs_decision":
                triggers.append((i, n["target_kind"], n["target"]))
                graph.decided([n], {"opportunity": i, "simulated": True})
    return triggers


def receipt_controls(episode):
    rows = live.read_json(episode / "boundary.json")["outcomes"]
    failed = next(
        o
        for o in rows
        if o.get("decision", {}).get("action") == "run_tests"
        and o["response"]["result"].get("passed") is False
    )
    graph = FailureProjectGraph()

    def submit(i, actor="member_001", package="root", ok=False, replayed=False):
        o = deepcopy(failed)
        o["worker_id"] = actor
        r = o["response"]
        r["command_id"] = str(i)
        r["result"]["report_event"]["operation_id"] = "1" if replayed else str(i)
        if ok:
            r["result"].update(
                passed=True, counts={"passed": 1, "tests_run": 1}, diagnostic_summary={}
            )
        return graph.observe(i, o, package)

    assert submit(1) and not submit(1) and not submit(2, replayed=True)
    assert submit(3, actor="member_002") and submit(4, package="other") and submit(5)
    assert all(n["state"] == "observed" for n in graph.nodes.values())
    assert submit(6)
    due = [n for n in graph.nodes.values() if n["state"] == "needs_decision"]
    assert due and all(n["actor"] == "member_001" and n["package"] == "root" for n in due)
    graph.decided(due, {"scripted": True})
    for i in (7, 8, 9):
        submit(i)
    assert all(n["state"] != "needs_decision" for n in graph.nodes.values())
    assert submit(10, ok=True)
    assert all(n["state"] == "cleared" for n in due)
    assert submit(11)
    assert all(n["state"] == "observed" for n in due)
    mixed = FailureProjectGraph()
    for i in range(3):
        o = deepcopy(failed)
        r = o["response"]
        r["command_id"] = r["result"]["report_event"]["operation_id"] = str(i)
        r["result"]["diagnostic_summary"]["failed_tests"] = [
            dict(nodeid=f"test_{i}", phase="call", outcome="failed")
        ]
        mixed.observe(i, o, "root")
    (incident,) = [n for n in mixed.nodes.values() if n["state"] == "needs_decision"]
    assert incident["target_kind"] == "mixed_targets" and mixed.decision_evidence(incident) == [
        "0",
        "1",
        "2",
    ]


def sdk(root, episode):
    sys.path.insert(0, str(live.ROOT / "tests"))
    import test_role_baseline_world_v141 as fixture

    def local(args, **kwargs):
        command, kwargs["env"] = launch_spec(args[1:], inherited=kwargs["env"])
        return subprocess.run(command, **kwargs)

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
    prepared.world.__class__ = M.ControlledWorld
    calls = []

    def provider(route, payload):
        if route.startswith("/tokenize"):
            return dict(prompt_tokens=1000)
        data = json.loads(payload["wire"]["messages"][-1]["content"])
        incident = data["project_graph"].get("test_failure_incident")
        if calls:
            assert incident and len(incident["evidence"]) >= 2
            assert all(
                not data["project_graph"]["facts"][e]["receipt"]["passed"]
                for e in incident["evidence"]
            )
        target = ("none", "owned_patch", "independent_diagnosis")[len(calls)]
        choice = next(k for k, v in data["routes"].items() if v["added_product"] == target)
        probe = data["obligation_graph"][data["probed_obligation"]]
        proposal = dict(
            route=choice,
            work_order="none",
            reason="distinct test evidence",
            basis=list(data["project_graph"]["facts"]),
            reconsider_after="next public test",
            current_obligations=[],
            anomaly="A1" if incident else "UNKNOWN",
            probe_completion=probe["completion"],
            probe_readiness=probe["readiness"],
        )
        calls.append(payload["request_id"])
        return dict(
            id=f"local-{len(calls)}",
            usage=dict(total_tokens=128),
            choices=[
                dict(
                    message=dict(
                        tool_calls=[
                            dict(
                                function=dict(
                                    name="activate_organization", arguments=json.dumps(proposal)
                                )
                            )
                        ]
                    )
                )
            ],
        )

    manifest = live.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    sha = live.digest(manifest.read_bytes())
    counter = M.OfficialDeepSeekCounter(manifest, manifest_sha256=sha)
    content, meta = M.load_official_content_counter(manifest, manifest_sha256=sha)
    count = M.Backend(root / "count", None, "cpu", counter, None, set())
    workers = []

    def worker(route, payload):
        if route.startswith("/tokenize"):
            return count.post(route, payload)
        workers.append(payload["member_id"])
        assert len(workers) < 16
        ident = f"worker-{len(workers)}"
        msg = dict(
            role="assistant",
            content=None,
            tool_calls=[
                dict(
                    id=ident,
                    type="function",
                    function=dict(name="read_file", arguments=json.dumps({"path": "sample.py"})),
                )
            ],
        )
        return dict(
            id=ident,
            model="deepseek-flash",
            object="chat.completion",
            created=0,
            choices=[dict(index=0, finish_reason="tool_calls", message=msg)],
            usage=dict(
                prompt_tokens=256,
                completion_tokens=25,
                total_tokens=281,
                prompt_cache_hit_tokens=0,
                prompt_cache_miss_tokens=256,
            ),
        )

    ex = live.Execution(
        worker,
        root / "telemetry",
        "fixture",
        "cpu",
        content_counter=content,
        controller_backend=provider,
    )
    deadline = M.DispatchDeadline(soft_seconds=180, hard_seconds=240)
    prepared.source_provider.runner.hard_at = deadline.hard_at
    owner = M.native.build_team_owner(
        ex.post,
        organization_id="FREE2",
        slot_id="cpu",
        condition_id="control",
        folder=root / "ledger",
        deadline=deadline,
        identity=dict(policy_version=M.native.VERSION, model="scripted", thinking=False),
        observation_token_counter=content,
        observation_tokenizer_id=meta["tokenizer_id"],
        require_content_counter=True,
    )
    rt, *_ = M.native.build_runtime(
        owner,
        prepared,
        root / "runtime",
        public_initial_message=M.native.CONTRACT,
        deadline=deadline,
    )
    M.native.set_native_limit(rt, 5_000_000)
    ex.attach(rt)
    policy = live.Policy(
        ex,
        rt,
        dict(instance_id="fixture"),
        root,
        counter,
    )
    rt.opportunities = 12
    policy.observe({})
    traces = live.read_json(episode / "boundary.json")["outcomes"]
    for i, o in enumerate(traces, 1):
        if i <= 12:
            continue
        rt.opportunities += 1
        policy.observe(o)
        if len(calls) == 2 and ex.grants and ex.drain_for_incident:

            class GrantsServed(Exception):
                pass

            def settled(outcome):
                policy.observe(outcome)
                if len(calls) == 3:
                    raise GrantsServed

            try:
                M.native.run_fragment(prepared, rt, on_opportunity=settled)
            except GrantsServed:
                pass
        if len(calls) == 3:
            break
    records = prepared.world.protocol()["graph_control"]["versions"]
    assert [r["changed"] for r in records] == [False, True, True], [
        (r["decision"], r["changed"]) for r in records
    ] + [
        (live.read_json(p)["info"].get("error"), p.parent.name)
        for p in (root / "osa-decisions").glob("*/decision.json")
    ]
    assert len(set(calls)) == 3 and policy.tokens == 384 and ex.native_limit <= 5_000_000 - 384
    assert (
        "member_002" in workers
        and records[1]["after"]["work"]["work_root"]["owner"] == "member_002"
    )
    assert ex.grants[0] == ("new_duty", "member_001")
    assert records[-1]["after"]["duties"]["work_root"]["owner"] == "member_001"
    assert len(list((root / "osa-decisions").glob("*/decision.json"))) == 3
    M.native.close_runtime(rt)
    return [r["version"] for r in records]


if __name__ == "__main__":
    base = live.ROOT / "runs/software-benchmark-v245-4/full-osa12-r1"
    traces = {p.parent.name: replay(p) for p in sorted(base.glob("*/OSA"))}
    for i in ("3", "7"):
        assert traces[i]
    receipt_controls(base / "7/OSA")
    with TemporaryDirectory() as tmp:
        versions = sdk(Path(tmp), base / "3/OSA")
    print(json.dumps(dict(versions=versions, triggers=traces), ensure_ascii=False))
