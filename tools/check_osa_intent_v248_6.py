"""Replay all distinct paid v248 OSA answers against P2 without repairing missing judgments."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from unittest.mock import patch

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_membership_v247 as sdk
from proworksim import software_organization_intent_v248_6 as p2
from proworksim.storage import read_json

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v248"
OUT = ROOT / "artifacts/software-benchmark-v248/intent-replay-r1"


def historical_intent(original):
    d = original["decision"]
    intent = dict(
        assessment=original["assessment"],
        decision=d,
        coordination_cost=original["resource_plan"]["coordination_cost"],
        reevaluation=original["reevaluation"],
    )
    if d["action"] == "CHANGE":
        plan = original["execution_plan"]
        intent["change_plan"] = dict(
            **{
                k: original["expected_contribution"][k]
                for k in ("intended_use", "verification", "failure_condition")
            },
            first_action=plan["immediate_action"]["action"],
            subsequent_actions=plan["subsequent_actions"],
            preconditions=plan["preconditions"],
        )
    return intent


def replay():
    report = read_json(
        ROOT / "artifacts/software-benchmark-v248/dynamic-membership-r2/results.json"
    )
    receipts = {}
    for f in RUN.glob("*/*/O-*/osa-api/*/http_response.raw"):
        sent = read_json(f.with_name("request.json"))["payload"]
        state = json.loads(sent["wire"]["messages"][1]["content"])
        receipts[(f.parents[2].name, state["decision_key"])] = f
    rows = []
    for block in report["blocks"]:
        for arm, run in block["arms"].items():
            for step in run["decisions"]:
                case = next(
                    c["index"] for c in report["cohort"] if c["instance"] == block["instance"]
                )
                obs = (
                    RUN
                    / run["deployment"]
                    / str(case)
                    / arm
                    / "decisions"
                    / f"{step['opportunity']:04}"
                )
                state = read_json(obs / "state.json")
                raw = receipts[(arm, state["decision_key"])]
                args = read_json(raw)["choices"][0]["message"]["tool_calls"][0]["function"][
                    "arguments"
                ]
                sent = read_json(raw.with_name("request.json"))["payload"]
                assert json.loads(sent["wire"]["messages"][1]["content"]) == state
                row = dict(
                    instance=block["instance"],
                    arm=arm,
                    opportunity=step["opportunity"],
                    original=step["status"],
                    provider_sha256=sha256(raw.read_bytes()).hexdigest(),
                    source=str(raw.relative_to(ROOT)),
                )
                try:
                    original = p2.unpack(args)
                    intent = historical_intent(original)
                    compiled = p2.compile_intent(state, intent)
                    # Count only recoveries where the source actually agrees with the compiled
                    # candidate, members, operations, reservations and product bindings.
                    prior = original["organization_patch"].copy()
                    if compiled["decision"]["action"] == "KEEP" and not prior["operations"]:
                        prior["target_graph_version"] = compiled["organization_patch"][
                            "target_graph_version"
                        ]
                    assert prior == compiled["organization_patch"]
                    for key in (
                        "decision",
                        "membership_decision",
                        "expected_contribution",
                        "resource_plan",
                        "reevaluation",
                        "assessment",
                    ):
                        assert original[key] == compiled[key], key
                    if intent["decision"]["action"] == "CHANGE":
                        assert original["execution_plan"] == compiled["execution_plan"]
                    row["replay"] = compiled["decision"]["action"]
                    row["candidate"] = compiled["decision"]["candidate_id"]
                except (json.JSONDecodeError, ValueError, KeyError, ValidationError) as exc:
                    row.update(replay="rejected", reason=str(exc).splitlines()[0])
                if step["status"] != "rejected":
                    assert row["replay"] == step["status"]
                rows.append(row)
    assert len(rows) == len({r["provider_sha256"] for r in rows}) == 14
    return rows


def main():
    rows = replay()

    def scripted_answer(state, key, action="CHANGE"):
        return historical_intent(sdk_answer(state, key, action))

    sdk_answer = sdk.answer
    with (
        TemporaryDirectory() as work,
        patch.object(sdk, "answer", scripted_answer),
        patch.object(sdk, "apply", p2.apply),
    ):
        controls = sdk.exercise(Path(work))
    OUT.mkdir(parents=True, exist_ok=True)
    d = dict(
        cases=rows,
        previous=Counter(x["original"] for x in rows),
        replay=Counter(x["replay"] for x in rows),
        sdk=controls,
    )
    (OUT / "results.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(d["previous"], d["replay"], controls["paid_calls"])


if __name__ == "__main__":
    main()
