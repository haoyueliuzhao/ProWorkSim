"""Prepare label/outcome-blinded fidelity packets; never claim reviews occurred."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference, write_new

SEED = "communication-v157-fidelity-20261108-before-model-results"
CRITICAL_RULE = "handoff_or_published_artifact_reference_or_test_risk_unknown_claim"


def sample(events):
    """All critical handoffs + ceil(25%) ordinary per condition, score-independent."""
    selected, ordinary = [], defaultdict(list)
    for row in events:
        if row["critical"]:
            selected.append(row)
        else:
            ordinary[row["condition"]].append(row)
    for rows in ordinary.values():
        rows.sort(key=lambda r: hashlib.sha256((SEED+r["source_id"]).encode()).hexdigest())
        selected.extend(rows[:math.ceil(len(rows)/4)])
    return sorted(selected, key=lambda r: hashlib.sha256(("order:"+SEED+r["source_id"]).encode()).hexdigest())


def prepare(roots, output):
    all_rows, seen = [], set()
    for root in roots:
        for path in sorted(Path(root).rglob("communication/events.jsonl")):
            events = [json.loads(line) for line in path.read_text().splitlines() if line]
            published = {e["sequence"]: e for e in events if e["kind"] == "published"}
            for event in events:
                if event["kind"] != "representation_prepared":
                    continue
                ref = event["L0"]
                key = (ref["source_id"], ref["recipient"])
                if key in seen:
                    raise ValueError("A communication was rendered twice for the same receiver")
                seen.add(key)
                file = path.parent/"sources"/(hashlib.sha256(ref["source_id"].encode()).hexdigest()
                                               +"-"+ref["version_hash"]+".json")
                source = json.loads(file.read_bytes())
                if reference(file)["sha256"] != ref["version_hash"]:
                    raise ValueError("Immutable communication original differs from the rendered version")
                origin = published[event["sequence"]]
                critical = (origin.get("event_kind") == "handoff"
                    or bool(source["metadata"].get("artifact_refs"))
                    or any(f["field"] in {"test_status", "risk", "unknown"} for f in source["facts"]))
                all_rows.append({"condition": event["condition"], "source_id": ref["source_id"],
                    "recipient": ref["recipient"], "critical": critical, "source": source,
                    "rendered": event, "evidence": {"events": reference(path), "source": reference(file)}})
    selected = sample(all_rows)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    packets, mapping = [], []
    for index, row in enumerate(selected, 1):
        event, source, audit_id = row["rendered"], row["source"], f"review-{index:04d}"
        rendered = event.get("L1", source["raw_text"][:500])
        packet = {"audit_id": audit_id, "original_published_text": source["raw_text"],
            "receiver_default_text": rendered, "source_facts": source["facts"],
            "critical_fact_truth_not_assumed": True,
            "version_metadata": source["metadata"].get("artifact_version"),
            "original_retrieval_available": True,
            "review": {"key_facts_retained": None, "wrong_claims": None,
                       "version_reference_correct": None, "risk_omissions": None,
                       "notes": None, "reviewer": None, "reviewed": False}}
        packets.append(packet)
        mapping.append({"audit_id": audit_id, **{k: row[k] for k in
            ("condition", "source_id", "recipient", "critical", "evidence")}})
    write_new(output/"reviewer-A.json", {"packets": packets, "reviews_completed": 0})
    write_new(output/"reviewer-B.json", {"packets": packets, "reviews_completed": 0})
    private = write_new(output/"administrative-mapping-not-for-reviewers.json", {"rows": mapping})
    return write_new(output/"manifest.json", {"version": "v157-fidelity-sample-r1",
        "seed": SEED, "critical_rule": CRITICAL_RULE, "all_communications": len(all_rows),
        "sampled": len(selected), "critical_total": sum(r["critical"] for r in all_rows),
        "ordinary_sampling": "ceil(25pct)_within_each_condition", "reviews_completed": 0,
        "condition_labels_and_outcomes_omitted": True,
        "format_may_reveal_treatment_blinding_not_guaranteed": True,
        "hidden_grading_results_read": False, "administrative_mapping": private})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.output), ensure_ascii=False))
