"""Evidence-bound auxiliary review records; no classifier or runtime intervention."""
from collections import Counter

STATUSES = {"PRESENT", "ABSENT", "UNKNOWN"}
DECISIONS = {"NO_CHANGE", "ABSTAIN", "INTERVENE"}
AXES = ("dependency", "unmet_need", "misalignment", "decision")
DIMENSIONS = ("technical", "information", "organization", "resource")


def validate_annotation(row, window):
    """Validate identity/time/claim boundaries, not the semantic truth of a label."""
    if row.get("window_id") != window["window_id"]:
        raise ValueError("Window identity mismatch")
    if row.get("reviewer_kind") not in {"independent_ai_auxiliary", "independent_human"}:
        raise ValueError("Declare reviewer provenance")
    if row.get("reviewer_kind") == "independent_ai_auxiliary" and row.get("human_gold") is not False:
        raise ValueError("AI auxiliary judgments cannot be human gold")
    if not row.get("reviewer_id") or not row.get("rationale"):
        raise ValueError("Reviewer and rationale are required")
    if any(row.get(axis) not in STATUSES for axis in AXES[:3]):
        raise ValueError("D, N and M require separate three-state labels")
    if row.get("decision") not in DECISIONS:
        raise ValueError("Invalid decision")
    if row["decision"] == "NO_CHANGE" and row["misalignment"] != "ABSENT":
        raise ValueError("Evidence-insufficient judgments must not become negative labels")
    if row["decision"] == "INTERVENE":
        if row["misalignment"] != "PRESENT" or row["unmet_need"] != "PRESENT":
            raise ValueError("A dependency alone cannot justify organizational intervention")
        if not row.get("intervention_reason"):
            raise ValueError("Explain why normal coordination is insufficient")
    if set(row.get("issues", {})) != set(DIMENSIONS):
        raise ValueError("Keep technical, information, organizational and resource issues separate")
    if any(not isinstance(row["issues"][axis], list) for axis in DIMENSIONS):
        raise ValueError("Issue dimensions must be lists")
    confidence = row.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("Confidence must be a declared, uncalibrated 0..1 judgment")
    cutoff = window["cutoff"]["sequence"]
    if row.get("cutoff_sequence") != cutoff:
        raise ValueError("Cutoff mismatch")
    for name in ("evidence_for", "evidence_against"):
        if not isinstance(row.get(name), list):
            raise ValueError("Keep support and counterevidence separately")
        for ref in row[name]:
            if (type(ref.get("sequence")) is not int or not 0 < ref["sequence"] <= cutoff
                    or not ref.get("reason")):
                raise ValueError("Evidence must precede cutoff and have a reason")
    if not row["evidence_for"]:
        raise ValueError("Even abstention must cite the observable evidence boundary")
    return {"schema_valid": True, "semantic_truth_verified": False,
            "runtime_actions": 0, "human_gold": row.get("human_gold") is True}


def agreement(left, right):
    """Descriptive same-window agreement; neither adjudication nor accuracy."""
    a, b = {r["window_id"]: r for r in left}, {r["window_id"]: r for r in right}
    if len(a) != len(left) or len(b) != len(right) or set(a) != set(b) or not a:
        raise ValueError("Exactly one label from each reviewer per identical window")
    result = {}
    for axis in AXES:
        ca, cb = Counter(a[k][axis] for k in a), Counter(b[k][axis] for k in a)
        n = len(a)
        same = sum(a[k][axis] == b[k][axis] for k in a)
        po = same / n
        pe = sum(ca[label] * cb[label] for label in set(ca) | set(cb)) / (n * n)
        result[axis] = {"n": n, "agreements": same, "agreement": po,
                        "cohen_kappa": (po - pe) / (1 - pe) if pe < 1 else None,
                        "left": dict(ca), "right": dict(cb)}
    result["disagreement_ids"] = sorted(k for k in a if any(a[k][axis] != b[k][axis] for axis in AXES))
    result["independent_task_count"] = None
    result["not_detector_accuracy_or_human_reference"] = True
    return result
