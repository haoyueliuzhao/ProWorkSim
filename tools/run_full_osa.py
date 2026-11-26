"""Current full-task OSA entry. Frozen v245 runners remain available for historical replay."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa_v245_4 as baseline
from run_full_osa_v245_3 import (
    M,
    LIMIT,
    NOTICE,
    PROJECT,
    PairedLedger,
    build as historical_build,
    checked,
    digest,
    json_bytes,
    menu,
    orders,
    read_json,
    reference,
    save,
)
from proworksim import software_event_orders_v243 as event
from proworksim.software_failure_graph_v246 import FailureProjectGraph, identity
from proworksim.software_fixed_organization_clone_v131 import clone_function

ROOT = baseline.previous.ROOT


def build(row):
    project, nodes, routes = historical_build(row)
    if "incident" not in row:
        return project, nodes, routes
    # Tests establish the failure. A simultaneous public checklist establishes the
    # separate completion and verification obligations to which a graph patch binds.
    package = row["incident"]["package"]
    checklist = {
        **row,
        "evidence": {"E0": row["evidence"]["E0"]},
        "probe_id": package + "/independent_review",
    }
    _, checklist_nodes, _ = historical_build(checklist)
    checklist["probe_id"] = next(iter(checklist_nodes))
    visible = json.loads(baseline.wire(checklist, {})["messages"][-1]["content"])
    for key, node in visible["obligation_graph"].items():
        if key not in nodes:
            nodes[key] = node
    project["test_failure_incident"] = row["incident"]
    return project, nodes, routes


incident_contract = SimpleNamespace(
    **{
        name: clone_function(fn, {**fn.__globals__, "build": build})
        for name, fn in (
            ("compile_decision", event.contract.compile_decision),
            ("dispatch", event.contract.dispatch),
        )
    }
)


def wire(row, choices):
    request = baseline.wire(row, choices)
    if "incident" in row:
        data = json.loads(request["messages"][-1]["content"])
        project, nodes, _ = build(row)
        data.update(project_graph=project, obligation_graph=nodes)
        data["organization_graph"]["constraints"]["review_by_package"] = {
            p["task_id"]: ("required" if p["independent_review_required"] else "optional")
            for p in row["evidence"]["E0"]["packages"]
            if "independent_review_required" in p
        }
        fields = request["tools"][0]["function"]["parameters"]["properties"]
        pending = [k for k, n in nodes.items() if n["completion"] in {"UNSATISFIED", "STALE"}]
        fields["current_obligations"] = (
            {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": pending}}
            if pending
            else {"type": "array", "maxItems": 0}
        )
        request["messages"][-1]["content"] = json.dumps(
            data, ensure_ascii=False, separators=(",", ":")
        )
        request["messages"][0]["content"] += (
            " This decision was triggered by the incident in the project graph. Compare continued repair by the owner"
            " with a concrete change of role or responsibility. Cite the failed public runs and name the next"
            " evidence that would resolve the incident. The affected package is the work context, not a proven cause."
            " A mixed-target streak signals stalled testing and does not establish a single recurring defect."
            " For collection or selection failures, diagnose the test entry before assigning a code fault."
        )
    return request


class Execution(baseline.Execution):
    decide = clone_function(
        event.Execution.decide,
        {**event.Execution.decide.__globals__, "wire": wire, "contract": incident_contract},
    )

    def __init__(self, *args, controller_backend, **kwargs):
        def post(route, payload):
            return controller_backend(
                route, {**payload, "request_id": payload["request_id"] + ":" + self.record["id"]}
            )

        super().__init__(*args, controller_backend=post, **kwargs)

    def attach(self, runtime):
        super().attach(runtime)
        ordinary = self.normal_select
        self.drain_for_incident = False

        def select_ordinary():
            # The existing grant scheduler offers ordinary work first while tokens
            # are plentiful. With a new pending incident, serve the promised turns
            # before reevaluating so the old plan cannot defer OSA until budget end.
            if (
                self.drain_for_incident
                and self.grants
                and self.grants[0][0]
                in {
                    "publish_artifact",
                    "inspect_handoff",
                    "record_disposition",
                    "implementation",
                    "verification",
                    "fix_current_tree",
                    "delivery",
                }
            ):
                return None
            return ordinary()

        self.normal_select = select_ordinary


def failure_decision(ex, rt, task, dest, counter, graph, incident):
    actor, package = incident["actor"], incident["package"]
    world = rt.prepared.world
    work = world.dynamic()["work"]
    if package not in work or work[package]["children"] or world._completion_current(package):
        return None
    commands = graph.decision_evidence(incident)
    related = [
        n
        for n in graph.nodes.values()
        if n["state"] == "needs_decision"
        and n["scope"] == incident["scope"]
        and graph.decision_evidence(n) == commands
    ]
    refs = [graph.reports[c] for c in commands]
    rid = identity([ex.trace.branch, incident["id"], commands])
    view = world._action_delivery_readiness(actor, PROJECT)
    readiness = baseline.evidence(
        dict(
            decision=dict(action="delivery_readiness", arguments={}),
            response=dict(ok=True, result=view),
        )
    )
    readiness["packages"] = [p for p in readiness["packages"] if p["task_id"] == package]
    checklist_id = identity([rid, rt.opportunities, readiness])
    checklist_ref = dict(
        command_id=checklist_id,
        actor_id=actor,
        tool="delivery_readiness",
        opportunity=rt.opportunities,
    )
    node = dict(
        anomaly_id=incident["id"],
        anomaly_type="A1",
        subject=incident["target"],
        affected_work=[package],
        evidence_refs=[checklist_ref, *refs],
    )
    frozen = menu(world, node, actor)
    facts = {"E0": readiness}
    for i, r in enumerate(refs, 1):
        named = [n["target"] for n in related if n["target_kind"] in {"test", "test_function"}]
        facts[f"E{i}"] = dict(
            operation=r["tool"],
            accepted=True,
            executed=True,
            passed=False,
            failed_cases=named
            or [t for kind, t in r["targets"] if kind in {"test", "test_function"}],
            reference=r["source_reference"],
            report_id=r["report_id"],
            selection=r["selection"],
            counts=r["counts"],
        )
    summary = dict(
        id=incident["id"],
        actor=actor,
        package=package,
        target=incident["target"],
        target_kind=incident["target_kind"],
        state=incident["state"],
        revision=graph.revision,
        failures_observed=len(incident["failures"]),
        evidence=[e for e in facts if e != "E0"],
        related_targets=[
            dict(id=n["id"], kind=n["target_kind"], target=n["target"]) for n in related
        ],
        previous_decision=incident["decisions"][-1] if incident["decisions"] else None,
    )
    row = dict(
        instance=task["instance_id"],
        id=rid,
        reference_type="A1",
        observer=actor,
        graph=frozen["graph"],
        options=frozen["options"],
        targets=[package],
        work_status={package: dict(completed=False, authors=work[package]["authors"])},
        evidence=facts,
        provenance=dict(commands=[checklist_id, *commands], origin="current_episode_test_receipts"),
        available_tokens=rt.team_budget.snapshot()["available_tokens"],
        incident=summary,
    )
    _, nodes, routes = build(row)
    if not routes:
        return None
    row["probe_id"] = next((k for k in nodes if k.endswith("/diagnose_failure")), next(iter(nodes)))
    request = wire(row, orders(row))
    if counter.measure(request)["prompt_tokens"] + request["max_tokens"] > min(
        8192, row["available_tokens"]
    ):
        return None
    ex.record = row
    save(
        dest / "decision-input.json",
        dict(
            row=row,
            routes=json.loads(request["messages"][-1]["content"])["routes"],
            opportunity=rt.opportunities,
        ),
    )
    active, info = ex.decide(node, actor, frozen, "OSA")
    save(dest / "decision.json", dict(active=active, info=info, opportunity=rt.opportunities))
    graph.decided(
        related,
        dict(
            id=rid,
            opportunity=rt.opportunities,
            prior_graph_version=frozen["base_version"],
            graph_version=active["version"],
            first_action=info["first_action"],
            changed=active["changed"],
            option=active["decision"]["option"],
            validator=info["validator"],
        ),
    )
    return info["osa_tokens"]


class Policy:
    def __init__(self, execution, runtime, task, out, counter):
        self.ex, self.rt, self.task, self.out, self.counter = execution, runtime, task, out, counter
        self.graph = FailureProjectGraph()
        self.calls = self.tokens = 0
        self.initial_done = False

    def observe(self, outcome):
        world = self.rt.prepared.world
        step = self.rt.opportunities
        state = world.dynamic()
        actor = outcome.get("worker_id")
        pkg = state["active_work"].get(actor)
        if not pkg:
            leaves = [k for k, v in state["work"].items() if not v["children"]]
            pkg = leaves[0] if len(leaves) == 1 else None
        updated = self.graph.observe(step, outcome, pkg)
        if updated:
            save(self.out / "project-graph.json", self.graph.snapshot())
        budget = self.rt.team_budget.snapshot()
        pending = [
            n for n in self.graph.nodes.values() if n["state"] == "needs_decision" and n["package"]
        ]
        self.ex.drain_for_incident = bool(pending)
        if (
            world.protocol()["terminal"]
            or self.ex.grants
            or self.ex.sender_credit
            or self.ex.follow_credit
            or budget["held_tokens"]
        ):
            return
        dest = self.out / "osa-decisions" / f"{step:06d}"
        for n in pending:
            cost = failure_decision(self.ex, self.rt, self.task, dest, self.counter, self.graph, n)
            if cost is not None:
                save(self.out / "project-graph.json", self.graph.snapshot())
                break
        else:
            if self.initial_done or step < 12:
                return
            cost = baseline.decision(self.ex, self.rt, self.task, dest, self.counter)
        if cost is not None:
            self.tokens += cost
            self.calls += 1
            self.initial_done = True
            self.ex.drain_for_incident = any(
                n["package"] and n["state"] == "needs_decision" for n in self.graph.nodes.values()
            )


def generate(task, out, *, ledger_path, namespace):
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    meter = PairedLedger.load(ledger_path)
    slot = f"{namespace}:{task['index']}:OSA"
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
        policy = Policy(ex, rt, task, out, counter)

        def observe(o):
            M.after_opportunity(actor, out / "transport-fault.json")
            policy.observe(o)
            save(
                out / "progress.json",
                dict(
                    opportunity=rt.opportunities,
                    worker_tokens=owner.adapter.ledger.actual,
                    osa_tokens=policy.tokens,
                    osa_calls=policy.calls,
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
            osa_tokens=policy.tokens,
            osa_calls=policy.calls,
            osa_called=bool(policy.calls),
            termination=boundary["termination_class"],
            logical_tokens=owner.adapter.ledger.actual + policy.tokens,
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    bank = read_json(baseline.previous.BANK)["rows"]
    task = next((r for r in bank if r["index"] == args.index), None)
    if task is None:
        parser.error(f"Task index {args.index} is absent from the bank")
    generate(task, args.output, ledger_path=args.ledger, namespace=args.namespace)
