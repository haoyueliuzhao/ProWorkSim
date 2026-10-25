"""Pure file controls for a narrow release; no resource launch or host changes."""
import copy
import json

import pytest

from proworksim import software_benchmark_dispatch_v058 as dispatch
from proworksim import software_benchmark_shared_server_hold_v057 as original_hold


@pytest.fixture
def authorization(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for name in dispatch.SOURCE_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic sealed source\n")
    hold = root / "config/v057-shared-server-hold.json"
    hold.write_text(json.dumps({"version": original_hold.VERSION, "hold": True,
                               "automatic_release": False, "release_authorization": None}))
    path = root / "config/v058-offline-rescore-authorization.json"
    monkeypatch.setattr(dispatch, "ROOT", root)
    monkeypatch.setattr(dispatch, "AUTHORIZATION_FILE", path)
    monkeypatch.setattr(original_hold, "HOLD_FILE", hold)
    value = {"version": dispatch.VERSION, "status": "approved", "automatic_release": False,
             "explicit_rootful_container_authorization": "Synthetic CPU control only; not real authorization",
             "tasks": sorted(dispatch.TASKS), "operations": sorted(dispatch.OPERATIONS),
             "constraints": copy.deepcopy(dispatch.EXPECTED_CONSTRAINTS),
             "sources": dispatch.source_manifest()}
    return path, value, hold


def write(path, value):
    path.write_text(json.dumps(value))


def test_missing_pending_and_invalid_authorization_deny_even_with_environment_override(authorization, monkeypatch):
    path, value, _ = authorization
    monkeypatch.setenv("PROWORKSIM_IGNORE_HOLD", "1")
    monkeypatch.setenv("PROWORKSIM_V058_APPROVED", "true")
    for text in (None, "not json", "[]", json.dumps(value | {"status": "pending"}),
                 json.dumps(value | {"explicit_rootful_container_authorization": None})):
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text)
        with pytest.raises(original_hold.SharedServerHold):
            dispatch.require_v058_dispatch_allowed("v058.admission.prepare")


def test_reviewed_authorization_only_admits_exact_operations_and_tasks(authorization):
    path, value, _ = authorization
    write(path, value)
    for operation in dispatch.BATCH_OPERATIONS:
        assert dispatch.require_v058_dispatch_allowed(operation) == value
    for operation in dispatch.TASK_OPERATIONS:
        for task in dispatch.TASKS:
            assert dispatch.require_v058_dispatch_allowed(operation, task) == value
        for task in (None, "psf__requests-1766", "psf__requests-1921", "other"):
            with pytest.raises(dispatch.ScopedDispatchDenied):
                dispatch.require_v058_dispatch_allowed(operation, task)
    for operation in ("scorer.score_request", "v057.scorer.score_request", "new_v057_nat", "v058.model.run"):
        with pytest.raises(dispatch.ScopedDispatchDenied):
            dispatch.require_v058_dispatch_allowed(operation, "psf__requests-2931")
    with pytest.raises(original_hold.SharedServerHold):
        original_hold.require_experiment_dispatch_allowed("new_v057_nat")


def test_widened_constraints_or_source_change_revokes_authorization(authorization):
    path, value, _ = authorization
    for key, wrong in (("network_mode", "host"), ("host_mounts", True),
                       ("daemon_start_or_restart", True), ("cap_add", ["NET_ADMIN", "SYS_ADMIN"]),
                       ("concurrency", 3), ("per_container_memory_bytes", 32 * 1024**3),
                       ("model_calls", False)):
        changed = copy.deepcopy(value)
        changed["constraints"][key] = wrong
        write(path, changed)
        with pytest.raises(dispatch.ScopedDispatchDenied, match="constraints"):
            dispatch.require_v058_dispatch_allowed("v058.rescore.run")
    for changed in (value | {"tasks": sorted(dispatch.TASKS) + ["psf__requests-1766"]},
                    value | {"operations": sorted(dispatch.OPERATIONS) + ["new_v057_nat"]},
                    value | {"automatic_release": True}, value | {"sources": value["sources"][:-1]}):
        write(path, changed)
        with pytest.raises(dispatch.ScopedDispatchDenied):
            dispatch.require_v058_dispatch_allowed("v058.rescore.run")
    write(path, value)
    (dispatch.ROOT / dispatch.SOURCE_PATHS[1]).write_text("changed provider\n")
    with pytest.raises(dispatch.ScopedDispatchDenied, match="source binding"):
        dispatch.require_v058_dispatch_allowed("v058.rescore.run")


def test_scoped_release_cannot_replace_the_global_hold(authorization):
    path, value, hold = authorization
    write(path, value)
    for state in ({"version": original_hold.VERSION, "hold": False, "automatic_release": False,
                   "release_authorization": "Synthetic broad release must not pass"},
                  {"version": original_hold.VERSION, "hold": True, "automatic_release": True},
                  {"version": "invalid", "hold": True}):
        write(hold, state)
        # Updating the source seal alone must not make an altered global hold acceptable.
        write(path, value | {"sources": dispatch.source_manifest()})
        with pytest.raises(dispatch.ScopedDispatchDenied, match="incident-wide hold"):
            dispatch.require_v058_dispatch_allowed("v058.admission.execute")


def test_instance_resolver_runs_only_after_sealed_approval_and_cannot_widen_tasks(authorization):
    path, value, _ = authorization
    calls = []

    def resolve(task):
        calls.append(task)
        return task

    write(path, value | {"status": "pending"})
    with pytest.raises(dispatch.ScopedDispatchDenied, match="pending"):
        dispatch.require_v058_dispatch_allowed("v058.admission.worker", lambda: resolve("psf__requests-2931"))
    assert calls == []
    write(path, value | {"sources": []})
    with pytest.raises(dispatch.ScopedDispatchDenied, match="source binding"):
        dispatch.require_v058_dispatch_allowed("v058.admission.worker", lambda: resolve("psf__requests-2931"))
    assert calls == []
    write(path, value)
    assert dispatch.require_v058_dispatch_allowed(
        "v058.admission.worker", lambda: resolve("psf__requests-2931")) == value
    for task in ("psf__requests-1766", "psf__requests-1921", None, ["psf__requests-2931"]):
        with pytest.raises(dispatch.ScopedDispatchDenied, match="allowed instance"):
            dispatch.require_v058_dispatch_allowed("v058.admission.worker", lambda task=task: resolve(task))
    assert calls[0] == "psf__requests-2931" and len(calls) == 5
