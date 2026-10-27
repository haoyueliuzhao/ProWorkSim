import importlib.util
import io
import json
from pathlib import Path
import tarfile
import threading

import pytest

from proworksim import software_benchmark_scorer_v064 as scorer
from proworksim import software_benchmark_grading_environment_v064 as environment
from proworksim import software_benchmark_tcp_transport_v064 as transport
from proworksim.software_benchmark_archive_storage_v064 import compress_transport_archive
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grading_v064_test_module", ROOT / "tools/run_capability_grading_v064.py")
grading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grading)


def configure_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(scorer.policy, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(scorer.policy, "GRADING_ROOT", tmp_path / "grading")
    monkeypatch.setattr(scorer.policy, "PLAN_FILE", tmp_path / "plan.json")
    monkeypatch.setattr(scorer.policy, "COORDINATOR_RUN_ROOT", tmp_path / "coordinator")
    monkeypatch.setattr(grading, "RUN_ROOT", tmp_path / "coordinator")
    monkeypatch.setattr(scorer.policy, "cpu_set", lambda role, lane=0: ",".join(map(str, range(76 + 4 * lane, 80 + 4 * lane))))


def claim_fixture(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    folder = tmp_path / "grading/score-0"
    folder.mkdir(parents=True)
    plan = write_new(tmp_path / "plan.json", {"rows": []})
    request = {"directory": str(folder), "resource_key": "score-0", "plan": plan,
               "cpuset_cpus": None}
    request_ref = write_new(folder / "request.json", request)
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    claim = {"version": scorer.policy.VERSION, "key": "score-0", "plan": plan,
             "lane": 3, "spec": {"role": "score"}, "lease": str(claims / "active-grader-3.json")}
    claim_ref = write_new(claims / "score-0.json", claim)
    (claims / "active-grader-3.json").write_bytes(Path(claim_ref["path"]).read_bytes())
    write_new(folder / "capacity-claim.json", {"prepared_request": request_ref, "claim": claim_ref})
    return request, request_ref, claim_ref


def test_claimed_lane_controls_actual_affinity_and_released_claim_is_refused(tmp_path, monkeypatch):
    request, _, _ = claim_fixture(tmp_path, monkeypatch)
    resolved = scorer.resolve_execution_request(request)
    assert resolved["cpuset_cpus"] == "88,89,90,91"
    assert request["cpuset_cpus"] is None
    (tmp_path / "resource-claims/active-grader-3.json").unlink()
    with pytest.raises(ValueError, match="absent, released"):
        scorer.resolve_execution_request(request)


def test_cancellation_precedes_claim_and_failed_process_creation_releases_own_claim(tmp_path, monkeypatch):
    request, request_ref, claim_ref = claim_fixture(tmp_path, monkeypatch)
    folder = Path(request["directory"])
    # The coordinator is responsible for writing this sidecar after admission.
    (folder / "capacity-claim.json").unlink()
    monkeypatch.setattr(grading.policy, "require_v064_allowed", lambda *_: {})
    calls = []
    monkeypatch.setattr(grading.policy, "claim_resource", lambda key: calls.append(key) or claim_ref)
    monkeypatch.setattr(grading, "capacity_available", lambda: True)
    stopped = threading.Event()
    stopped.set()
    assert grading.run_request(request_ref, stopped)["status"] == "not_started_cancelled"
    assert calls == [] and not (folder / "started.json").exists()
    monkeypatch.setattr(grading.policy, "release_resource", lambda ref, **kw: calls.append((ref, kw)))
    monkeypatch.setattr(grading.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no child")))
    result = grading.run_request(request_ref)
    assert result["status"] == "technical_unknown" and result["returncode"] is None
    assert calls[0] == "score-0" and calls[-1] == (claim_ref, {"quiescent": True})
    proof = json.loads((folder / "quiescence.json").read_bytes())
    assert proof["quiescent"] is True and proof["owned_container_ids"] == []


def test_project_candidate_keeps_real_arm_and_fixed_endpoint_identity(tmp_path):
    patch = tmp_path / "candidate.patch"
    patch.write_text("original patch representation\n")
    config = {"slot_id": "v064:task:PROJECT:1", "instance_id": "task", "condition_id": "QWEN_PROJECT_B5000K",
              "seed": 1, "arm": "PROJECT"}
    value = {"version": "software-benchmark-native-closure-v054", "lock_before_grading": True,
             "endpoint": "terminal_code", "measurement_kind": "full_verified_comparison",
             "slot": config, "tree_sha256": "tree", "patch_receipt": {
                 "round_trip_verified": True, "utf8_strict": True, "candidate_content_changed": False,
                 "candidate_tree_sha256": "tree", "patch": reference(patch)}}
    ref = write_new(tmp_path / "lock.json", value)
    assert scorer._locked_candidate(ref, config, endpoint="terminal_code")["slot"]["arm"] == "PROJECT"
    with pytest.raises(ValueError, match="endpoint or new condition"):
        scorer._locked_candidate(ref, {**config, "arm": "REF"}, endpoint="terminal_code")
    with pytest.raises(ValueError, match="endpoint or new condition"):
        scorer._locked_candidate(ref, config, endpoint="last_legal_delivery")


def test_compressed_controller_members_bind_to_original_bytes_without_raw_tar(tmp_path):
    folder = tmp_path / "controller-output"
    folder.mkdir()
    child = folder / "controller-result.json"
    child.write_text('{"status":"closed"}\n')
    ref = reference(child)
    archive = tmp_path / "controller-output.tar"
    with tarfile.open(archive, "w") as stream:
        item = tarfile.TarInfo("output/controller-result.json")
        body = child.read_bytes()
        item.size = len(body)
        stream.addfile(item, io.BytesIO(body))
    storage = compress_transport_archive(archive, reference(archive), allowed_root=tmp_path)
    assert not archive.exists()
    scorer._archive_members_bind(storage, [ref], folder)
    child.write_text('{"status":"forged"}\n')
    with pytest.raises(ValueError, match="not unique or regular|differs from the original"):
        scorer._archive_members_bind(storage, [reference(child)], folder)


def test_same_tree_delivery_reuses_only_own_qualified_code_report(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    slot = "v064:fixture:QWEN_PROJECT_B5000K:1"
    config = write_new(tmp_path / "config.json", {"arm": "PROJECT", "instance_id": "fixture"})
    row = {"slot_index": 0, "slot_id": slot, "arm": "PROJECT", "instance_id": "fixture", "configuration": config}
    plan = write_new(tmp_path / "plan.json", {"rows": [row]})
    code = write_new(tmp_path / "code-lock.json", {"tree_sha256": "same", "patch_receipt": {"base_tree_sha256": "base"}})
    delivery = write_new(tmp_path / "delivery-lock.json", {"tree_sha256": "same", "patch_receipt": {"base_tree_sha256": "base"}})
    evidence = write_new(tmp_path / "evidence.json", {})
    result = write_new(tmp_path / "result.json", {"slot_id": slot, "candidate_lock": code,
        "delivery_candidate_lock": delivery, "delivery_evidence": evidence})
    monkeypatch.setattr(scorer, "_generation_result", lambda *args: None)
    monkeypatch.setattr(scorer, "validate_project_delivery", lambda *args: {"submitted": True, "same_tree": True})
    manifest = write_new(tmp_path / "manifest.json", {})
    monkeypatch.setattr(grading, "prepare_manifest", lambda: manifest)
    folder = tmp_path / "grading/score-0"
    folder.mkdir(parents=True)
    request = write_new(folder / "request.json", {"directory": str(folder), "resource_key": "score-0",
        "generation_result": result, "slot_id": slot, "candidate_lock": code})
    identity = write_new(folder / "identity.json", {"request": request, "candidate_lock": code,
        "configuration": config, "endpoint": "code", "plan": plan, "scorer_manifest": manifest})
    write_new(folder / "receipt.json", {"version": scorer.VERSION, "resource_key": "score-0", "slot_id": slot,
        "identity": identity, "status": "official_report", "resolved": True,
        "official_result": ["fixture", {"fixture": {"resolved": True, "patch_successfully_applied": True}}]})
    write_new(folder / "completion.json", {"returncode": 0})
    write_new(folder / "quiescence.json", {"resource_key": "score-0", "quiescent": True,
        "cleanup_errors": [], "create_result_unknown": False})
    value = grading.delivery_disposition(result, request)
    assert value["status"] == "same_tree_official_result_reused" and value["resolved"] is True
    assert value["scoring_request"] is None
    wrong = write_new(tmp_path / "other-request.json", {**json.loads(Path(request["path"]).read_bytes()), "slot_id": "other"})
    with pytest.raises(ValueError, match="this slot's exact"):
        grading.delivery_disposition(result, wrong)


def test_absent_legal_delivery_is_recorded_without_starting_scoring(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    config = write_new(tmp_path / "config.json", {"arm": "PROJECT"})
    row = {"slot_index": 0, "slot_id": "slot", "arm": "PROJECT", "instance_id": "task", "configuration": config}
    write_new(tmp_path / "plan.json", {"rows": [row]})
    evidence = write_new(tmp_path / "evidence.json", {})
    result = write_new(tmp_path / "result.json", {"slot_id": "slot", "delivery_evidence": evidence})
    monkeypatch.setattr(scorer, "_generation_result", lambda *args: None)
    monkeypatch.setattr(scorer, "validate_project_delivery", lambda *args: {"submitted": False, "same_tree": None})
    value = grading.delivery_disposition(result)
    assert value["status"] == "no_legal_delivery" and value["resolved"] is False
    assert value["scoring_request"] is None


def test_private_requests_capabilities_and_transport_bounds_remain_narrow():
    assert environment.capabilities("psf__requests-1766") == ["NET_ADMIN", "NET_BIND_SERVICE"]
    assert environment.capabilities("psf__requests-2931") == ["NET_ADMIN"]
    assert environment.capabilities("django__django-1") == []
    assert scorer.policy.CONSTRAINTS["maximum_real_tls_sessions"] == 40
    with pytest.raises(transport.RelayError):
        transport.Limits(max_connections=513).validate()
    with pytest.raises(transport.RelayError):
        transport.Limits(max_bytes=64 * 1024**2 + 1).validate()


def test_real_managed_delivery_schema_and_streamed_zstd_bind_both_tree_identities(tmp_path, monkeypatch):
    from proworksim.software_benchmark_project_closure_v064 import export_managed_closure
    from proworksim.software_benchmark_snapshot_recovery_v061 import export_utf8_patch
    from proworksim.software_benchmark_archive_storage_v064 import prepare_zstd_codec, export_compressed_stream
    fixture_spec = importlib.util.spec_from_file_location("managed_closure_cpu_fixture", ROOT / "tests/test_software_benchmark_managed_v064.py")
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture_module)
    configure_paths(tmp_path, monkeypatch)
    fixture_root = tmp_path / "world-fixture"
    fixture_root.mkdir()
    prepared, port, _, _ = fixture_module.fixture(fixture_root)
    for index, (name, arguments) in enumerate((
        ("write_file", {"path": "sample.py", "text": "value = 1\n"}),
        ("run_tests", {}), ("fix_patch", {"task_ids": [], "message": "tested"}),
        ("submit_integration", {"message": "submitted"}),
        ("write_file", {"path": "sample.py", "text": "value = 2\n"}),
    )):
        assert port.call(name, request_key=f"scoring-{index}", association={}, **arguments)["ok"] is True
    slot = "v064:fixture__aligned-064:QWEN_PROJECT_B7500K:1"
    folder = tmp_path / "episodes/0"
    output = folder / "controller-output"
    output.mkdir(parents=True)
    closure = export_managed_closure(prepared, output, slot_id=slot, sdk_closed=True)
    baseline = json.loads(Path(closure["baseline_snapshot"]["path"]).read_bytes())
    terminal = closure["terminal_bundle"]
    snapshot = json.loads(Path(closure["delivery_snapshot"]["path"]).read_bytes())
    baseline_ref = write_new(folder / "baseline-snapshot.json", baseline)
    config = {"slot_id": slot, "instance_id": "fixture__aligned-064", "condition_id": "QWEN_PROJECT_B7500K",
              "arm": "PROJECT", "seed": 1}
    plan = write_new(tmp_path / "plan.json", {})
    locks = {}
    for endpoint, bundle in (("terminal_code", terminal), ("last_legal_delivery", snapshot["candidate"])):
        candidate = write_new(folder / (endpoint + ".json"), bundle)
        patch = export_utf8_patch(baseline, bundle, folder / (endpoint + ".patch"))
        locks[endpoint] = write_new(folder / (endpoint + "-lock.json"), {
            "version": "software-benchmark-native-closure-v054", "lock_before_grading": True,
            "measurement_kind": "full_verified_comparison", "endpoint": endpoint,
            "slot": config, "baseline": baseline_ref, "candidate": candidate,
            "tree_sha256": patch["candidate_tree_sha256"], "patch_receipt": patch})
    child = write_new(output / "controller-result.json", {"status": "closed"})
    evidence_refs = [closure["delivery_evidence"], closure["delivery_snapshot"], child]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive_file:
        for ref in evidence_refs:
            path = Path(ref["path"])
            info = tarfile.TarInfo("output/" + path.relative_to(output).as_posix())
            body = path.read_bytes()
            info.size = len(body)
            archive_file.addfile(info, io.BytesIO(body))
    raw = buffer.getvalue()
    storage = export_compressed_stream([raw], folder / "controller-output.tar.zst", allowed_root=folder,
                                       codec_manifest=prepare_zstd_codec())
    claim = write_new(tmp_path / "controller-claim.json", {"plan": plan,
        "spec": {"role": "controller", "slot_id": slot}})
    transfer = write_new(folder / "controller-output-transfer.json", {
        "transfer": {"role": "controller", "container_path": "/pws/output", "container_id": "cpu-owned-fixture",
            "container_claim": claim, "stream_sha256": storage["decompressed_sha256"],
            "bytes": storage["decompressed_bytes"], "raw_archive_materialized": False},
        "archive_storage": storage, "relocation": {"container_prefix": "/pws/output",
            "host_prefix": str(output), "raw_json_references_rewritten": False}})
    writers = write_new(folder / "writers.json", {"all_quiet": True, "errors": [], "writers": [{
        "role": "controller", "claim": claim, "container_id": "cpu-owned-fixture",
        "state": {"Running": False, "Pid": 0}}]})
    result = {"delivery_evidence": closure["delivery_evidence"], "delivery_snapshot": closure["delivery_snapshot"],
        "project_baseline_snapshot": baseline_ref, "controller_result": child,
        "controller_output_transfer": transfer, "controller_exit_code": 0, "writer_quiescence": writers,
        "candidate_lock": locks["terminal_code"], "delivery_candidate_lock": locks["last_legal_delivery"]}
    proof = scorer.validate_project_delivery(result, config, folder)
    assert proof["legal_delivery_evidence"] is True and proof["same_tree"] is False
    assert proof["native_delivery_tree_sha256"] == json.loads(Path(locks["last_legal_delivery"]["path"]).read_bytes())["tree_sha256"]
    assert not list(folder.glob("*.tar"))
