"""Archive-only SDK primary evidence: exact recovery and fail-closed controls."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive_fixture(tmp_path, *, missing_member=False, duplicate_member=False, wrong_response=False):
    fixture = load(ROOT / "tests/test_passive_capture_analysis_v203_2_1_r2.py", "prior_cpu_fixture")
    controller, physical_host = fixture.no_artifact_controller(tmp_path)
    host = controller.parent
    path = controller / "managed-runtime/experience.jsonl"
    original = path.read_bytes()
    if wrong_response:
        rows = [json.loads(line) for line in original.splitlines()]
        rows[0]["payload"]["response"]["id"] = "wrong-provider-response"
        original = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo("output/managed-world/unrelated.bin")
        info.size = 1024
        archive.addfile(info, io.BytesIO(b"x" * 1024))
        if not missing_member:
            for _ in range(2 if duplicate_member else 1):
                info = tarfile.TarInfo("output/managed-runtime/experience.jsonl")
                info.size = len(original)
                archive.addfile(info, io.BytesIO(original))
    blob = host / "controller-output.tar.gz"
    blob.write_bytes(gzip.compress(raw.getvalue(), mtime=0))

    def reference(path):
        value = path.read_bytes()
        return {"path": str(path), "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}

    def save(path, value):
        path.write_text(json.dumps(value))
        return reference(path)

    raw_sha = hashlib.sha256(raw.getvalue()).hexdigest()
    transfer = {
        "transfer": {"bytes": len(raw.getvalue()), "stream_sha256": raw_sha},
        "relocation": {"host_prefix": str(controller), "container_prefix": "/pws/output",
                       "archive_only_prefixes": ["managed-world", "managed-runtime"]},
        "archive_storage": {"version": "v064-lossless-transport-storage-r1", "encoding": "gzip",
                            "round_trip_verified": True, "blob": reference(blob),
                            "decompressed_bytes": len(raw.getvalue()), "decompressed_sha256": raw_sha},
    }
    primary_result = {"slot_id": "E", "controller_result": reference(controller / "controller-result.json"),
                      "controller_output_transfer": save(host / "controller-output-transfer.json", transfer)}
    save(host / "result.json", primary_result)
    path.unlink()
    return controller, physical_host, blob, transfer, primary_result, save


def analyzer():
    return load(ROOT / "tools/analyze_passive_capture_v203_2_1_r4.py", "archive_analyzer_r4")


def test_verified_original_archive_recovers_sdk_decision_and_control_receipt(tmp_path):
    controller, host, blob, *_ = archive_fixture(tmp_path)
    paths = [blob, controller / "controller-result.json", controller / "model-ledger/ledger.json"]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    report = analyzer().analyze_capture(controller, "E", host)
    assert report["schema"] == "passive-capture-analysis-v203.2.1-r4"
    assert report["integrity"]["status"] == "COMPLETE"
    assert report["reconciliation"]["independent_runtime_trace_closed"]
    assert report["reconciliation"]["primary_action_receipts_match"]
    assert report["accepted_requests"][0]["decision_id"] == "sdk-d1"
    assert report["source_files"][str(blob)]["full_decompressed_stream_verified"]
    assert not (controller / "managed-runtime/experience.jsonl").exists()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


@pytest.mark.parametrize("mode", ["missing_member", "duplicate_member", "wrong_response"])
def test_missing_ambiguous_or_misattributed_primary_is_not_filled(tmp_path, mode):
    controller, host, *_ = archive_fixture(tmp_path, **{mode: True})
    report = analyzer().analyze_capture(controller, "E", host)
    assert report["integrity"]["status"] != "COMPLETE"
    assert report["integrity"]["dimensions"]["requests"]["status"] == "PARTIAL"
    assert report["accepted_requests"][0]["decision_id"] is None


@pytest.mark.parametrize("mode", ["blob_changed", "raw_digest_wrong", "different_controller"])
def test_archive_and_full_raw_stream_binding_are_mandatory(tmp_path, mode):
    controller, host, blob, transfer, primary, save = archive_fixture(tmp_path)
    if mode == "blob_changed":
        blob.write_bytes(blob.read_bytes() + b"changed")
    elif mode == "raw_digest_wrong":
        transfer["archive_storage"]["decompressed_sha256"] = "0" * 64
        transfer["transfer"]["stream_sha256"] = "0" * 64
    else:
        transfer["relocation"]["host_prefix"] = str(tmp_path / "other-controller")
    if mode != "blob_changed":
        primary["controller_output_transfer"] = save(controller.parent / "controller-output-transfer.json", transfer)
        save(controller.parent / "result.json", primary)
    report = analyzer().analyze_capture(controller, "E", host)
    assert report["integrity"]["status"] != "COMPLETE"
    assert any(issue["kind"] == "invalid_primary_runtime_trace" for issue in report["issues"])
    assert report["accepted_requests"][0]["decision_id"] is None
