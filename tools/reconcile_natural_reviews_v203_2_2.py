"""Validate independently authored blind labels and retain disagreements.

No organizational labels are inferred here. Agreement is descriptive; final
records require an independently authored adjudication for every differing D/N/M
or action. AI records never constitute independent human confirmation.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_collaboration_audit_v203_2_2 import AXES, agreement, validate_annotation

BASE = ROOT / "artifacts/software-benchmark-v203-2-2/natural-audit-r1"
REV = ROOT / "artifacts/software-benchmark-v203-2-2/independent-review-r1"


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f"Refuse to silently replace sealed result: {path}")
    path.write_bytes(raw)


def jsonl(path, values):
    raw = "".join(json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n" for v in values).encode()
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f"Refuse to silently replace sealed result: {path}")
    path.write_bytes(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()
    windows = {w["window_id"]: w for w in rows(BASE / "decision_windows.jsonl")}
    assert len(windows) == 108
    REV.mkdir(parents=True, exist_ok=True)
    provenance = {}
    labels = {}
    for name in ("a", "b"):
        path = REV / f"reviewer-{name}.jsonl"
        records = rows(path)
        by_id = {r["window_id"]: r for r in records}
        if len(records) != 108 or set(by_id) != set(windows):
            raise ValueError("Review missing, duplicate, or outside frozen window set")
        for record in records:
            validate_annotation(record, windows[record["window_id"]])
            if record["reviewer_id"] != name.upper() or record["reviewer_kind"] != "independent_ai_auxiliary":
                raise ValueError("Reviewer identity/provenance differs")
        labels[name] = by_id
        provenance[name] = {"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes())}
    # Packet identities are the frozen input of the independent reviewers.
    for w in windows.values():
        if sha((BASE / w["packet_path"]).read_bytes()) != w["packet_sha256"]:
            raise ValueError("A blind packet changed after window freeze")
    metrics = agreement(list(labels["a"].values()), list(labels["b"].values()))
    metrics.update(review_sources=provenance, unique_tasks=len({w["task_id"] for w in windows.values()}),
                   human_gold=False, decision_windows=108, annotation_generation_by_this_script=False)
    dump(REV / "agreement.json", metrics)
    disagreements = [{"window_id": key, "packet_path": windows[key]["packet_path"],
                      "packet_sha256": windows[key]["packet_sha256"],
                      "reviewer_a": labels["a"][key], "reviewer_b": labels["b"][key]}
                     for key in metrics["disagreement_ids"]]
    jsonl(REV / "disagreements.jsonl", disagreements)
    jsonl(REV / "human-review-template.jsonl", [
        {"window_id": key, "packet_path": w["packet_path"], "packet_sha256": w["packet_sha256"],
         "cutoff_sequence": w["cutoff"]["sequence"], "reviewer_id": None,
         "dependency": None, "unmet_need": None, "misalignment": None, "decision": None,
         "supporting_evidence": [], "counterevidence": [], "confidence": None}
        for key, w in windows.items()])
    if not args.finalize:
        print(json.dumps({"windows":108, "disagreements":len(disagreements), "agreement": {k: metrics[k] for k in AXES}}, ensure_ascii=False))
        return
    adjudication = rows(REV / "adjudication.jsonl") if disagreements else []
    resolved = {r["window_id"]: r for r in adjudication}
    if len(resolved) != len(adjudication) or set(resolved) != set(metrics["disagreement_ids"]):
        raise ValueError("Every disagreement needs exactly one third-reviewer judgment")
    final = []
    for key, w in windows.items():
        record = dict(resolved[key] if key in resolved else labels["a"][key])
        validate_annotation(record, w)
        if key in resolved and (record["reviewer_id"] != "C" or record["reviewer_kind"] != "independent_ai_auxiliary"):
            raise ValueError("Adjudication provenance differs")
        record.update(task_id=w["task_id"], packet_sha256=w["packet_sha256"],
                      reconciliation="third_ai_adjudication" if key in resolved else "agreement_on_D_N_M_and_action_only",
                      original_reviews={name: labels[name][key] for name in ("a", "b")},
                      independent_human_confirmation=False, intervention_executed=False)
        final.append(record)
    jsonl(BASE / "mismatch_annotations.jsonl", final)
    result = {"windows": len(final), "unique_tasks": metrics["unique_tasks"], "adjudicated": len(adjudication),
              "labels": {axis: dict(Counter(r[axis] for r in final)) for axis in AXES},
              "task_ids_with_auxiliary_positive_windows": sorted({r["task_id"] for r in final if r["misalignment"] == "PRESENT"}),
              "task_ids_with_unknown_windows": sorted({r["task_id"] for r in final if r["misalignment"] == "UNKNOWN"}),
              "human_gold": False, "detector_accuracy": None, "v203_3_admission": "HOLD",
              "conditions": "Previously exposed tasks; correlated windows; only auxiliary AI references.",
              "sources": provenance, "final_sha256": sha((BASE / "mismatch_annotations.jsonl").read_bytes())}
    dump(REV / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
