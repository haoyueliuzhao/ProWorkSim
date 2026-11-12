"""Regenerate local CPU fixtures; no model, network, process or world operation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_observer_views_v203_2_1 import (  # noqa: E402
    AcceptedRequest, INTEGRITY_DIMENSIONS, ObserverViews, assess_integrity,
    make_evidence, validate_stage_assessment,
)


def save(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    (OUT / name).write_bytes(raw)
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def closed(source):
    return {"expected_sources": [source], "observed_sources": [source],
            "coverage_closed": True, "coverage_evidence": ["cpu-source-inventory"]}


def main():
    receipt = {"id": "CPU-SCRIPTED-NOT-A-PROVIDER-CALL", "usage": {
        "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
    }}
    save("cpu-response.json", receipt)
    views = ObserverViews("cpu-view-control", ["001", "002"])
    first = {"model": "cpu-scripted", "messages": [{"role": "user", "content": {
        "task_id": "T", "revision": 1, "actor": "001", "patch": {"id": "p1", "published": True},
        "visible_fragment": "Only this fragment is actually presented.",
    }}], "tools": [{"type": "function", "function": {"name": "offer_transfer"}}]}
    second = {"model": "cpu-scripted", "messages": [{"role": "user", "content": {
        "task_id": "T", "revision": 2, "actor": "001",
        "cpu_fixture_current_state": "Current producer artifact is required and unavailable.",
    }}], "tools": first["tools"]}
    for index, wire in enumerate((first, second), start=1):
        raw = save(f"cpu-request-{index}.json", wire)
        views.add_request(AcceptedRequest.from_bytes(
            episode_id="cpu-view-control", actor="001", request_id=f"q{index}",
            decision_id=f"d{index}", accepted_at=index * 10, raw_request=raw,
            request_sha256=sha(raw), provider_receipt=receipt, mode="cpu_scripted",
        ))
    views.add_global_event({"episode_id": "cpu-view-control", "event_id": "published",
                            "occurred_at": 5, "payload": {"published": True,
                            "full_source": "UNSEEN_FULL_SOURCE", "private": "OTHER_MEMBER_PRIVATE"}})
    views.add_global_event({"episode_id": "cpu-view-control", "event_id": "final",
                            "occurred_at": 30, "payload": {"official_result": "FUTURE_RESULT"}})
    early_view, late_view = views.member_view("001", 10), views.member_view("001", 20)
    row = {"episode_id": "cpu-view-control", "task_id": "T", "task_revision": 1,
           "phase": "T1", "actor": "001", "request_id": "q1", "at_time": 10,
           "operation": "offer_transfer", "layers": {"exposure": {
               "value": "EXPOSED", "evidence": [make_evidence(early_view, "/tools/0")],
           }}}
    early_assessment = validate_stage_assessment(row, early_view)
    later_ref = make_evidence(late_view, "/messages/0/content/cpu_fixture_current_state")
    late_assessment = validate_stage_assessment({
        **row, "task_revision": 2, "phase": "T5", "request_id": "q2", "at_time": 20,
        "dependency": "PRESENT", "dependency_evidence": [later_ref],
        "layers": {"exposure": {"value": "EXPOSED",
                                  "evidence": [make_evidence(late_view, "/tools/0")]}},
    }, late_view)
    dimensions = {name: closed(f"source-{name}") for name in INTEGRITY_DIMENSIONS}
    complete = assess_integrity("cpu-view-control", dimensions)
    missing = {**dimensions, "delivery": {"expected_sources": ["source-delivery"],
                                          "observed_sources": []}}
    partial = assess_integrity("cpu-view-control", missing)
    invalid = assess_integrity("cpu-view-control", dimensions,
                               fatal_errors=("CPU-injected-episode-integrity-failure",))
    assert complete["status"] == "COMPLETE" and partial["status"] == "PARTIAL"
    assert partial["dimensions"]["ownership"]["status"] == "COMPLETE"
    assert not partial["dimensions"]["delivery"]["absence_eligible"]
    assert invalid["status"] == "INVALID" and not invalid["analysis_dimensions"]
    visible = json.dumps(early_view.to_dict())
    assert all(secret not in visible for secret in ("UNSEEN_FULL_SOURCE", "OTHER_MEMBER_PRIVATE", "FUTURE_RESULT"))
    assert early_assessment["dependency"] == "UNKNOWN" and late_assessment["dependency"] == "PRESENT"
    assert late_assessment["misalignment"] == "UNKNOWN" and late_assessment["decision"] == "ABSTAIN"
    save("examples.json", {
        "evidence_mode": "cpu_scripted", "natural_task_material": False,
        "integrity": {"complete": complete, "missing_delivery": partial, "fatal": invalid},
        "member_at_10": early_view.to_dict(), "member_at_20": late_view.to_dict(),
        "global_at_10": views.global_view(10).to_dict(),
        "assessments": [early_assessment, late_assessment],
    })
    suites = ET.parse(OUT / "pytest-junit.xml").getroot().findall("testsuite")
    counts = {name: sum(int(suite.get(name, "0")) for suite in suites)
              for name in ("tests", "failures", "errors", "skipped")}
    assert counts["tests"] == 25 and not (counts["failures"] or counts["errors"] or counts["skipped"])
    paths = [ROOT / "src/proworksim/software_observer_views_v203_2_1.py",
             ROOT / "tests/test_observer_views_v203_2_1.py",
             ROOT / "tools/analyze_passive_capture_v203_2_1.py",
             *[OUT / name for name in ("generate_evidence.py", "README.md", "pytest-junit.xml",
                                      "cpu-request-1.json", "cpu-request-2.json", "cpu-response.json", "examples.json")]]
    summary = {
        "schema": "observer-view-controls-v203.2.1", "date": "2026-11-12",
        "evidence_mode": "cpu_scripted", "pytest": counts,
        "actual_model_requests": 0, "actual_api_tokens": 0, "actual_api_cash": 0,
        "world_actions": 0, "docker_or_services": 0,
        "judgment": "CPU_CONTRACT_CONTROLS_PASSED",
        "not_proven": ["real_transport_deployment", "production_durability",
                       "natural_dependency_accuracy", "organizational_intervention_benefit"],
        "source_and_evidence_sha256": {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in paths},
    }
    save("summary.json", summary)
    print(json.dumps({"summary": str((OUT / "summary.json").relative_to(ROOT)), "pytest": counts}))


if __name__ == "__main__":
    main()
