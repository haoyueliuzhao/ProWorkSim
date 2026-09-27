"""Explicit unknown-preserving revision; no GPU work or old score changes."""

import copy
from pathlib import Path

import pytest

from proworksim.harness_admission import VERSION_017, body_hash, validate_h1_launch
from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v016 import validate_original_s1
from scripts.build_harness_study_v017 import build_protocol
from test_harness_admission_v016 import admission_fixture
from test_candidate_selection_v015 import save
from scripts.build_harness_study_v016 import read, ref


def test_revised_gate_preserves_unknowns_and_requires_actual_capacity(tmp_path):
    _, kwargs, admission, path, report, s1report, _ = admission_fixture(tmp_path)
    supervisor = read(admission["original_s1_supervisor"]["path"])
    protocols = {}
    for job in supervisor["config"]["candidates"]:
        screen = read(job["screen_protocol"])
        protocol = build_protocol(screen)
        assert len(protocol["windows"]) == 4
        assert sum(len(w["slots"]) for w in protocol["windows"]) == 24
        assert all(w["mode"] == "evaluate" for w in protocol["windows"])
        assert protocol["recipe"]["max_length"] == 16384
        protocols[job["name"]] = protocol
    partial = next(r for r in report["runs"] if r["candidate_id"] == "qwen38-27b")
    partial["progress"]["counts"].update(closed_known=22, closed_unknown=14)
    source = next(j for j in supervisor["config"]["candidates"] if j["name"] == "qwen38-27b")
    with pytest.raises(ValueError, match="explicit new-protocol"):
        validate_original_s1(read(source["screen_protocol"]), source["screen_protocol"], report)
    kept = validate_original_s1(
        read(source["screen_protocol"]),
        source["screen_protocol"],
        report,
        allow_closed_unknown=True,
    )
    assert kept["unknown_scores_preserved"] == 14
    save(s1report, report)
    admission.update(
        version=VERSION_017,
        original_s1_completion_rule="all_attempts_closed_unknown_scores_preserved",
        original_s1_report=ref(s1report),
        protocol_body_sha256={c: body_hash(p) for c, p in protocols.items()},
        harness_identity=protocols["qwen35-9b"]["harness_identity"]["openhands_v16"],
    )
    admission["H0"]["target_harness_identity"] = admission["harness_identity"]
    for name in ("scripts/build_harness_study_v017.py", "src/proworksim/candidate_runtime_v017.py"):
        file = kwargs["source_root"] / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# fixture only\n")
        admission["source_files"][name] = digest(file.read_bytes())
    admission["capacity"] = {}
    for job in supervisor["config"]["candidates"]:
        c = job["name"]
        file = tmp_path / f"{c}-capacity.json"
        save(
            file,
            {
                "status": "passed",
                "http_status": 200,
                "source_unchanged": True,
                "source_before": kwargs["source_identity"],
                "devices": 2 if c == "qwen35-9b" else 4,
                "optimizer_steps": 0,
                "world_actions": 0,
                "profile": {"candidate_id": job["candidate"]},
                "actor_identity": {
                    "base_manifest_sha256": admission["weight_manifests"][c]["sha256"]
                },
            },
        )
        admission["capacity"][c] = ref(file)
    save(path, admission)
    protocol = protocols["qwen35-9b"]
    protocol["launch_gate"] = {"version": VERSION_017, "state": "admitted", "admission": ref(path)}
    result = validate_h1_launch(protocol, **kwargs)
    assert result["original_unknown_scores_preserved"]["qwen38-27b"] == 14
    broken = copy.deepcopy(admission)
    broken.pop("capacity")
    save(path, broken)
    protocol["launch_gate"]["admission"] = ref(path)
    with pytest.raises(ValueError, match="bounded actual capacity"):
        validate_h1_launch(protocol, **kwargs)
    assert partial["progress"]["counts"]["closed_unknown"] == 14
    assert json_bytes(report) == Path(s1report).read_bytes()
