import json

import pytest

from proworksim import software_benchmark_rescore_policy_v063 as policy
from proworksim import software_benchmark_scorer_v063 as scorer
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold


def test_pending_grant_and_foreign_operations_never_reach_resources(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", path)
    path.write_text(json.dumps({"version": policy.VERSION, "status": "pending"}))
    with pytest.raises(SharedServerHold, match="pending"):
        policy.require_v063_allowed("v063.run")
    with pytest.raises(SharedServerHold, match="outside"):
        policy.require_v063_allowed("v063.grader.create", instance_id="psf__requests-1921")
    with pytest.raises(SharedServerHold, match="outside"):
        policy.require_v063_allowed("v062.run")


def test_single_lane_and_each_of_three_claims_is_consumed_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "BATCH_ROOT", tmp_path)
    auth = tmp_path / "grant.json"
    auth.write_text("{}")
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", auth)
    keys = ["control-" + policy.TASK + "-gold", "control-" + policy.TASK + "-empty", policy.SCORE_KEY]
    plan = write_new(tmp_path / "plan.json", {"resources": {key: {} for key in keys}})
    monkeypatch.setattr(policy, "require_v063_allowed", lambda *_: {"plan": plan})
    with pytest.raises(ValueError, match="Only the two controls"):
        policy.claim_resource("score-30")
    first = policy.claim_resource(keys[0])
    with pytest.raises(ValueError, match="occupied"):
        policy.claim_resource(keys[1])
    assert policy.release_resource(first, quiescent=False) is False
    assert policy.release_resource(first, quiescent=True) is True
    with pytest.raises(ValueError, match="consumed"):
        policy.claim_resource(keys[0])
    for key in keys[1:]:
        claim = policy.claim_resource(key)
        assert policy.release_resource(claim, quiescent=True) is True
        assert reference(claim["path"]) == claim
    assert len(list((tmp_path / "resource-claims").glob("*.json"))) == 3


def test_parent_progress_remains_checked_after_cleanup_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.parent, "COORDINATOR_RUN_ROOT", tmp_path)
    summary = write_new(tmp_path / "run-summary.json", {})
    progress = tmp_path / "progress.json"
    progress.write_text(json.dumps({"phase": "closed", "failure": None, "summary": summary}))
    calls = []
    monkeypatch.setattr(policy, "_validate_parent_cleanup", lambda sha: calls.append(sha))
    assert policy.require_parent_quiescent() == summary
    progress.write_text(json.dumps({"phase": "running", "failure": None, "summary": summary}))
    with pytest.raises(SharedServerHold, match="Wait for"):
        policy.require_parent_quiescent()
    assert calls == [summary["sha256"]]


def test_even_self_consistent_substitute_candidate_is_rejected(tmp_path, monkeypatch):
    original = {"candidate_lock": {"sha256": "original"}}
    original_ref = write_new(tmp_path / "original-request.json", original)
    monkeypatch.setattr(scorer, "_planned", lambda _: (
        {"original_score_request": original_ref}, {"role": "score"}, {}))
    request = {"version": scorer.VERSION, "limits": scorer.LIMITS,
               "resource_key": policy.SCORE_KEY, "candidate_lock": {"sha256": "substitute"}}
    with pytest.raises(ValueError, match="exact original"):
        scorer.validate_request(request)


@pytest.mark.parametrize("override", [
    {"mounts": ["/host"]}, {"network_mode": "host"}, {"ports": {"80": 80}},
    {"device_requests": ["gpu"]}, {"privileged": True}, {"cap_add": ["NET_ADMIN"]},
])
def test_new_grader_refuses_host_or_network_extensions(override):
    with pytest.raises(ValueError):
        scorer.validate_options({"image": "sha256:fixed", **override}, "sha256:fixed")
