"""Evidence-only successor measurement. Official grades are never an observer input."""

from .storage import read_json
from .software_benchmark_candidates_v054 import checked
from .software_anomaly_lifecycle_v242 import EDIT, TEST
from .software_anomaly_graph_v226 import DEPENDENCY, EDITS


def test_index(folder):
    public = []
    for f in sorted((folder / "public-test-rpc").glob("*/response.json")):
        req = read_json(f.with_name("request.json"))
        report = read_json(f)
        if req.get("hidden_evaluation") is not False or report.get("validation_status") not in (
            "verified",
            "failed",
        ):
            continue
        root = [
            s
            for s in (report.get("test_evidence") or {}).get("sessions", [])
            if s.get("root") is True
        ]
        if len(root) != 1 or root[0].get("partial") or not root[0].get("collection_complete"):
            continue
        cases = {}
        for entry in root[0].get("test_reports", []):
            if entry.get("phase") == "call" and entry.get("nodeid") and not entry.get("wasxfail"):
                cases.setdefault(entry["nodeid"], set()).add(entry["outcome"])
        public.append((req, report, cases))
    return public


def match_test(public, actor, result):
    if not result.get("executed") or type(result.get("passed")) is not bool:
        return {}
    selection = (result.get("selection_normalization") or {}).get("executed")
    found = [
        cases
        for q, r, cases in public
        if q["actor_id"] == actor
        and q["source_reference"] == result.get("source_reference")
        and q["public_test_selection"] == selection
        and r["counts"] == result.get("counts")
        and r["passed"] == result["passed"]
    ]
    return found[0] if found and all(x == found[0] for x in found) else {}


def evaluate(folder):
    d = read_json(folder / "decision.json")
    b = read_json(folder / "boundary.json")
    m = read_json(folder / "mechanism.json")
    node = d["anomaly"]
    kind = node["anomaly_type"]
    scope = set(node["affected_work"])
    subject = node["subject"]
    observer = node["evidence_refs"][-1]["command_id"].split(":")[1]
    lock = read_json(
        checked(read_json(checked(read_json(folder / "candidate-lock.json")))["terminal_code"])
    )
    final = lock["source_reference"]
    target = subject.split("::")[0]
    checks = set(m["regression_targets"])
    trail = [
        dict(state="DETECTED", ordinal=node["evidence_refs"][0]["opportunity"]),
        dict(state="ACTIVE", ordinal=d["original_ordinal"]),
    ]
    reports = test_index(folder)
    passes = {}
    edited = set()
    was_improved = False
    closures = {}
    reopens = set()
    test_products = set()
    duplicate_tests = 0
    executed_tests = 0
    first_observation = None
    last_ref = None
    reviews = {}
    handoffs = []
    for i, outcome in enumerate(b["outcomes"], d["original_ordinal"] + 1):
        actor = outcome.get("worker_id")
        resp = outcome.get("response") or {}
        a = outcome.get("decision") or {}
        v = resp.get("result") or {}
        cmd = resp.get("command_id")
        tool = a.get("action")
        args = a.get("arguments", {})
        if not resp.get("ok"):
            rejection = (resp.get("error") or {}).get("rejection") or {}
            readiness = (rejection.get("context") or {}).get("readiness") or {}
            if kind != "A2" or tool != "begin_work" or not readiness:
                continue
            v = readiness
        ref = (
            v.get("source_reference")
            or (v.get("identity") or {}).get("source_reference")
            or (v.get("final_identity") or {}).get("source_reference")
        )
        if tool in EDIT | EDITS:
            paths = set(v.get("paths", [])) | {
                args.get(k) for k in ("path", "old_path", "new_path")
            }
            if actor == observer:
                edited.update(paths)
        task = args.get("task_id") or v.get("task_id")
        if tool in ("complete_work", "complete_evidence") and task:
            closures[(task, v.get("event_sequence") or cmd)] = dict(
                version=ref, patch=v.get("patch_id"), ordinal=i, actor=actor
            )
        if tool == "reopen_work":
            candidates = [key for key in closures if key[0] == task]
            if candidates:
                reopens.add(candidates[-1])
        if (
            tool == "org_review_patch"
            and v.get("patch_id")
            and v.get("actor_id") == actor
            and v.get("author")
            and v["author"] != actor
        ):
            if v.get("decision") == "accept":
                reviews[v["patch_id"]] = v
            elif v.get("decision") == "request_changes":
                reviews.pop(v["patch_id"], None)
        if tool in (
            "handoff_patch",
            "integrate_patch",
            "adopt_evidence",
            "send_message",
            "read_work_event",
            "org_review_patch",
        ):
            handoffs.append(
                dict(
                    ordinal=i,
                    actor=actor,
                    tool=tool,
                    command=cmd,
                    patch=v.get("patch_id") or args.get("patch_id"),
                    task=task,
                    message=(args.get("body") or "").split(" ", 1)[0] or None,
                    version=ref,
                )
            )
        if tool in TEST and v.get("executed") and ref:
            key = (
                actor,
                ref["object_id"],
                ref["version_id"],
                str(sorted((v.get("selection_normalization") or {}).get("executed", {}).items())),
            )
            duplicate_tests += key in test_products
            executed_tests += 1
            test_products.add(key)
        if actor != observer:
            continue
        state = None
        if kind in ("A1", "A3") and tool in TEST and ref and ref["object_id"] == final["object_id"]:
            facts = match_test(reports, actor, v)
            key = (ref["object_id"], ref["version_id"])
            present = facts.get(subject)
            previously = passes.setdefault(key, set())
            previously.difference_update(n for n, vals in facts.items() if "failed" in vals)
            previously.update(n for n, vals in facts.items() if vals == {"passed"})
            if present == {"failed"}:
                state = "REOPENED" if was_improved else "ACTIVE"
            elif present == {"passed"} or (facts and subject in previously):
                state = (
                    "RESOLVED"
                    if ref == final and target not in edited and checks <= previously
                    else "MITIGATED"
                )
        if (
            kind == "A4"
            and tool == "org_review_patch"
            and scope <= set(v.get("task_revisions", {}))
        ):
            if ref and subject == "independent_current_review":
                if v.get("patch_id") in reviews:
                    state = "RESOLVED" if ref == final else "MITIGATED"
                elif (
                    v.get("decision") == "request_changes"
                    and v.get("actor_id") == actor
                    and v.get("author") not in (actor, None)
                ):
                    state = "REOPENED" if was_improved else "ACTIVE"
        if kind == "A4" and tool == "delivery_readiness" and ref:
            packages = {p["task_id"]: p for p in (v.get("package_chain") or {}).get("packages", [])}
            if scope <= packages.keys():
                missing = any(subject in packages[t].get("missing", []) for t in scope)
                state = (
                    ("REOPENED" if was_improved else "ACTIVE")
                    if missing
                    else ("RESOLVED" if ref == final else "MITIGATED")
                )
        if kind == "A2" and tool in ("work_readiness", "begin_work") and task in scope:
            if any(
                gap.get("kind") in DEPENDENCY
                and subject in (gap.get("task_id"), gap.get("patch_id"), gap.get("evidence_id"))
                for gap in v.get("gaps", [])
            ):
                state = "REOPENED" if was_improved else "ACTIVE"
            elif v.get("ready") is True and v.get("gaps") == []:
                state = "RESOLVED" if ref == final else "MITIGATED"
        if kind == "A3" and subject == "merge_conflict" and tool == "integrate_patch" and ref:
            if v.get("conflicts") or (v.get("conflict_count") or 0) > 0:
                state = "REOPENED" if was_improved else "ACTIVE"
        if (
            kind == "A3"
            and subject == "merge_conflict"
            and tool == "delivery_readiness"
            and v.get("ready_to_submit") is True
            and ref == final
        ):
            if (
                (v.get("final_test") or {}).get("passed") is True
                and v.get("current_fixed_patch_ids")
                and v.get("gaps") == []
                and checks
                and checks <= passes.get((ref["object_id"], ref["version_id"]), set())
            ):
                state = "RESOLVED"
        if state:
            trail.append(dict(state=state, ordinal=i, command=cmd, source_reference=ref))
            if first_observation is None:
                first_observation = i
            was_improved |= state in ("MITIGATED", "RESOLVED")
            last_ref = ref
    last = trail[-1]["state"]
    judged = first_observation is not None and last_ref == final
    endpoint = last if judged else "UNKNOWN"
    if endpoint != last:
        trail.append(
            dict(state=endpoint, reason="No matching process evidence on the locked final version")
        )
    ledger = []
    for (pkg, event), work in closures.items():
        ledger.append(
            dict(
                package=pkg,
                event=event,
                current=work["version"] == final,
                reopened=(pkg, event) in reopens,
                **work,
            )
        )
    return dict(
        endpoint=endpoint,
        last_observed_state=last if first_observation else None,
        trace=trail,
        first_evidence_after=None
        if first_observation is None
        else first_observation - d["original_ordinal"],
        observer=observer,
        target=subject,
        scope=sorted(scope),
        target_file_changed=target in edited,
        frozen_regressions=sorted(checks),
        official_grade_used=False,
        lock=final,
        closed_packages=ledger,
        reviews=[
            dict(
                patch=p,
                actor=r["actor_id"],
                task_revisions=r["task_revisions"],
                source_reference=r["identity"]["source_reference"],
            )
            for p, r in reviews.items()
        ],
        rework=dict(
            reopened=len(reopens),
            completed=len(closures),
            repeated_identical_tests=duplicate_tests,
            executed_tests=executed_tests,
        ),
        handoffs=handoffs,
    )
