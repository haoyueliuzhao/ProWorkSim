"""Narrow r2 adoption controls: immutable predecessors and no entered-slot replay."""
import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ref_resume_v056_r2", ROOT / "tools/resume_ref_budget_queue_v056_r2.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def state():
    slots = [{"slot_id": str(i), "instance_id": f"task-{i}", "condition_id": "REF_B0500K"} for i in range(4)]
    value = module.queue_api.initial_state({"path": "old-binding"}, slots)
    for index, status in enumerate(("closed", "deferred", "running")):
        value["rows"][index]["generation"].update(status=status, job_id=f"generation-{index}")
        value["rows"][index]["score"]["status"] = "not_applicable"
        value["jobs"][f"generation-{index}"] = {"kind": "generation", "slot_id": str(index),
            "status": "running" if status == "running" else "completed", "directory": f"old-root/job-{index}"}
    return value


def test_only_untouched_pending_rows_change_source_revision():
    old = state()
    before = copy.deepcopy(old)
    new, moved, retained = module.revised_state(old, {"path": "old"}, {"path": "new"}, claim_exists=lambda _: False)
    assert old == before
    assert moved == ["3"] and retained == ["0", "1", "2"]
    assert new["jobs"] == old["jobs"]
    assert [row["slot"] for row in new["rows"]] == [row["slot"] for row in old["rows"]]
    assert [row["generation"]["status"] for row in new["rows"]] == ["closed", "deferred", "running", "pending"]
    assert new["rows"][3]["execution_revision"] == module.REVISION
    assert all(row["execution_revision"] == module.OLD_REVISION for row in new["rows"][:3])


@pytest.mark.parametrize("prior_kind", ["claim", "job"])
def test_pending_with_prior_dispatch_evidence_cannot_be_replayed(prior_kind):
    old = state()
    if prior_kind == "job":
        old["jobs"]["uncertain-old"] = {"kind": "generation", "slot_id": "3"}
    with pytest.raises(ValueError, match="prior dispatch/claim"):
        module.revised_state(old, {}, {}, claim_exists=lambda _: prior_kind == "claim")


def test_changed_source_requires_exact_original_archive(tmp_path):
    source = tmp_path / "adapter.py"
    source.write_text("old implementation\n")
    old_ref = reference(source)
    old_manifest = write_new(tmp_path / "old-manifest.json", {"files": [old_ref]})
    snapshot = write_new(tmp_path / "archived-adapter.py", source.read_bytes())
    source.write_text("corrected implementation\n")
    new_ref = reference(source)
    new_manifest = write_new(tmp_path / "new-manifest.json", {"files": [new_ref]})
    old, new = {"frozen_sources": old_manifest}, {"frozen_sources": new_manifest}
    with pytest.raises(ValueError, match="lacks an exact archive"):
        module.source_revision_evidence(old, new, [])
    index = write_new(tmp_path / "index.json", {"copies": [{"original": old_ref, "snapshot": snapshot}]})
    result = module.source_revision_evidence(old, new, [index["path"]])
    assert result["changed_sources"] == [{"old": old_ref, "new": new_ref, "old_bytes_snapshot": snapshot}]


def test_inspection_reconciles_copy_without_writing_original_files(tmp_path):
    old = module.queue_api.initial_state({}, [{"slot_id": "one", "instance_id": "task", "condition_id": "REF_B0500K"}])
    folder = tmp_path / "job"
    folder.mkdir()
    job_ref = write_new(folder / "job.json", {"version": "synthetic"})
    write_new(folder / "completion.json", {"job": job_ref, "returncode": 75, "status": "process_exited"})
    write_new(folder / "result.json", {"slot_id": "one", "condition_id": "REF_B0500K",
        "status": "technical_unknown", "entered": False, "finally_stopped_scopes": []})
    old["jobs"]["generation-one"] = {"status": "running", "kind": "generation", "job": job_ref,
        "directory": str(folder), "intent_unix": 0, "payload": {"output": str(folder)},
        "slot_id": "one", "resident": "gpu0"}
    old["rows"][0]["generation"].update(status="running", job_id="generation-one")
    before = copy.deepcopy(old)
    state_path = write_new(tmp_path / "state.json", old)
    refreshed, events = module.refresh_copy(tmp_path, old)
    assert old == before and reference(tmp_path / "state.json") == state_path
    assert not (tmp_path / "status.json").exists() and not (tmp_path / "events.jsonl").exists()
    assert refreshed["rows"][0]["generation"]["status"] == "deferred"
    assert any(event["kind"] == "slot_deferred" for event in events)
