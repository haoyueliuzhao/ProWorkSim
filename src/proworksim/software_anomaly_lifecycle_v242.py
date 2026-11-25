"""Post-decision anomaly tracking using public, version-bound evidence only."""

from pathlib import Path
from .storage import read_json
from .software_benchmark_candidates_v054 import checked

EDIT = {"replace_file", "write_file", "rename_file", "delete_file", "integrate_patch"}
TEST = {"run_tests", "run_patch_review_tests"}


def public_reports(folder):
    records = []
    for f in sorted((folder / "public-test-rpc").glob("*/response.json")):
        req = read_json(f.with_name("request.json"))
        r = read_json(f)
        if req.get("hidden_evaluation") or r.get("validation_status") != "verified":
            continue
        result = {}
        for s in (r.get("test_evidence") or {}).get("sessions", []):
            if s.get("root") is not True or s.get("partial") or not s.get("collection_complete"):
                continue
            for t in s.get("test_reports", []):
                if t.get("phase") == "call" and t.get("nodeid") and not t.get("wasxfail"):
                    result.setdefault(t["nodeid"], set()).add(t["outcome"])
        records.append((req, r, result))
    return records


def lifecycle(folder):
    d = read_json(folder / "decision.json")
    b = read_json(folder / "boundary.json")
    start = d["anomaly"]
    kind = start["anomaly_type"]
    subject = start["subject"]
    packages = set(start["affected_work"])
    observer = d["menu"]["evidence"][next(iter(d["menu"]["evidence"]))].get("actor")
    if not observer:
        observer = start["evidence_refs"][-1]["command_id"].split(":")[1]
    locked = read_json(
        checked(read_json(checked(read_json(folder / "candidate-lock.json")))["terminal_code"])
    )["source_reference"]
    receipts = public_reports(folder)
    history = [
        dict(state="DETECTED", ordinal=start["evidence_refs"][0]["opportunity"]),
        dict(state="ACTIVE", ordinal=d["original_ordinal"]),
    ]
    test_file = subject.split("::")[0]
    edited = set()
    last_match = None
    had_pass = False
    regressions = set(read_json(folder / "mechanism.json").get("regression_targets", []))
    usable = {}
    for offset, o in enumerate(b["outcomes"], 1):
        if o.get("worker_id") != observer:
            continue
        resp = o.get("response") or {}
        a = o.get("decision") or {}
        v = resp.get("result") or {}
        tool = a.get("action")
        if not resp.get("ok"):
            continue
        ref = (
            v.get("source_reference")
            or v.get("final_version")
            or ((v.get("final_identity") or {}).get("source_reference"))
        )
        if tool in EDIT:
            edited.update(v.get("paths", []))
            edited.update([a.get("arguments", {}).get("path")])
        label = None
        if (
            kind in ("A1", "A3")
            and tool in TEST
            and v.get("executed")
            and ref
            and ref.get("object_id") == locked.get("object_id")
        ):
            selected = (v.get("selection_normalization") or {}).get("executed")
            matches = [
                nodes
                for req, pub, nodes in receipts
                if req["actor_id"] == observer
                and req["source_reference"] == ref
                and req["public_test_selection"] == selected
                and pub.get("counts") == v.get("counts")
                and pub.get("passed") == v.get("passed")
            ]
            if not matches or any(z != matches[0] for z in matches):
                continue
            nodes = matches[0]
            out = nodes.get(subject)
            key = (ref["object_id"], ref["version_id"])
            usable.setdefault(key, set()).update(
                n for n, results in nodes.items() if results == {"passed"}
            )
            if out == {"failed"}:
                label = "REOPENED" if had_pass else "ACTIVE"
            elif out == {"passed"}:
                had_pass = True
                label = (
                    "RESOLVED"
                    if ref == locked and test_file not in edited and regressions <= usable[key]
                    else "MITIGATED"
                )
            elif (
                last_match
                and last_match[0] == ref
                and had_pass
                and ref == locked
                and test_file not in edited
                and {subject, *regressions} <= usable[key]
            ):
                label = "RESOLVED"
        elif kind == "A4" and tool == "delivery_readiness":
            work = {w["task_id"]: w for w in (v.get("package_chain") or {}).get("packages", [])}
            if not packages <= work.keys() or not ref:
                continue
            still_missing = any(subject in work[p].get("missing", []) for p in packages)
            label = (
                ("REOPENED" if had_pass else "ACTIVE")
                if still_missing
                else ("RESOLVED" if ref == locked else "MITIGATED")
            )
            had_pass |= not still_missing
        elif kind == "A2" and tool == "work_readiness" and v.get("task_id") in packages:
            if any(g.get("task_id") == subject for g in v.get("gaps", [])):
                label = "REOPENED" if had_pass else "ACTIVE"
            elif v.get("ready") is True:
                label = "RESOLVED" if ref == locked else "MITIGATED"
                had_pass = True
        if label:
            history.append(
                dict(
                    state=label,
                    ordinal=d["original_ordinal"] + offset,
                    version=ref,
                    command=resp["command_id"],
                )
            )
            last_match = (ref, label)
    state = last_match[1] if last_match else "UNKNOWN"
    if last_match and last_match[0] and last_match[0] != locked and state in ("ACTIVE", "REOPENED"):
        state = "UNKNOWN"
    if history[-1]["state"] != state:
        history.append(dict(state=state, reason="No matching evidence for the locked version"))
    return dict(
        kind=kind,
        subject=subject,
        observer=observer,
        locked=locked,
        history=history,
        state=state,
        regression_controls=sorted(regressions),
        target_file_edited=test_file in edited,
        official_score_used=False,
    )
