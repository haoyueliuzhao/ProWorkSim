"""Six real refusal observations, with explicit v0.9 failure attribution.

The last case deliberately faults an advertised implementation. This is a
controlled implementation exception, not an observed spontaneous runtime defect.
"""

import argparse
import copy
import json
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, json_bytes
from proworksim.tool_outcomes import classify_tool_result
from proworksim.world_core import WorldCore
if __package__:
    from .continuous_worker_experiment import package
else:
    from continuous_worker_experiment import package

EXPECTED = {
    "invalid_arguments": "policy_error",
    "permission_denied": "policy_error",
    "unknown_tool": "capability_gap",
    "superseded_work": "business_constraint",
    "world_paused": "business_constraint",
    "implementation_exception": "environment_error",
}
PROTOCOL = {
    "suite": "tool-rejection-attribution-v0.9",
    "cases": EXPECTED,
    "checks_per_case": ["actual_tool_rejection", "explicit_rejection_facts", "attribution", "business_state_preserved"],
    "measurement": "Call real bound WorldCore sessions, preserve exact response, then classify only structured rejection facts. No text heuristics.",
    "implementation_exception": "One deliberate KeyError injection into the real advertised wait action. An implementation boundary must explicitly classify this; it is not a spontaneous production failure.",
    "historical_context": "v0.8 pause probe raw outcome remains valid. Current general attribution separates policy mistakes, legitimate constraints, capability gaps and implementation exceptions.",
    "source_note": "Current run identity brackets this driver; frozen v0.8 before evidence is kept separately.",
}


def run(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    atomic_write(root / "protocol.json", json_bytes(PROTOCOL))
    world = WorldCore.create(root / "world", WorldSpec(
        "tool-rejection-v09", {"alice": {}, "bob": {}, "manager": {}},
        bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": power}
                          for power in ("install_project", "pause_world")],
    ))
    manager = world.session("manager")
    installed = manager.call("install_project", package=package("A"))
    if not installed.get("ok"):
        raise AssertionError(installed)
    alice = world.session("alice", "A")
    cases = []

    def business_state():
        state = world.store.load()
        return {key: copy.deepcopy(state.get(key)) for key in (
            "work_items", "artifacts", "adoptions", "projects", "workspaces", "issues",
        )}

    def capture(case, session, action, **arguments):
        prior = business_state()
        response = session.call(action, **arguments)
        outcome = classify_tool_result(response)
        facts = outcome["rejection"]
        checks = {
            "actual_tool_rejection": response.get("ok") is False,
            "explicit_rejection_facts": bool(facts["code"] and facts["type"] and facts["context"]),
            "attribution": outcome["status"] == EXPECTED[case],
            "business_state_preserved": business_state() == prior,
        }
        cases.append({"case": case, "actor": session.actor_id, "project": session.project_id,
                      "action": action, "arguments": arguments, "response": response,
                      "outcome": outcome, "expected_category": EXPECTED[case], "checks": checks})

    capture("invalid_arguments", alice, "wait", unexpected=True)
    capture("permission_denied", world.session("alice"), "pause")
    capture("unknown_tool", alice, "never_registered")
    changed = world.session("manager", "A").call(
        "revise", work_id="work-1", updates={"goal": "Current edition"},
        reason="A genuine new requirement",
    )
    if not changed.get("ok"):
        raise AssertionError(changed)
    capture("superseded_work", alice, "submit", work_id="work-1", artifacts=[])
    if not manager.call("pause")["ok"]:
        raise AssertionError("Authorized pause failed")
    capture("world_paused", alice, "wait", ticks=1)
    if not manager.call("resume")["ok"]:
        raise AssertionError("Authorized resume failed")

    def faulty_wait(*args, **kwargs):
        raise KeyError("injected internal implementation key")

    world._action_wait = faulty_wait
    capture("implementation_exception", alice, "wait", ticks=1)
    result = {"protocol": PROTOCOL["suite"], "source_before": before, "source_after": code_identity(),
              "cases": cases, "passed": all(all(case["checks"].values()) for case in cases),
              "checks_passed": sum(sum(case["checks"].values()) for case in cases), "checks_total": 24}
    atomic_write(root / "report.json", json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_total")}))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
