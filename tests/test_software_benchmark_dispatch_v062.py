import json

import pytest

from proworksim import software_benchmark_dispatch_v062 as policy
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold


def test_missing_or_completed_grant_cannot_enter(tmp_path, monkeypatch):
    auth = tmp_path / "grant.json"
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", auth)
    with pytest.raises(SharedServerHold, match="unavailable"):
        policy.require_v062_allowed("v062.run")
    auth.write_text(json.dumps({"version": policy.VERSION, "status": "completed"}))
    with pytest.raises(SharedServerHold, match="pending or closed"):
        policy.require_v062_allowed("v062.run")
    with pytest.raises(SharedServerHold, match="outside"):
        policy.require_v062_allowed("v061.run")


def test_claim_is_single_use_and_release_requires_quiescence(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "BATCH_ROOT", tmp_path)
    authorization = tmp_path / "grant.json"
    authorization.write_text("{}")
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", authorization)
    resources = {f"actor-{i}": {"role": "actor", "slot_id": str(i)} for i in range(3)}
    plan = write_new(tmp_path / "plan.json", {"resources": resources})
    monkeypatch.setattr(policy, "require_v062_allowed", lambda operation: {"plan": plan})
    first = policy.claim_resource("actor-0")
    policy.claim_resource("actor-1")
    with pytest.raises(ValueError, match="already consumed"):
        policy.claim_resource("actor-0")
    assert policy.release_resource(first, quiescent=False) is False
    with pytest.raises(ValueError, match="occupied"):
        policy.claim_resource("actor-2")
    assert policy.release_resource(first, quiescent=True) is True
    policy.claim_resource("actor-2")
    assert reference(first["path"]) == first


def diagnostic_evidence(tmp_path, monkeypatch, *, prior_passed=True, sources_changed=True,
                        model_calls=0, quiescent=True):
    monkeypatch.setattr(policy, "BATCH_ROOT", tmp_path)
    source = tmp_path / "current.py"
    source.write_text("current = True")
    current_sources = [reference(source)]
    monkeypatch.setattr(policy, "sources", lambda: current_sources)
    previous_source = tmp_path / "previous.py"
    previous_source.write_text("current = False")
    prior_sources = [reference(previous_source)] if sources_changed else current_sources
    quiet = write_new(tmp_path / "quiet.json", {"quiescent": quiescent, "cleanup_errors": [], "create_result_unknown": False})
    folder = tmp_path / "diagnostic-1"
    folder.mkdir()
    result = write_new(folder / "result.json", {"quiescence": quiet, "measurement_kind": "zero_model_diagnostic",
        "model_calls": model_calls, "diagnostic_passed": prior_passed, "passed": prior_passed,
        "execution_arm": "BASE5M"})
    attempts = tmp_path / "diagnostic-attempts"
    attempts.mkdir()
    prior = {"arm": "BASE", "diagnostic_index": 1, "result": result, "sources": prior_sources}
    write_new(attempts / "1.json", prior)
    write_new(attempts / "3-intent.json", {"arm": "BASE", "index": 3, "sources": current_sources})
    return {"role": "actor", "repair_of": 1, "diagnostic_index": 3, "execution_arm": "BASE5M"}, prior


@pytest.mark.parametrize("prior_passed", [True, False])
def test_revised_source_diagnostic_accepts_old_pass_or_failure(tmp_path, monkeypatch, prior_passed):
    spec, _ = diagnostic_evidence(tmp_path, monkeypatch, prior_passed=prior_passed)
    assert policy.validate_reserved_diagnostic(spec)["prior_passed"] is prior_passed


def test_reserved_diagnostic_rejects_unchanged_sources(tmp_path, monkeypatch):
    spec, _ = diagnostic_evidence(tmp_path, monkeypatch, sources_changed=False)
    with pytest.raises(ValueError, match="changed sources"):
        policy.validate_reserved_diagnostic(spec)


def test_reserved_diagnostic_rejects_current_source_qualification(tmp_path, monkeypatch):
    spec, prior = diagnostic_evidence(tmp_path, monkeypatch)
    folder = tmp_path / "diagnostic-qualifications/BASE"
    folder.mkdir(parents=True)
    write_new(folder / "1.json", {**prior, "sources": policy.sources()})
    with pytest.raises(ValueError, match="already has a current-source"):
        policy.validate_reserved_diagnostic(spec)


@pytest.mark.parametrize("values", [{"model_calls": 1}, {"quiescent": False}])
def test_reserved_diagnostic_rejects_model_or_unquiet_predecessor(tmp_path, monkeypatch, values):
    spec, _ = diagnostic_evidence(tmp_path, monkeypatch, **values)
    with pytest.raises(ValueError, match="zero-model, fully quiescent"):
        policy.validate_reserved_diagnostic(spec)
