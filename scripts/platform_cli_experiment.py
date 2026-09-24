"""Declared platform CLI chain; no direct calls to business worker methods."""

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import Store, digest, json_bytes

CHECKS = (
    "declaration_builds_real_world", "explicit_opportunity_cut", "checkpoint_continuation_completes",
    "original_public_experience_preserved", "assessment_executes_separate_from_workers",
    "no_undeclared_overall_score", "read_only_assessment_preserves_state_and_versions",
    "controller_and_environment_are_recorded_separately",
)
PROTOCOL = {"suite": "platform-cli-v0.10", "checks": CHECKS,
            "scenario": "examples/scenarios-v10/chain-accepted.json", "soft_cut": 8,
            "scope": "Actual CLI processes deploy a declared two-template world, cut, resume and separately assess. No prepare/deliver/review calls occur in this driver; no independent target is silently invented."}


def write(path, value):
    path.write_bytes(json_bytes(value))


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before, calls, checks, error = code_identity(), [], [], None
    write(output / "protocol.json", PROTOCOL)
    world = output / "world"

    def check(name, value):
        assert name in CHECKS and not any(c["name"] == name for c in checks)
        checks.append({"name": name, "passed": bool(value), "expected": True,
                       "actual": bool(value), "not_executed": False})

    def cli(*arguments):
        command = [sys.executable, "-m", "proworksim", *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True)
        calls.append({"command": command, "exit_code": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(calls[-1])
        return json.loads(result.stdout)

    def inventory():
        paths = [world / "control" / "state.json"]
        paths += [p for p in (world / "control" / "versions").rglob("*") if p.is_file()]
        assert len(paths) > 1
        return {str(p.relative_to(world)): digest(p.read_bytes()) for p in paths}

    try:
        built = cli("scenario-build", world, "--spec", PROTOCOL["scenario"])
        check("declaration_builds_real_world", built["status"] == "ready" and len(Store(world).load()["projects"]) == 2)
        first = output / "cut.json"
        cut = cli("staff-run", world, "--max-opportunities", 8, "--output", first)
        check("explicit_opportunity_cut", cut["status"] == "budget_exhausted" and cut["opportunities"] == 8)
        prior = json.loads(first.read_text())["worker_checkpoint"]["experience"]["events"]
        second = output / "continued.json"
        completed = cli("staff-run", world, "--checkpoint", first, "--output", second)
        check("checkpoint_continuation_completes", completed["status"] == "completed")
        experience = json.loads(second.read_text())["worker_checkpoint"]["experience"]["events"]
        check("original_public_experience_preserved", bool(prior) and experience[:len(prior)] == prior)
        files = inventory()
        assessment = output / "assessment.json"
        evaluated = cli("episode-assess", world, "--experience", second, "--output", assessment)
        result = json.loads(assessment.read_text())["assessment"]
        check("assessment_executes_separate_from_workers", evaluated["status"] == "complete" and not any(e["kind"] == "assessment" for e in experience))
        check("no_undeclared_overall_score", "passed" not in result and result["independent_targets"]["status"] == "unassessed" and result["process_constraints"]["status"] == "unassessed")
        check("read_only_assessment_preserves_state_and_versions", inventory() == files)
        kinds = {event["kind"] for event in experience}
        check("controller_and_environment_are_recorded_separately", {"controller_action", "environment_event", "tool_call", "public_observation"} <= kinds)
    except Exception:
        error = traceback.format_exc()
    done = {check["name"] for check in checks}
    checks.extend({"name": name, "passed": False, "not_executed": True} for name in CHECKS if name not in done)
    result = {"protocol": PROTOCOL, "source_before": before, "source_after": code_identity(),
              "calls": calls, "checks": checks, "error": error,
              "passed": error is None and all(c["passed"] for c in checks),
              "passed_checks": sum(c["passed"] for c in checks), "total_checks": len(CHECKS),
              "not_executed": sum(c["not_executed"] for c in checks)}
    write(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: result[key] for key in ("passed", "passed_checks", "total_checks", "not_executed")}))
    raise SystemExit(0 if result["passed"] else 1)
