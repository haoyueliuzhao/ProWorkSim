"""Preserve r2 CPU and existing-record evidence without new world/model work."""
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TOOL = ROOT / "tools/analyze_passive_capture_v203_2_1_r2.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    spec = importlib.util.spec_from_file_location("r2_readonly_evidence", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sdk = ROOT / "runs/software-benchmark-v203-2-1/sdk-controls-r1/normal"
    episode_paths = [ROOT / f"runs/software-benchmark-v203-2-1/passive-pilot12-r1/episodes/{index}/result.json"
                     for index in (2032100, 2032101)]
    frozen = [ROOT / "tools/analyze_passive_capture_v203_2_1.py",
              ROOT / "src/proworksim/software_observer_views_v203_2_1.py",
              sdk / "model-ledger/ledger.json", sdk / "primary/boundary.json",
              sdk / "runtime/experience.jsonl", sdk / "model-ledger/passive-observer/events.sqlite",
              *episode_paths]
    before = {str(path.relative_to(ROOT)): sha(path) for path in frozen}
    ledger = json.loads((sdk / "model-ledger/ledger.json").read_bytes())
    report = module.analyze_capture(sdk, ledger["slot_id"])
    assert report["integrity"]["status"] == "PARTIAL"
    assert report["reconciliation"]["primary_calls"] == 17
    assert report["reconciliation"]["primary_action_receipts_match"]
    assert report["reconciliation"]["opportunities_match"]
    assert report["accepted_requests"] == []
    save("existing-sdk-normal-final.json", report)
    failures = []
    for path in episode_paths:
        original = json.loads(path.read_bytes())
        result = module.analyze_capture(None, original["slot_id"], generation_result=original)
        assert result["execution_state"] == "NOT_STARTED" and result["integrity"]["status"] == "PARTIAL"
        assert result["issues"][0]["original_error"] == original["error"]
        failures.append({"primary_result": str(path.relative_to(ROOT)), "analysis": result})
    save("existing-precontroller-failures.json", failures)
    after = {str(path.relative_to(ROOT)): sha(path) for path in frozen}
    assert before == after
    suites = ET.parse(OUT / "pytest-junit.xml").getroot().findall("testsuite")
    tests = {key: sum(int(suite.get(key, "0")) for suite in suites)
             for key in ("tests", "failures", "errors", "skipped")}
    assert tests == {"tests": 5, "failures": 0, "errors": 0, "skipped": 0}
    paths = [TOOL, ROOT / "tests/test_passive_capture_analysis_v203_2_1_r2.py",
             *[OUT / name for name in ("generate_evidence.py", "README.md", "pytest-junit.xml",
                                      "existing-sdk-normal-final.json", "existing-precontroller-failures.json")]]
    save("summary.json", {
        "schema": "passive-analysis-controls-v203.2.1-r2", "pytest": tests,
        "existing_sdk_primary_calls": 17, "existing_sdk_opportunities": 16,
        "existing_sdk_status": report["integrity"]["status"], "precontroller_failure_count": len(failures),
        "new_model_requests": 0, "world_actions_replayed": 0, "docker_or_services": 0,
        "frozen_sources_and_existing_inputs_unchanged": True, "existing_source_sha256": before,
        "source_and_evidence_sha256": {str(path.relative_to(ROOT)): sha(path) for path in paths},
    })
    print(json.dumps({"pytest": tests, "sdk_status": report["integrity"]["status"], "precontroller": len(failures)}))


if __name__ == "__main__":
    main()
