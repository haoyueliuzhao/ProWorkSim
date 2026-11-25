"""Run a D4 order on a real two-member SDK with scripted responses and a published upstream patch."""

from pathlib import Path
from types import SimpleNamespace
import os
import sys
import subprocess
import json
import itertools
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as job
from proworksim.harness_port import HarnessPort
from proworksim.software_graph_controller_v228 import menu
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_event_orders_v243 import orders
from proworksim.software_review_handoff_v243_1 import Execution
from proworksim.software_dependency_chain_v243_2 import dependency_chain
from proworksim.software_fixed_organization_clone_v131 import clone_function
from prepare_osa_states_v236 import evidence
from run_offline_scorer_v096 import launch_spec


class Finished(Exception):
    pass


def main():
    sys.path.insert(0, str(job.ROOT / "tests"))
    import test_role_baseline_world_v141 as fixture
    from test_organization_world_v211 import split, ok
    from test_organization_world_v212 import setup

    m1, m2 = fixture.M1, fixture.M2
    M = job.M

    def local(args, **kwargs):
        command, kwargs["env"] = launch_spec(args[1:], inherited=kwargs["env"])
        return subprocess.run(command, **kwargs)

    prep = clone_function(
        fixture.prepare, {**fixture.prepare.__globals__, "subprocess": SimpleNamespace(run=local)}
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.environ.update(
            OH_PERSISTENCE_DIR=str(root / "sdk"),
            LITELLM_LOCAL_MODEL_COST_MAP="True",
            HF_HUB_OFFLINE="1",
            OPENHANDS_SUPPRESS_BANNER="1",
        )
        prepared, _, _, _ = prep(root / "fixture")
        M.natural.attach(prepared, ["behavior", "regression"], condition="G")
        w = prepared.world
        ports = {
            m: HarnessPort(
                M.natural.SoftwareCollaborationPort(w.session(m, M.natural.PROJECT), m),
                m,
                project_id=M.natural.PROJECT,
                public_sink=lambda *_: None,
                world_sink=lambda *_: None,
                harness_sink=lambda *_: None,
            )
            for m in (m1, m2)
        }
        for port in ports.values():
            port.tools()
        seq = itertools.count()

        def call(m, t, **a):
            return ports[m].call(t, request_key=f"d4-control-{next(seq)}", association={}, **a)

        split(call)
        setup(call, "behavior")
        offer = ok(
            call,
            m1,
            "assign_work",
            task_id="regression",
            to_member=m2,
            reason="Perform downstream validation",
        )
        ok(call, m2, "accept_transfer", offer_id=offer["offer_id"])
        setup(call, "regression", m2, m1)
        ok(
            call,
            m2,
            "change_dependency",
            task_id="regression",
            operation="add",
            depends_on="behavior",
            reason="Use the implemented behavior",
        )
        ok(call, m1, "begin_work", task_id="behavior")
        ok(call, m1, "write_file", path="sample.py", text="value = 2\n")
        ok(call, m1, "run_tests")
        patch = ok(
            call, m1, "fix_patch", task_ids=["behavior"], message="Publish current implementation"
        )["patch_id"]
        ok(call, m1, "complete_work", task_id="behavior", patch_id=patch)
        response = call(m2, "work_readiness", task_id="regression")
        witness = dict(
            worker_id=m2,
            decision=dict(action="work_readiness", arguments=dict(task_id="regression")),
            response=response,
        )
        g = AnomalyGraph(m2)
        g.observe(0, witness)
        (node,) = [n for n in g.nodes.values() if n["anomaly_type"] == "A2"]
        frozen = menu(w, node, m2)
        row = dict(
            graph=frozen["graph"], targets=["regression"], evidence={"E1": evidence(witness)}
        )
        key, order = next(iter(orders(row).items()))
        assert order["artifact"] == patch and order["state"] == "published_not_adopted"
        tok = job.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        sha = M.digest(tok.read_bytes())
        counter = M.OfficialDeepSeekCounter(tok, manifest_sha256=sha)
        content, meta = M.load_official_content_counter(tok, manifest_sha256=sha)
        count = M.Backend(root / "count", None, "cpu", counter, None, set())
        receipts = []
        sent = None
        read = False
        adopted = False
        ready = False
        dispatched = []

        def policy(route, payload):
            if route.startswith("/tokenize"):
                return count.post(route, payload)
            assert route == "/chat/completions" and len(dispatched) < 20
            m = payload["member_id"]
            tool, args = "dynamic_status", {}
            if m == m1 and sent is None:
                tool, args = (
                    "handoff_patch",
                    dict(patch_id=patch, to_member=m2, message="Current upstream implementation"),
                )
            elif m == m2 and sent is not None:
                if not read:
                    tool, args = "read_work_event", dict(sequence=sent)
                elif not adopted:
                    tool, args = "integrate_patch", dict(patch_id=patch)
                elif not ready:
                    tool, args = "work_readiness", dict(task_id="regression")
                else:
                    tool, args = "begin_work", dict(task_id="regression")
            dispatched.append(m)
            i = str(len(dispatched))
            msg = dict(
                role="assistant",
                content=None,
                tool_calls=[
                    dict(
                        id="d4-" + i,
                        type="function",
                        function=dict(name=tool, arguments=json.dumps(args)),
                    )
                ],
            )
            return dict(
                id="cpu-" + i,
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

        w.__class__ = M.ControlledWorld
        ex = Execution(policy, root / "telemetry", "fixture", "d4-script", content_counter=content)
        ex.record = row
        deadline = M.DispatchDeadline(soft_seconds=180, hard_seconds=240)
        prepared.source_provider.runner.hard_at = deadline.hard_at
        owner = M.native.build_team_owner(
            ex.post,
            organization_id="FREE2",
            slot_id="d4-script",
            condition_id="control",
            folder=root / "ledger",
            deadline=deadline,
            identity=dict(policy_version=M.native.VERSION, model="scripted", thinking=False),
            observation_token_counter=content,
            observation_tokenizer_id=meta["tokenizer_id"],
            require_content_counter=True,
        )
        rt, _, _ = M.native.build_runtime(
            owner,
            prepared,
            root / "runtime",
            deadline=deadline,
            public_initial_message=M.native.CONTRACT,
        )
        try:
            M.native.set_native_limit(rt, 5000000)
            ex.attach(rt)
            active = ex.apply_order(
                node,
                m2,
                frozen,
                dict(
                    option="K",
                    evidence=["E1"],
                    reason="Test addressed release of an already published version",
                ),
                key,
                order,
            )

            def observe(o):
                nonlocal sent, read, adopted, ready
                receipts.append(o)
                r = o.get("response") or {}
                t = (o.get("decision") or {}).get("action")
                if t and not r.get("ok"):
                    raise ValueError(str(r.get("error")))
                v = r.get("result") or {}
                if t == "handoff_patch":
                    sent = v["handoff_sequence"]
                if t == "read_work_event":
                    read = v["sequence"] == sent and v["patch_id"] == patch
                if t == "integrate_patch":
                    adopted = v["patch_id"] == patch and v["conflicts"] == []
                if t == "work_readiness":
                    ready = v["ready"] and not v["gaps"]
                if t == "begin_work":
                    raise Finished()

            try:
                M.native.run_fragment(prepared, rt, on_opportunity=observe)
            except Finished:
                pass
            chain = dependency_chain(
                [witness, *receipts],
                boundary=0,
                start=0,
                upstream="behavior",
                downstream="regression",
                producer=m1,
                consumer=m2,
                known_artifact=patch,
            )
            assert active["changed"] and dispatched[0] == m1 and sent and read and adopted and ready
            assert [x["kind"] for x in chain["events"]] == [
                "blocked",
                "addressed_handoff",
                "read_handoff",
                "adopted",
                "downstream_ready",
                "downstream_began",
            ]
            job.save(
                job.PLAN / "d4-control.json",
                dict(
                    sdk=True,
                    scripted=True,
                    provider_calls=0,
                    official_scores=0,
                    starting_artifact=patch,
                    order=order,
                    changed_dimensions=["D4", "D7"],
                    first_actor=dispatched[0],
                    scripted_sdk_calls=len(dispatched),
                    chain=chain,
                ),
            )
        finally:
            M.native.close_runtime(rt)


if __name__ == "__main__":
    main()
