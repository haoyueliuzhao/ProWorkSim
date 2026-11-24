"""Restore a registered state and vary only the v230 context projection."""

import argparse
import json
import os
from pathlib import Path
import time
import traceback

from proworksim import software_natural_organization_runtime_v224_2 as native
from proworksim import software_natural_organization_world_v224_2 as natural
from proworksim import software_role_baseline_world_v141 as substrate
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.software_benchmark_candidates_v054 import checked
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_delegation_actor_v203_3_3_r2 import public_environment
from proworksim.software_graph_controller_v228 import ControlledWorld, menu
from proworksim.software_graph_execution_v230 import Execution
from proworksim.software_organization_actor_v223_1 import Actor
from proworksim.software_organization_api_v204 import Backend, DirectHTTPS
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.software_organization_runtime_v204 import after_opportunity, public_context
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.software_context_panel_v231 import PairedLedger, ROOT, DESIGN, RUN, panel_row


def save(path, obj):
    atomic_write(path, json_bytes(obj))


class PreparedFirstRequest(BaseException):
    """Stop only a rehearsal, immediately before the physical transport."""


def disabled(*args, **kwargs):
    raise RuntimeError("No external action in checkpoint rehearsal")


def episode(index, arm, out, rehearsal):
    design = read_json(DESIGN)
    state = design["states"][index]
    row = panel_row(state)
    source = ROOT / state["source_prefix"]
    archive = ROOT / state["graph_receipt"]
    original = read_json(archive)
    if digest(archive.read_bytes()) != state["graph_receipt_sha256"]:
        raise ValueError("Frozen decision receipt changed")
    branch = archive.parent if archive.name == "assigned-graph.json" else archive.parent.parent
    common = read_json(branch / "common-state.json")
    point = source / "checkpoint"
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        OH_PERSISTENCE_DIR=str(out / "sdk-settings"),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
        OPENHANDS_SUPPRESS_BANNER="1",
    )
    slot = f"v231:{state['case']}:{arm}"
    actor = rt = None
    meter = None
    admitted = False
    result = {
        "instance_id": row["instance_id"],
        "case": state["case"],
        "condition": arm,
        "slot": slot,
        "started": time.time(),
        "rehearsal": rehearsal,
        "status": "preparing",
    }
    try:
        resume.register_persistence_types()
        saved, proof = resume.read(point)
        node = common["node"]
        if not (
            common["checkpoint"] == proof["identity"] == state["checkpoint"]
            and proof["prefix_tokens"] == state["shared_prefix_usage"]
            and node["anomaly_id"] == saved["control_state"]["node"]["anomaly_id"]
            and common["graph"] == original["before"]
        ):
            raise ValueError("Checkpoint or work graph mismatch")
        observer = saved["control_state"].get("observer") or row["observer"]
        cfg = read_json(checked(row["configuration"]))
        deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        if rehearsal:
            _, public = public_environment(cfg)
            entry = {
                "version": "v064-repository-public-test-entry-r1",
                "instance_id": row["instance_id"],
                "argv": cfg["public_test_entry"]["argv"],
                "cwd": "/testbed",
                "timeout_seconds": 1800,
                "hidden_material_used": False,
            }
            manifest = source / "actor/source-manifest.json"
            callback = disabled
        else:
            meter = PairedLedger.load(RUN / "authority.json")
            meter.admit(slot, state["remaining_per_branch"])
            admitted = True
            actor = Actor(row, out / "actor", resume_test_calls=saved["public_test_calls"])
            actor.start()
            public, entry, manifest, callback = (
                actor.public,
                actor.entry,
                out / "actor/source-manifest.json",
                actor.test,
            )
        prepared = substrate.prepare_case(
            manifest,
            out / "prepared",
            organization_id="FREE2",
            public_test_callback=callback,
            deadline=deadline,
            public_test_entry=entry,
        )
        natural.attach(prepared, [r["id"] for r in row["requirements"]], condition="G")
        resume.restore_world(prepared, point)
        world = prepared.world
        world.__class__ = ControlledWorld
        tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        h = digest(tok.read_bytes())
        counter = OfficialDeepSeekCounter(tok, manifest_sha256=h)
        content, meta = load_official_content_counter(tok, manifest_sha256=h)
        if rehearsal:
            counting_backend = Backend(out / "count-only", None, slot, counter, None, ())

            def post(route, payload):
                if route.startswith("/tokenize"):
                    return counting_backend.post(route, payload)
                if route != "/chat/completions":
                    raise ValueError("Unexpected counting route")
                result["first_request"] = {
                    "member": payload["member_id"],
                    "usage_id": payload["usage_id"],
                    "prompt_tokens": counter.measure(payload["wire"])["prompt_tokens"],
                    "max_output": payload["wire"]["max_tokens"],
                }
                raise PreparedFirstRequest

        else:
            transport = DirectHTTPS(load_api_key(ROOT / ".env"), timeout_seconds=1800)
            names = {
                tool["function"]["name"]
                for m in ("member_001", "member_002")
                for tool in native.member_wire_tools("FREE2", m)
            }
            backend = Backend(out / "api", meter, slot, counter, transport, names)

            def post(route, payload):
                if route == "/chat/completions" and world.protocol()["terminal"]:
                    raise ValueError("Closed before dispatch")
                return backend.post(route, payload)

        execution = Execution(post, out / "telemetry", row["instance_id"], slot, arm)
        owner = native.build_team_owner(
            execution.post,
            organization_id="FREE2",
            slot_id=slot,
            condition_id="v231-" + arm,
            folder=out / "model-ledger",
            deadline=deadline,
            identity={
                "policy_version": native.VERSION,
                "model": "deepseek-flash",
                "thinking": False,
            },
            observation_token_counter=content,
            observation_tokenizer_id=meta["tokenizer_id"],
            require_content_counter=True,
        )
        initial = (
            native.CONTRACT
            + "\n"
            + cfg["public_task"]["problem_statement"]
            + "\n"
            + public_context(cfg, public)
        )
        rt, _, _ = native.build_runtime(
            owner, prepared, out / "runtime", deadline=deadline, public_initial_message=initial
        )
        restored = resume.restore_runtime(prepared, rt, point)
        save(out / "restore.json", restored)
        frozen = menu(world, node, observer)
        rt.policies[observer].conversation.send_message(
            "Work observation: "
            + json.dumps(
                {
                    "kind": node["anomaly_type"],
                    "subject": node.get("subject"),
                    "scopes": node["affected_work"],
                    "evidence": frozen["evidence"],
                }
            )
        )
        native.enter_continuation(rt)
        native.set_native_limit(
            rt, design["logical_team_tokens"] - state["shared_controller_usage"]
        )
        execution.attach(rt)
        if actor:
            actor.bind_deadline(rt.deadline)
        balance = rt.team_budget.snapshot()["available_tokens"]
        if balance != state["remaining_per_branch"]:
            raise ValueError(f"Unexpected restored balance {balance}")
        active = execution.activate(node, observer, frozen, original["decision"])
        if (
            active.get("after") != original["after"]
            or active["evidence_refs"] != original["evidence_refs"]
        ):
            raise ValueError("Organization or decision evidence mismatch")
        save(out / "assigned-graph.json", active)
        result.update(
            checkpoint=proof["identity"],
            available_at_start=balance,
            option=original["decision"]["option"],
            graph_sha256=digest(json_bytes(active["after"])),
        )
        if rehearsal:
            try:
                native.run_fragment(prepared, rt)
            except PreparedFirstRequest:
                result.update(
                    status="restore_verified",
                    first_member=result["first_request"]["member"],
                    provider_calls=0,
                )
                return
            raise ValueError("Rehearsal closed before the first real dispatch boundary")
        result["status"] = "running"
        save(out / "result.json", result)

        def progress(outcome):
            after_opportunity(actor, out / "transport-fault.json")
            save(
                out / "progress.json",
                {
                    "opportunity": rt.opportunities,
                    "worker": outcome.get("worker_id"),
                    "status": outcome["status"],
                    "new_tokens": owner.adapter.ledger.actual - proof["prefix_tokens"],
                    "time": time.time(),
                },
            )

        boundary = native.run_fragment(prepared, rt, on_opportunity=progress)
        save(out / "boundary.json", boundary)
        if boundary["execution_integrity_failure"]:
            raise RuntimeError(str(boundary["execution_integrity_failure"]))
        native.close_runtime(rt)
        rt = None
        save(
            out / "candidate-lock.json",
            native.lock_fixed_candidates(prepared, out / "closure", sdk_closed=True),
        )
        result.update(
            status="closed",
            termination=boundary["termination_class"],
            logical_tokens=owner.adapter.ledger.actual + state["shared_controller_usage"],
            observer_errors=execution.trace.errors,
        )
    except Exception as exc:
        result.update(status="technical_unknown", error=str(exc), traceback=traceback.format_exc())
    finally:
        for fn in (
            ([lambda: native.close_runtime(rt)] if rt else [])
            + ([actor.close] if actor else [])
            + ([lambda: meter.close(slot)] if admitted else [])
        ):
            try:
                fn()
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(str(exc))
        result["finished"] = time.time()
        save(out / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, choices=range(3), required=True)
    parser.add_argument("--arm", choices=("T0", "T1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rehearsal", action="store_true")
    args = parser.parse_args()
    expected = RUN / read_json(DESIGN)["states"][args.index]["case"] / args.arm
    if not args.rehearsal and args.output.resolve() != expected:
        parser.error("Different physical branch identity")
    episode(args.index, args.arm, args.output, args.rehearsal)
