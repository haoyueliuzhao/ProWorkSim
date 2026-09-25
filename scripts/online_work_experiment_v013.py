"""Real public-action witnesses and anti-farming controls for online work scopes.

This module never samples a model or supplies demonstrations to the online actor.
"""

import argparse
import json
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.online_rewards import assess_online_reward
from proworksim.storage import json_bytes
from proworksim.templates.decision_team import witness_code
from proworksim.templates.online_work import build_online_case, registry


def ref(value):
    return {
        "object_id": value.get("object_id", value.get("artifact_id")),
        "version_id": value["version_id"],
    }


def records(table):
    return [dict(zip([c["name"] for c in table["columns"]], row)) for row in table["rows"]]


class Witness:
    def __init__(self, prepared):
        self.prepared = prepared
        self.capture = {r: [] for r in prepared.active_roles}
        self.ports = {
            r: capture_port(prepared.world.session(r, "TEAM"), self.capture[r])
            for r in self.capture
        }
        self.recorder = ExperienceRecorder()
        self.event_offset = len(prepared.world.state["event_history"])

    def call(self, actor, tool, **args):
        result = self.ports[actor].call(tool, **args)
        event = self.capture[actor][-1]
        self.recorder.record(event["kind"], event["payload"], actor)
        for event in self.prepared.world.state["event_history"][self.event_offset :]:
            self.recorder.record("environment_event", event)
        self.event_offset = len(self.prepared.world.state["event_history"])
        if not result["ok"]:
            raise ValueError(result)
        return result["result"]

    def observe(self, actor):
        obs = self.ports[actor].observe()
        self.recorder.record("public_observation", obs, actor)
        return obs

    def read(self, actor, alias):
        return self.call(actor, "read_alias", alias=alias, work_id="TEAM::build")


def supply(witness, *, repeat=False):
    evidence = witness.read("provider", "basis")
    response = witness.call(
        "provider",
        "handoff_information",
        route_id="basis",
        work_id="TEAM::build",
        handoff_key="rule-supply",
        reference=ref(evidence["reference"]),
        body="Selected the applicable approved basis for the public work period.",
    )
    if repeat:
        witness.read("provider", "basis")
        witness.call(
            "provider",
            "handoff_information",
            route_id="basis",
            work_id="TEAM::build",
            handoff_key="second-delivery",
            reference=ref(evidence["reference"]),
            body="The same exact material sent again.",
        )
    return response


def implement(witness, *, adopt=False, wrong=False):
    refs = {}
    for alias in ("data", "basis"):
        refs[alias] = ref(witness.read("implementer", alias)["reference"])
        if adopt:
            witness.call(
                "implementer",
                "adopt",
                alias=alias,
                **refs[alias],
                policy="fixed",
                work_ids=["TEAM::build"],
            )
    code = witness_code()
    if wrong:
        code["models"][0]["sql"] = code["models"][0]["sql"].replace(
            "COUNT(DISTINCT order_id)", "COUNT(order_id)"
        )
    witness.call(
        "implementer",
        "write_object",
        alias="code",
        data=code,
        dependencies=list(refs.values()),
        work_id="TEAM::build",
    )
    witness.call(
        "implementer",
        "sql_build",
        work_id="TEAM::build",
        code_alias="code",
        output_alias="result",
        input_aliases=["data", "basis"],
    )
    witness.call(
        "implementer", "preflight_submission", work_id="TEAM::build", artifacts=["code", "result"]
    )
    return witness.call(
        "implementer", "submit", work_id="TEAM::build", artifacts=["code", "result"]
    )


def review(witness, *, judgment="correct", wrong_location=False):
    obs = witness.observe("reviewer")
    item = obs["work_items"]["TEAM::build"]
    sid = item.get("pending_submission_id") or item["latest_submission_id"]
    submission = witness.call(
        "reviewer", "inspect_submission", work_id="TEAM::build", submission_id=sid
    )
    workspace = obs["workspaces"]["TEAM"]
    documents = {}
    for alias in ("code", "result"):
        oid = workspace[alias]
        documents[alias] = witness.call(
            "reviewer",
            "read_version",
            reference={"object_id": oid, "version_id": submission["artifact_versions"][oid]},
            work_id="TEAM::build",
        )
    for alias in ("data", "audit_basis"):
        documents[alias] = witness.read("reviewer", alias)
    if judgment == "read_only":
        return None
    data = documents["data"]["data"]["tables"]
    audit = documents["audit_basis"]["data"]
    actual = records(documents["result"]["data"]["tables"]["metrics"])
    errors = []
    for index, row in enumerate(actual):
        eligible = [
            p
            for p in records(data["transactions"])
            if p["customer_id"] == row["customer_id"]
            and p["period"] == audit["period"]
            and p["status"] in audit["allowed_statuses"]
        ]
        expected = (
            sum(p["amount"] * audit["amount_factor"] for p in eligible),
            len({p["order_id"] for p in eligible}),
        )
        if (row["revenue_cents"], row["order_count"]) != expected:
            errors.append(index)
    if judgment == "approve_any" or not errors:
        return witness.call("reviewer", "approve", work_id="TEAM::build", submission_id=sid)
    index = 2 if wrong_location else errors[0]
    return witness.call(
        "reviewer",
        "raise_issue",
        work_id="TEAM::build",
        submission_id=sid,
        issue_key="independent-count-check",
        **ref(documents["result"]["reference"]),
        locator=["tables", "metrics", "rows", index, 2],
        description="This exact result cell disagrees with the independently read distinct-order business condition.",
        evidence=[ref(documents["data"]["reference"]), ref(documents["audit_basis"]["reference"])],
    )


def run_case(case_id, root, *, control=None):
    prepared = build_online_case(case_id, root)
    root = Path(root)
    witness = Witness(prepared)
    begin_episode(
        prepared.world,
        root / "episode",
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        scenario=prepared.scenario,
        policies={
            r: {"implementation": "explicit_rule_witness", "config": {"control": control}}
            for r in prepared.active_roles
        },
    )
    task = prepared.case["task"]
    if control != "no_actions":
        if task == "handoff":
            if control == "read_only":
                witness.read("provider", "basis")
            else:
                supply(witness, repeat=control == "repeat")
        elif task == "implement":
            implement(witness, wrong=control == "wrong_sql")
        elif task == "review":
            review(
                witness,
                judgment="approve_any"
                if control == "bad_approval"
                else "read_only"
                if control == "read_only"
                else "correct",
                wrong_location=control == "wrong_location",
            )
        else:
            supply(witness)
            implement(witness, adopt=True)
            if control != "without_review":
                review(witness)
    finish_episode(
        prepared.world,
        root / "episode",
        experience=witness.recorder.snapshot(),
        termination={"status": "rule_witness_boundary", "model_execution": False},
    )
    reward = assess_online_reward(root / "episode", prepared.reward_spec)
    (root / "capture.json").write_bytes(json_bytes(witness.capture))
    (root / "reward.json").write_bytes(json_bytes(reward))
    report = {
        "case_id": case_id,
        "control": control,
        "origin": "rule_witness",
        "source": code_identity(),
        "reward": reward,
        "prefix_event_count": len(prepared.prefix["experience"]["events"]),
        "target_action_counts": {
            r: sum(
                e["kind"] == "tool_call" and e.get("worker_id") == r
                for e in witness.recorder.events
            )
            for r in prepared.active_roles
        },
        "current_episode_excludes_prefix": len(read_events(root / "episode/start-experience.json"))
        == 0,
    }
    (root / "report.json").write_bytes(json_bytes(report))
    return report


def read_events(path):
    return json.loads(path.read_text())["events"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "registry.json").write_bytes(json_bytes(registry()))
    reports = []
    for window in range(2):
        for task in ("handoff", "implement", "review", "chain"):
            identity = f"train-w{window}-{task}"
            reports.append(run_case(identity, args.output / identity))
    controls = [
        ("train-w0-handoff", "read_only", 0.25),
        ("train-w0-handoff", "repeat", 1),
        ("train-w0-implement", "no_actions", 0),
        ("train-w0-implement", "wrong_sql", 0.2),
        ("train-w0-review", "no_actions", 0),
        ("train-w1-review", "bad_approval", 0.25),
        ("train-w1-review", "wrong_location", 0.25),
        ("train-w0-chain", "without_review", 0.5),
    ]
    checks = [
        r["reward"]["eligible"]
        and r["reward"]["reward"] == 1
        and r["current_episode_excludes_prefix"]
        for r in reports
    ]
    for index, (identity, control, expected) in enumerate(controls):
        report = run_case(identity, args.output / f"control-{index}", control=control)
        report["expected_reward"] = expected
        checks.append(
            report["reward"]["eligible"]
            and report["reward"]["reward"] == expected
            and report["current_episode_excludes_prefix"]
        )
        reports.append(report)
    result = {
        "source": code_identity(),
        "model_execution": False,
        "training": False,
        "reports": reports,
        "checks_passed": sum(checks),
        "checks_total": len(checks),
    }
    (args.output / "report.json").write_bytes(json_bytes(result))
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}))
    if not all(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
