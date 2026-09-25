"""Real world transitions for D2 validity; program witnesses are never model data."""

import copy
from pathlib import Path

import pytest

from proworksim.episode import assess_historical_episode, begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.information_mapper import information_graph, map_joint_method
from proworksim.member_views import member_view
from proworksim.rewards import episode_reward
from proworksim.scenarios import build_scenario
from proworksim.storage import digest, json_bytes
from proworksim.support_weights import build_support
from proworksim.team_rollout import export_team_rollout
from proworksim.team_validity import assess_team_validity
from proworksim.templates.decision_team import ROLES, scenario_spec, witness_code


class Witness:
    def __init__(self, tmp_path, layout="split_a", control="base"):
        self.spec = scenario_spec(layout=layout, control=control)
        deployment = build_scenario(self.spec, tmp_path / "world")
        assert deployment.status == "ready", deployment.diagnostics
        self.world = deployment.world
        self.recorder = ExperienceRecorder()
        self.capture = {role: [] for role in ROLES}
        self.ports = {
            role: capture_port(self.world.session(role, "TEAM"), self.capture[role])
            for role in ROLES
        }
        self.cursor = len(self.world.state["event_history"])
        self.episode = tmp_path / "episode"
        self.policies = {role: {"implementation": "explicit_program_witness"} for role in ROLES}
        self.members = {role: {"actor_id": role, "origin": "rule"} for role in ROLES}
        begin_episode(
            self.world,
            self.episode,
            experience=self.recorder.snapshot(),
            work_ids=[],
            work_nodes=["TEAM::build"],
            scenario=self.spec,
            policies=self.policies,
        )

    def call(self, role, action, **arguments):
        key = str(len(self.recorder.events))
        result = self.ports[role].call(action, request_key=key, **arguments)
        self.recorder.record(
            "tool_call",
            {"action": action, "arguments": arguments, "request_key": key, "response": result},
            worker_id=role,
        )
        for event in self.world.state["event_history"][self.cursor :]:
            self.recorder.record("environment_event", event)
        self.cursor = len(self.world.state["event_history"])
        return result

    def ok(self, role, action, **arguments):
        result = self.call(role, action, **arguments)
        assert result["ok"], result
        return result["result"]

    def transfer(self, requested=False):
        for route in self.spec["projects"][0]["package"]["information_routes"]:
            if route["provider"] in route["recipients"]:
                continue
            request = (
                self.ok(
                    route["recipients"][0],
                    "request_information",
                    route_id=route["route_id"],
                    work_id="build",
                )
                if requested
                else None
            )
            ref = self.ok(route["provider"], "read_object", alias=route["object_alias"])[
                "reference"
            ]
            self.ok(
                route["provider"],
                "handoff_information",
                route_id=route["route_id"],
                work_id="build",
                handoff_key="actual-choice",
                body="Applicable source was read",
                reference=ref,
                **({"request_id": request["request_id"]} if request else {}),
            )

    def deliver(self, inspect=True, audit_version=None):
        for alias in ["data", "basis"]:
            ref = self.ok("implementer", "read_object", alias=alias)["reference"]
            self.ok(
                "implementer",
                "adopt",
                alias=alias,
                object_id=ref.get("object_id", ref.get("artifact_id")),
                version_id=ref["version_id"],
                policy="fixed",
                work_ids=["build"],
            )
        self.ok("implementer", "write_object", alias="code", data=witness_code())
        self.ok(
            "implementer",
            "sql_build",
            work_id="build",
            code_alias="code",
            output_alias="result",
            input_aliases=["data", "basis"],
        )
        submission = self.ok("implementer", "submit", work_id="build", artifacts=["code", "result"])
        if inspect:
            self.ok(
                "reviewer",
                "inspect_submission",
                work_id="build",
                submission_id=submission["submission_id"],
            )
            for aid, vid in submission["artifact_versions"].items():
                self.ok("reviewer", "read_object", object_id=aid, version_id=vid)
            self.ok(
                "reviewer",
                "read_object",
                alias="audit_basis",
                **({"version_id": audit_version} if audit_version else {}),
            )
        self.ok("reviewer", "approve", work_id="build", submission_id=submission["submission_id"])

    def finish(self):
        finish_episode(
            self.world,
            self.episode,
            experience=self.recorder.snapshot(),
            termination={"status": "program_witness_boundary"},
        )
        self.before = digest(json_bytes(self.world.state))
        result = assess_team_validity(
            self.episode,
            members=self.members,
            independent_capture=self.capture,
            spec=self.spec["variation"]["validity_spec"],
        )
        assert digest(json_bytes(self.world.state)) == self.before
        return result


@pytest.mark.parametrize(
    "layout,requested", [("split_a", False), ("split_a", True), ("split_b", False)]
)
def test_real_handoff_read_adoption_review_and_export(tmp_path, layout, requested):
    witness = Witness(tmp_path, layout)
    witness.transfer(requested)
    witness.deliver()
    validity = witness.finish()
    assert validity["value"] is True, validity
    assessment = assess_historical_episode(witness.episode)
    reward = episode_reward(
        assessment,
        {
            "version": "reward-spec-v0.11",
            "reward_id": "fixed-content",
            "objectives": [{"kind": "content", "work_node": "TEAM::build"}],
        },
    )
    window = {
        "window_id": "witness-only",
        "xi_id": layout,
        "xi_fingerprint": digest(json_bytes(witness.spec)),
        "gamma_fingerprint": "declared-program-contract",
        "team_policy_fingerprint": digest(json_bytes(witness.policies)),
    }
    rollout = export_team_rollout(
        witness.episode, window=window, members=witness.members, validity=validity, reward=reward
    )
    mapping = map_joint_method(
        information_graph(rollout), route_id="basis", spec_id="two-manual-methods"
    )
    assert mapping["class_id"] == ("requested_handoff" if requested else "proactive_handoff"), (
        mapping
    )
    views = {role: member_view(rollout, role) for role in ROLES}
    support = build_support(
        [
            {
                "slot_id": "0",
                "window": window,
                "rollout": rollout,
                "mapping": mapping,
                "member_views": views,
            }
        ],
        window=window,
        member_ids=list(ROLES),
    )
    assert all(
        block["n_positive"] == 0 and block["semantic_work_support"] == {}
        for block in support["blocks"].values()
    )


def test_final_correctness_does_not_replace_actual_review(tmp_path):
    witness = Witness(tmp_path)
    witness.transfer()
    witness.deliver(inspect=False)
    validity = witness.finish()
    assert validity["components"]["delivery"]["value"] is True
    assert validity["components"]["basis"]["value"] is False
    assert validity["value"] is False


def test_retired_audit_basis_is_not_justified_by_correct_numbers(tmp_path):
    witness = Witness(tmp_path, control="old_versions")
    witness.transfer()
    witness.deliver(audit_version="v1")
    validity = witness.finish()
    assert validity["components"]["delivery"]["value"] is True
    assert validity["components"]["basis"]["value"] is False


def test_declared_repair_and_rejected_unauthorized_action_are_allowed(tmp_path):
    witness = Witness(tmp_path)
    refused = witness.call("implementer", "read_object", alias="basis")
    assert refused["ok"] is False
    discarded = witness.ok("implementer", "submit", work_id="build", artifacts=["code", "result"])
    witness.ok(
        "implementer",
        "withdraw",
        work_id="build",
        submission_id=discarded["submission_id"],
        reason="Real preparation correction",
    )
    witness.transfer()
    witness.deliver()
    assert witness.finish()["value"] is True


def test_missing_independent_capture_remains_unknown_and_mismatch_fails(tmp_path):
    witness = Witness(tmp_path)
    witness.transfer()
    witness.deliver()
    witness.finish()
    missing = assess_team_validity(
        witness.episode,
        members=witness.members,
        independent_capture=None,
        spec=witness.spec["variation"]["validity_spec"],
    )
    assert missing["value"] is None
    changed = copy.deepcopy(witness.capture)
    changed["provider"] = []
    mismatch = assess_team_validity(
        witness.episode,
        members=witness.members,
        independent_capture=changed,
        spec=witness.spec["variation"]["validity_spec"],
    )
    assert mismatch["components"]["record"]["value"] is False


def test_real_unavailable_reply_is_unknown_not_a_fabricated_valid_delivery(tmp_path):
    witness = Witness(tmp_path, control="unavailable")
    request = witness.ok("implementer", "request_information", route_id="basis", work_id="build")
    witness.ok("provider", "read_object", alias="basis")
    witness.ok(
        "provider",
        "handoff_information",
        route_id="basis",
        work_id="build",
        handoff_key="actual-unavailable",
        body="Only retired basis is held",
        request_id=request["request_id"],
        status="unavailable",
    )
    value = witness.finish()
    assert value["components"]["record"]["value"] is True
    assert value["components"]["permission"]["value"] is True
    assert value["components"]["basis"]["value"] is None
    assert value["components"]["delivery"]["value"] is None
    assert value["value"] is None
    assert not witness.world.state["adoptions"]
    assert not witness.world.state["work_items"]["TEAM::build"]["submissions"]


def test_materializer_keeps_missing_and_hash_mismatched_raw_slots(tmp_path):
    from scripts.team_rollout_experiment import INVENTORY_VERSION, materialize_inventory
    from proworksim.storage import atomic_write, read_json

    witness = Witness(tmp_path / "case")
    witness.transfer()
    witness.deliver()
    witness.finish()

    def pin(name, value):
        path = tmp_path / name
        atomic_write(path, json_bytes(value))
        return {"path": str(path), "sha256": digest(path.read_bytes())}

    scenario = pin("scenario.json", witness.spec)
    capture = pin("capture.json", witness.capture)
    protocol = pin("protocol.json", {"kind": "explicit_program_materialization_control"})
    window = {
        "window_id": "controlled-window",
        "xi_id": "split_a",
        "xi_fingerprint": digest(json_bytes(witness.spec)),
        "gamma_fingerprint": protocol["sha256"],
        "team_policy_fingerprint": digest(json_bytes(witness.policies)),
    }
    base = {"episode": str(witness.episode), "scenario_ref": scenario, "capture_ref": capture}
    inventory = {
        "version": INVENTORY_VERSION,
        "windows": [
            {
                "window": window,
                "members": witness.members,
                "mapper": {"route_id": "basis", "spec_id": "predeclared-two-methods"},
                "min_class_count": 2,
                "protocol_ref": protocol,
                "assessment_spec": {},
                "reward_spec": {
                    "version": "reward-spec-v0.11",
                    "reward_id": "fixed-content",
                    "objectives": [{"kind": "content", "work_node": "TEAM::build"}],
                },
                "slots": [
                    {**base, "slot_id": "present"},
                    {**base, "slot_id": "absent", "episode": str(tmp_path / "absent-episode")},
                    {
                        **base,
                        "slot_id": "wrong-hash",
                        "scenario_ref": {**scenario, "sha256": "wrong"},
                    },
                ],
            }
        ],
    }
    inventory_ref = pin("inventory.json", inventory)
    report = materialize_inventory(inventory_ref["path"], tmp_path / "materialized")
    assert report["counts_across_windows_only"]["M"] == 3
    assert report["counts_across_windows_only"]["materialized"] == 1
    assert report["counts_across_windows_only"]["unusable"] == 2
    window_report = report["windows"][0]
    assert window_report["raw_joint_valid_yield"] == {"n": 0, "M": 3, "rate": 0.0}
    assert window_report["q_equals_b_all_original_weights_one"]
    support = read_json(Path(window_report["support_ref"]["path"]))
    assert all(block["M"] == 3 and block["n_positive"] == 0 for block in support["blocks"].values())
    assert all(
        row["reward"] is None and row["validity"] is None for row in window_report["slots"][1:]
    )
    with pytest.raises(ValueError, match="new directory"):
        materialize_inventory(inventory_ref["path"], tmp_path / "materialized")
    with pytest.raises(ValueError, match="input episode"):
        materialize_inventory(inventory_ref["path"], witness.episode / "bad-export")
