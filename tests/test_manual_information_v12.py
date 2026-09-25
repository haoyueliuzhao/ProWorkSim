"""Real manual provider choices; transport never fabricates a provider decision."""

import copy

from proworksim.scenarios import build_scenario
from proworksim.templates.decision_team import scenario_spec


def fixture(tmp_path, layout="split_a", control="base"):
    deployment = build_scenario(scenario_spec(layout=layout, control=control), tmp_path / "world")
    assert deployment.status == "ready", deployment.diagnostics
    return deployment.world


def read(world, actor, alias, version=None):
    result = world.session(actor, "TEAM").call(
        "read_object", alias=alias, **({"version_id": version} if version else {})
    )
    assert result["ok"], result
    return result["result"]["reference"]


def handoff(world, actor, route, ref, request_id=None, key="delivery"):
    return world.session(actor, "TEAM").call(
        "handoff_information",
        route_id=route,
        work_id="build",
        handoff_key=key,
        body="Read and supply this selected exact evidence",
        reference=ref,
        **({"request_id": request_id} if request_id else {}),
    )


def test_request_does_not_choose_or_automatically_reply(tmp_path):
    world = fixture(tmp_path)
    worker = world.session("implementer", "TEAM")
    requested = worker.call("request_information", route_id="basis", work_id="build")
    assert requested["ok"] and requested["result"]["automatic_reply_scheduled"] is False
    assert world.state["events"] == []
    assert worker.call("wait", ticks=50)["ok"]
    assert world.state["raw_condition_responses"] == {}
    assert not world.state["handoffs"]
    assert worker.call("read_object", alias="basis")["ok"] is False
    assert world.state["condition_specs"][requested["result"]["condition_id"]]["status"] == "open"


def test_provider_selects_old_version_without_hidden_correction(tmp_path):
    world = fixture(tmp_path, control="old_versions")
    worker = world.session("implementer", "TEAM")
    request = worker.call("request_information", route_id="basis", work_id="build")["result"]
    ref = read(world, "provider", "basis", "v1")
    sent = handoff(world, "provider", "basis", ref, request["request_id"])
    assert sent["ok"]
    basis = world.state["workspaces"]["TEAM"]["basis"]
    assert worker.observe()["objects"][basis]["versions"] == ["v1"]
    assert worker.call("read_object", alias="basis", version_id="v2")["ok"] is False
    response = next(iter(world.state["raw_condition_responses"].values()))
    assert response["reference"] == {"object_id": basis, "version_id": "v1"}
    assert response["origin"] == "member_action"
    assert world.state["condition_specs"][request["condition_id"]]["status"] == "resolved"
    # Resolved here certifies receipt, not correct period or business semantics.
    assert not world.state["adoptions"]


def test_proactive_handoff_has_no_invented_request_or_adoption(tmp_path):
    world = fixture(tmp_path)
    ref = read(world, "provider", "basis")
    result = handoff(world, "provider", "basis", ref)
    assert result["ok"] and result["result"]["request_id"] is None
    assert not world.state["requests"] and not world.state["raw_condition_responses"]
    assert world.session("implementer", "TEAM").call("read_object", alias="basis")["ok"]
    assert world.state["adoptions"] == {}
    assert world.state["work_items"]["TEAM::build"]["submissions"] == []


def test_actual_reviewer_request_matches_its_own_identity(tmp_path):
    world = fixture(tmp_path, layout="split_b")
    request = world.session("reviewer", "TEAM").call(
        "request_information", route_id="audit_basis", work_id="build"
    )["result"]
    ref = read(world, "provider", "audit_basis")
    assert handoff(world, "provider", "audit_basis", ref, request["request_id"])["ok"]
    assert world.state["requests"][request["request_id"]]["requester_id"] == "reviewer"
    assert world.state["condition_specs"][request["condition_id"]]["status"] == "resolved"
    assert world.session("reviewer", "TEAM").call("read_object", alias="audit_basis")["ok"]
    assert (
        world.session("implementer", "TEAM").call("read_object", alias="audit_basis")["ok"] is False
    )


def test_queued_handoff_does_not_expose_evidence_to_recipient(tmp_path):
    world = fixture(tmp_path, control="late")
    worker = world.session("implementer", "TEAM")
    ref = read(world, "provider", "basis")
    sent = handoff(world, "provider", "basis", ref)
    assert sent["ok"]
    assert worker.observe()["handoffs"] == {}
    assert worker.call("read_object", alias="basis")["ok"] is False
    assert worker.call("wait", ticks=6)["ok"]
    assert sent["result"]["handoff_id"] in worker.observe()["handoffs"]
    assert worker.call("read_object", alias="basis")["ok"]


def test_sender_read_authority_and_idempotent_delivery(tmp_path):
    world = fixture(tmp_path)
    provider = world.session("provider", "TEAM")
    oid = world.state["workspaces"]["TEAM"]["basis"]
    ref = {"object_id": oid, "version_id": "v1"}
    assert handoff(world, "provider", "basis", ref)["ok"] is False
    read(world, "provider", "basis")
    sent = handoff(world, "provider", "basis", ref)
    assert sent["ok"]
    shares = copy.deepcopy(world.state["shares"])
    again = handoff(world, "provider", "basis", ref)
    assert again["ok"] and again["result"]["created"] is False
    assert world.state["shares"] == shares
    assert handoff(world, "implementer", "basis", ref, key="unauthorized")["ok"] is False
    assert (
        provider.call(
            "handoff_information",
            route_id="basis",
            work_id="build",
            handoff_key="delivery",
            body="Different meaning",
            reference=ref,
        )["ok"]
        is False
    )


def test_unavailable_is_a_real_member_response_without_grant(tmp_path):
    world = fixture(tmp_path, control="unavailable")
    worker = world.session("implementer", "TEAM")
    request = worker.call("request_information", route_id="basis", work_id="build")["result"]
    read(world, "provider", "basis")
    response = world.session("provider", "TEAM").call(
        "handoff_information",
        route_id="basis",
        work_id="build",
        handoff_key="unavailable",
        body="Only a retired period is held; no approved requested-period evidence exists.",
        status="unavailable",
        request_id=request["request_id"],
    )
    assert response["ok"]
    assert world.state["condition_specs"][request["condition_id"]]["status"] == "unavailable"
    assert worker.call("read_object", alias="basis")["ok"] is False
    assert next(iter(world.state["raw_condition_responses"].values()))["origin"] == "member_action"


def test_old_reply_is_history_and_cannot_satisfy_replacement(tmp_path):
    world = fixture(tmp_path, control="late")
    worker = world.session("implementer", "TEAM")
    request = worker.call("request_information", route_id="basis", work_id="build")["result"]
    ref = read(world, "provider", "basis")
    sent = handoff(world, "provider", "basis", ref, request["request_id"])
    assert sent["ok"]
    revised = world.session("operator", "TEAM").call(
        "revise",
        work_id="build",
        updates={"goal": "Same declared SQL contract under a fresh work edition"},
        reason="Predeclared late-reply scope control",
    )
    assert revised["ok"]
    replacement = revised["result"]["replacements"]["TEAM::build"]
    assert worker.call("wait", ticks=6)["ok"]
    assert world.state["handoffs"][sent["result"]["handoff_id"]]["status"] == "obsolete"
    assert world.state["condition_specs"][request["condition_id"]]["status"] == "superseded"
    assert worker.call("read_object", alias="basis")["ok"] is False
    assert world.state["work_items"][replacement]["submissions"] == []
    assert not world.state["adoptions"]


def test_holding_evidence_does_not_authorize_rewriting_its_business_facts(tmp_path):
    world = fixture(tmp_path)
    held = world.session("provider", "TEAM").call("read_object", alias="basis")
    assert held["ok"]
    assert (
        world.session("provider", "TEAM").call(
            "write_object", alias="basis", data=held["result"]["data"]
        )["ok"]
        is False
    )
    assert handoff(world, "provider", "basis", held["result"]["reference"])["ok"]


def test_generic_automatic_request_cannot_bypass_manual_provider_decision(tmp_path):
    world = fixture(tmp_path)
    oid = world.state["workspaces"]["TEAM"]["basis"]
    automatic = world.session("implementer", "TEAM").call(
        "request",
        work_id="build",
        provider="provider",
        reference={"object_id": oid, "version_id": "v1"},
        purpose="basis",
        delay=1,
    )
    assert automatic["ok"] is False
    assert automatic["error"]["rejection"]["code"] == "manual_route_requires_member_handoff"
    assert world.state["requests"] == {} and world.state["events"] == []
    assert world.state["raw_condition_responses"] == {} and world.state["handoffs"] == {}
    assert world.state["knowledge"]["provider"]["read_artifacts"] == []
    assert world.session("implementer", "TEAM").call("read_object", alias="basis")["ok"] is False
