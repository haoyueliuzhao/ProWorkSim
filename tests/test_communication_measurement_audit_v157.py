import importlib.util
import json
from pathlib import Path
import sqlite3

from proworksim import software_input_provenance_v156 as p


def test_streaming_audit_compares_independent_ledger_and_exposes_tampering(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "audit_v157", Path(__file__).parents[1]/"tools/audit_communication_measurement_v157.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = p.SourceFragment("Base/Template", "template", "template-event", "system")
    identity = {"request_id": "request1", "episode_id": "team1", "member_id": "member_001",
                "decision_id": "decision1", "attempt_id": "request1", "model_alias": "deepseek-flash",
                "request_time": "2026-11-08T00:00:00Z", "usage_id": "compressor",
                "logical_id": "logical1", "physical_attempt_index": 1, "condition": "C1"}
    built = p.build_request(p.annotate_tree({"model": "deepseek-flash", "messages": [
        {"role": "user", "content": "fixed test payload"}]}, template), identity, template_source=template)
    capture = p.persist_request(tmp_path/"captures", built)
    folder = Path(capture["payload"]["path"]).parent
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
             "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20}
    body = {"id": "response1", "model": "deepseek-flash", "usage": usage}
    response = p.capture_response(built, body, outcome="success", http_status=200)

    def write(name, value):
        path = folder/name
        path.write_text(json.dumps(value))
        return module.reference(path)

    receipt = {"request_id": "request1", "request_capture": capture, "response_metadata": response,
               "response_metadata_ref": write("response-metadata.json", response),
               "response_original_ref": write("response-original.json", body)}
    write("physical-receipt.json", receipt)
    ledger = tmp_path/"ledger.sqlite"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE requests(request_id TEXT,slot_id TEXT,member_id TEXT,condition TEXT,"
                   "status TEXT,usage_json TEXT,reserved_utc TEXT,request_sha256 TEXT,usage_id TEXT,"
                   "logical_id TEXT,attempt_index INTEGER)")
        db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   ("request1", "team1", "member_001", "C1", "settled", json.dumps(usage), "now",
                    built.manifest["payload_sha256"], "compressor", "logical1", 1))
    report = module.audit(ledger, [tmp_path/"captures"], len, "CPU_character_fixture",
                          mechanism_gates=dict.fromkeys(("G0-4", "G0-5", "G0-6"), True))
    assert report["reconciliation"]["known_actual_total_tokens"] == 110
    assert report["reconciliation"]["cached_input_tokens_known"] == 80
    assert report["API_usage_by_purpose"]["compressor"]["total_tokens"] == 110
    assert report["gates"]["G0-1"] and not report["gates"]["G0-2-provider-exact"]
    (folder/"payload.json").write_bytes(b"tampered")
    broken = module.audit(ledger, [tmp_path/"captures"], len, "CPU_character_fixture")
    assert not broken["gates"]["G0-1"]
    assert broken["issues"][0]["kind"] == "capture_integrity"
