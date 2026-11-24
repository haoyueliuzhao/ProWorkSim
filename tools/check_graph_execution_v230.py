"""Run the actual managed two-worker OpenHands loop with deterministic local responses."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from proworksim import software_natural_organization_runtime_v224_2 as native
from proworksim import software_natural_organization_world_v224_2 as natural
from proworksim.software_graph_controller_v228 import menu, ControlledWorld
from proworksim.software_graph_execution_v230 import Execution, CALL_BOUND
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest, json_bytes, atomic_write

ROOT = Path(__file__).resolve().parents[1]


class Finished(Exception):
    pass


def exercise(out, condition):
    sys.path.insert(0, str(ROOT / "tests"))
    import test_role_baseline_world_v141 as fixture

    def clean_run(argv, **kwargs):
        kwargs["env"] = {
            k: v
            for k, v in kwargs.get("env", os.environ).items()
            if k not in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "LD_PRELOAD")
        }
        return subprocess.run(argv, **kwargs)

    setup = clone_function(
        fixture.prepare,
        {
            **fixture.prepare.__globals__,
            "sys": SimpleNamespace(executable=str(ROOT / ".venv/bin/python")),
            "subprocess": SimpleNamespace(run=clean_run),
        },
    )
    prepared, _, _, _ = setup(out / "fixture")
    deadline = DispatchDeadline(soft_seconds=180, hard_seconds=240)
    prepared.source_provider.runner.hard_at = deadline.hard_at
    natural.attach(prepared, ["behavior", "regression"], condition="G")
    world = prepared.world
    world.__class__ = ControlledWorld
    slot = "v230:cpu:" + condition
    requests = []

    def scripted(route, payload):
        if route.startswith("/tokenize"):
            return dict(
                prompt_tokens=1000,
                request_sha256=digest(json_bytes(payload["wire"])),
                method="scripted fixture",
                count_only_not_dispatchable=route.endswith("prefix"),
            )
        assert route == "/chat/completions" and len(requests) < 12
        actor = payload["member_id"]
        requests.append(actor)
        tool, args = (
            ("staff_wait", {"reason": "Waiting for a new duty"})
            if actor == "member_002" and requests.count(actor) == 1
            else ("read_file", {"path": "sample.py"})
        )
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "cpu-call-" + str(len(requests)),
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps(args)},
                }
            ],
        }
        return {
            "id": "cpu-response-" + str(len(requests)),
            "model": "deepseek-flash",
            "object": "chat.completion",
            "created": 0,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": msg}],
            "usage": {
                "prompt_tokens": 256,
                "completion_tokens": 25,
                "total_tokens": 281,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 256,
            },
        }

    def controller(route, payload):
        if route.startswith("/tokenize"):
            return scripted(route, payload)
        view = json.loads(payload["wire"]["messages"][1]["content"])
        assert (
            len(payload["wire"]["messages"]) == 2
            and payload["wire"]["tools"][0]["function"]["name"] == "activate_organization"
        )
        key = next(k for k, v in view["options"].items() if v["op"] == "diagnosis")
        choice = {
            "option": key,
            "evidence": ["E1"],
            "reason": "Independent review of observed code",
        }
        return {
            "id": "cpu-osa-decision",
            "usage": {"prompt_tokens": 256, "completion_tokens": 25, "total_tokens": 281},
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "activate_organization",
                                    "arguments": json.dumps(choice),
                                }
                            }
                        ]
                    }
                }
            ],
        }

    execution = Execution(
        scripted, out / "telemetry", "cpu", slot, condition, controller_backend=controller
    )
    owner = native.build_team_owner(
        execution.post,
        organization_id="FREE2",
        slot_id=slot,
        condition_id=condition,
        folder=out / "model-ledger",
        deadline=deadline,
        identity={
            "policy_version": native.VERSION,
            "model": "scripted-no-provider",
            "thinking": False,
        },
    )
    rt, _, _ = native.build_runtime(
        owner, prepared, out / "runtime", deadline=deadline, public_initial_message=native.CONTRACT
    )
    native.set_native_limit(rt, 5_000_000)
    execution.attach(rt)
    observations = []

    def step(outcome):
        actor = outcome["worker_id"]
        observations.append([actor, outcome["status"], (outcome.get("response") or {}).get("ok")])
        if len(observations) == 2:
            assert actor == "member_002" and actor in rt.waiting, observations
            node = {
                "anomaly_id": "fixture",
                "anomaly_type": "A1",
                "subject": "fixture-read",
                "affected_work": ["work_root"],
                "evidence_refs": [{"opportunity": 1, "tool": "read_file"}],
            }
            options = menu(world, node, "member_001")
            key = next(k for k, v in options["options"].items() if v["op"] == "diagnosis")
            choice = {
                "option": key,
                "reason": "Independent review of observed code",
                "evidence": ["E1"],
            }
            original_limit = execution.native_limit
            view, proposal = execution.controller_request(node, "member_001")
            assert view == options and execution.native_limit == original_limit - 281
            assert (
                json.loads(
                    proposal["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
                )
                == choice
            )
            used = rt.team_budget.snapshot()["charged_tokens"]
            rt.team_budget.native_allocation = used + 3 * CALL_BOUND - 1
            assert execution.activate(node, "member_001", options, choice)["activated"] is False
            assert menu(world, node, "member_001") == options and actor in rt.waiting
            rt.team_budget.native_allocation = used + 3 * CALL_BOUND
            execution.native_limit = rt.team_budget.native_allocation
            assert execution.activate(node, "member_001", options, choice)["changed"]
        if len(observations) == 4:
            # Exercise the closing boundary without burning hundreds of thousands of fake tokens.
            execution.native_limit = rt.team_budget.snapshot()["charged_tokens"] + CALL_BOUND + 1000
        if len(observations) == 5:
            assert requests[2:] == ["member_002", "member_002", "member_001"], requests
            assert all(v[2] for v in observations[2:]), observations
            assert not execution.grants and not execution.trace.errors
            assert world.read_page_hits >= 1
            raise Finished

    try:
        try:
            native.run_fragment(prepared, rt, on_opportunity=step)
        except Finished:
            pass
        assert len(observations) == 5, (observations, rt.stopped)
        return dict(
            condition=condition,
            provider_calls=0,
            scripted_worker_requests=len(requests),
            scripted_controller_requests=1,
            controller_usage_subtracted=281,
            actors=requests,
            native_outcomes=observations,
            read_cache_hits=world.read_page_hits,
            observer_errors=execution.trace.errors,
            underfunded_activation_rejected=True,
        )
    finally:
        native.close_runtime(rt)


def main():
    os.environ.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    rows = []
    for condition in ("T0", "T1"):
        with TemporaryDirectory(prefix="v230-local-sdk-") as path:
            os.environ["OH_PERSISTENCE_DIR"] = str(Path(path) / "sdk-settings")
            rows.append(exercise(Path(path), condition))
    atomic_write(
        ROOT / "artifacts/software-benchmark-v230/engineering-r1/sdk-control.json", json_bytes(rows)
    )
    print("Two real SDK controls passed, zero provider calls")


if __name__ == "__main__":
    main()
