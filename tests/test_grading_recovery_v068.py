import json
from pathlib import Path
import time
from types import FunctionType, ModuleType, SimpleNamespace

import pytest

from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim import software_benchmark_grading_recovery_v068 as recovery
from proworksim import software_benchmark_requests_tls_v068 as lifecycle
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def cloned_evaluator(events, *, fail=False, duplicate=False, finish_error=False):
    module = ModuleType("cpu_official_fixture")
    def cleanup(client, container, logger):
        events.append("upstream_remove")
    module.cleanup_container = cleanup
    source = "def run_instance(client, container, logger):\n    cleanup_container(client, container, logger)\n"
    if duplicate:
        source += "    cleanup_container(client, container, logger)\n"
    source += "    raise RuntimeError('upstream failure')\n" if fail else "    return 'official-result'\n"
    exec(source, module.__dict__)
    private = FunctionType(module.run_instance.__code__, dict(module.__dict__))
    container = SimpleNamespace(id="a" * 64)
    def finish():
        events.extend(["CA_final_identity", "relay_done"])
        if finish_error:
            raise ValueError("CA measurement unavailable")
    tracking = {"owned_container_ids": [container.id],
        "environment_container": SimpleNamespace(delegate=container, finish_transport=finish)}
    return module, private, container, tracking


def test_clone_namespace_receives_hook_order_is_correct_and_finish_idempotent():
    events = []
    module, private, container, tracking = cloned_evaluator(events, duplicate=True)
    original = module.cleanup_container
    assert private.__globals__ is not module.__dict__
    assert lifecycle.run_official(private, None, container, None, tracking=tracking) == "official-result"
    assert events == ["CA_final_identity", "relay_done", "upstream_remove", "upstream_remove"]
    assert private.__globals__["cleanup_container"] is original and module.cleanup_container is original
    assert tracking["tls_lifecycle"]["binding_restored"] is True


def test_upstream_exception_restores_actual_binding_and_foreign_container_is_refused():
    events = []
    module, private, container, tracking = cloned_evaluator(events, fail=True)
    with pytest.raises(RuntimeError, match="upstream failure"):
        lifecycle.run_official(private, None, container, None, tracking=tracking)
    assert private.__globals__["cleanup_container"] is module.cleanup_container
    events.clear()
    with pytest.raises(ValueError, match="outside this TLS wrapper"):
        lifecycle.run_official(private, None, SimpleNamespace(id="b" * 64), None, tracking=tracking)
    assert events == [] and private.__globals__["cleanup_container"] is module.cleanup_container


def test_measurement_exception_still_cleans_resource_and_remains_recorded():
    events = []
    module, private, container, tracking = cloned_evaluator(events, finish_error=True)
    lifecycle.run_official(private, None, container, None, tracking=tracking)
    assert events[-1] == "upstream_remove"
    assert tracking["transport_cleanup_errors"] == ["CA measurement unavailable"]
    assert private.__globals__["cleanup_container"] is module.cleanup_container


def test_private_scorer_changes_only_private_lifecycle_binding():
    old = recovery.original_scorer
    callback, environment = old.environment.tls.run_official, old.environment
    cloned = recovery.scorer_with_tls_lifecycle()
    private = cloned.__globals__["_score"]
    assert private.__globals__["environment"].tls.run_official is lifecycle.run_official
    assert private.__code__ is old._score.__code__ and cloned.__code__ is old.score_request.__code__
    assert old.environment is environment and old.environment.tls.run_official is callback


def fixture(tmp_path, monkeypatch):
    batch = tmp_path / "r3"
    key, task, identity = "control-psf__requests-1921-gold", "psf__requests-1921", "a" * 64
    folder = batch / "grading" / key
    (folder / "official-output").mkdir(parents=True)
    claims = batch / "resource-claims"
    claims.mkdir()
    plan = write_new(batch / "plan.json", {"frozen": True})
    config = {"instance_id": task, "scorer_request_base": {"docker_socket": "/unused.sock"}}
    request = {"directory": str(folder), "resource_key": key, "instance_id": task, "plan": plan}
    request_ref = write_new(folder / "request.json", request)
    claim = {"version": primary.VERSION, "key": key, "plan": plan, "lease": str(claims / "active-grader-2.json"),
             "spec": {"role": "control", "instance_id": task}}
    claim_ref = write_new(claims / (key + ".json"), claim)
    Path(claim["lease"]).write_bytes(Path(claim_ref["path"]).read_bytes())
    write_new(folder / "capacity-claim.json", {"prepared_request": request_ref, "claim": claim_ref})
    write_new(folder / "started.json", {"request": request_ref})
    write_new(folder / "completion.json", {"request": request_ref, "resource_key": key,
        "status": "technical_unknown", "returncode": 0, "started_unix": 1., "finished_unix": 2.,
        "capacity_claim": claim_ref})
    transport = write_new(folder / "official-output/transport.json", {"thread_finished": True,
        "original_ca_after": None, "original_ca_unchanged": False, "status": "failed"})
    write_new(folder / "official-output/initial-container.json", {"container_id": identity})
    write_new(folder / "quiescence.json", {"resource_key": key, "quiescent": False,
        "cleanup_errors": ["CA final identity: missing container"], "owned_container_ids": [identity],
        "create_result_unknown": False, "other_containers_affected": False, "transport_result": transport})
    write_new(folder / "receipt.json", {"status": "technical_unknown", "resolved": None})
    release_globals = {**primary.__dict__, "BATCH_ROOT": batch}
    release = FunctionType(primary.release_resource.__code__, release_globals,
        argdefs=primary.release_resource.__defaults__)
    monkeypatch.setattr(recovery, "primary", SimpleNamespace(BATCH_ROOT=batch, GRADING_ROOT=batch / "grading",
        PLAN_FILE=batch / "plan.json", VERSION=primary.VERSION, release_resource=release))
    monkeypatch.setattr(recovery, "original_scorer", SimpleNamespace(_planned=lambda _: ({}, {}, config),
        environment=SimpleNamespace(TLS_TASKS={task})))
    calls = []
    def inspector(value, **kwargs):
        calls.append(value)
        return {"container_id": value, "exists": False, "status": 404, "inspected_unix": time.time()}
    guard_calls = []
    wrapper = recovery.RecoveryGrading(base=SimpleNamespace(trustworthy_cleanup=lambda _: False),
        guard=lambda *args, **kwargs: guard_calls.append((args, kwargs)), inspector=inspector,
        releaser=release, proof_root=tmp_path / "new-proofs", original_reconciliations={})
    return wrapper, request_ref, folder, claim_ref, calls, guard_calls


def test_fresh_exact_absence_releases_only_claim_without_changing_unknown_result(tmp_path, monkeypatch):
    wrapper, request, folder, claim_ref, calls, guard_calls = fixture(tmp_path, monkeypatch)
    originals = {name: (folder / name).read_bytes() for name in ("receipt.json", "quiescence.json", "completion.json")}
    claim = recovery.load(claim_ref)
    unrelated = Path(claim["lease"]).with_name("active-grader-1.json")
    unrelated.write_bytes(b'{"belongs":"other"}\n')
    assert wrapper.trustworthy_cleanup(request) is True
    assert calls == ["a" * 64] and len(guard_calls) == 1
    assert not Path(claim["lease"]).exists() and unrelated.read_bytes() == b'{"belongs":"other"}\n'
    assert all((folder / name).read_bytes() == value for name, value in originals.items())
    # A lane now owned by another job must neither be removed nor re-inspected.
    Path(claim["lease"]).write_bytes(b'{"belongs":"next-job"}\n')
    assert wrapper.trustworthy_cleanup(request) is True
    assert calls == ["a" * 64] and Path(claim["lease"]).read_bytes() == b'{"belongs":"next-job"}\n'


def test_physical_proof_does_not_invent_a_missing_score_receipt(tmp_path, monkeypatch):
    wrapper, request, folder, _, _, _ = fixture(tmp_path, monkeypatch)
    (folder / "receipt.json").unlink()
    assert wrapper.trustworthy_cleanup(request) is True
    proof = json.loads(next(p for p in wrapper.proof_root.glob("*.json") if "reservation-release" not in p.name).read_bytes())
    assert proof["original_scoring_status_unchanged"] == "missing"
    assert proof["original_receipt"] is None and proof["scoring_evidence_recovered"] is False
    assert not (folder / "receipt.json").exists()


@pytest.mark.parametrize("change", ["exists", "stale", "wrong_id", "thread_alive", "unknown_create", "process_unknown"])
def test_unsafe_or_incomplete_absence_never_releases_or_certifies(tmp_path, monkeypatch, change):
    wrapper, request, folder, claim_ref, _, _ = fixture(tmp_path, monkeypatch)
    if change in {"exists", "stale", "wrong_id"}:
        wrapper.inspector = lambda value, **kwargs: {"container_id": "b" * 64 if change == "wrong_id" else value,
            "exists": change == "exists", "status": 200 if change == "exists" else 404,
            "inspected_unix": 1. if change == "stale" else time.time()}
    else:
        path = folder / ("quiescence.json" if change in {"thread_alive", "unknown_create"} else "completion.json")
        value = json.loads(path.read_bytes())
        if change == "thread_alive":
            transport = recovery.load(value["transport_result"])
            transport["thread_finished"] = False
            target = Path(value["transport_result"]["path"])
            target.write_text(json.dumps(transport))
            value["transport_result"] = reference(target)
        elif change == "unknown_create":
            value["create_result_unknown"] = True
        else:
            value["returncode"] = None
        path.write_text(json.dumps(value))
    assert wrapper.trustworthy_cleanup(request) is False
    assert Path(recovery.load(claim_ref)["lease"]).exists()
    assert not wrapper.proof_root.exists()
