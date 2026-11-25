"""Freeze the three-graph study, separate CPU fixtures, and four same-boundary admission checks."""

from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_scoped_obligations_v239_3 as prior
from proworksim import software_three_graph_v240 as policy
from proworksim.software_context_panel_v231 import DESIGN, PairedLedger
from proworksim.storage import read_json

ROOT = prior.prior.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v240/three-graphs-r1"
RUN = ROOT / "runs/software-benchmark-v240/three-graphs-r1"
MAIN = prior.GROUPS[0][1]
EXTRA = prior.GROUPS[1][1]


def freeze(name, data):
    p = PLAN / name
    if p.exists() and read_json(p) != data:
        raise ValueError(f"Frozen {name} differs")
    prior.first.save(p, data)


def sources():
    return read_json(MAIN / "panel.json") + [
        next(r for r in read_json(EXTRA / "additional-states.json") if r["id"] == "x04")
    ]


def reference_table(rows):
    refs = {r["id"]: r for p in [MAIN, EXTRA] for r in read_json(p / "agreed-reference.json")}
    # Operational probes chosen before any call; readiness of a stale proof is distinct
    # from the readiness of running a new check. The probed node denotes the latter.
    anchors = {
        "q01": ("verify_integrated_version", "SATISFIED", "NOT_APPLICABLE"),
        "q02": ("verify_integrated_version", "UNSATISFIED", "BLOCKED"),
        "q03": ("repair_target", "UNSATISFIED", "BLOCKED"),
        "q04": ("dependency/one_mask/ADOPT_UPSTREAM_ARTIFACT", "UNSATISFIED", "READY"),
        "q05": ("continue_progress", "UNSATISFIED", "READY"),
        "q06": ("pkg_parallel/verify_integrated_version", "STALE", "READY"),
        "q07": ("diagnose_failure", "UNSATISFIED", "READY"),
        "q08": ("repair_target", "UNSATISFIED", "BLOCKED"),
        "q09": ("verify_integrated_version", "SATISFIED", "NOT_APPLICABLE"),
        "q10": ("independent_review", "UNSATISFIED", "READY"),
        "q11": ("independent_review", "UNSATISFIED", "BLOCKED"),
        "q12": ("continue_progress", "UNSATISFIED", "READY"),
        "q13": ("resolve_conflict", "UNSATISFIED", "READY"),
        "q14": ("dependency/pkg_text_api/EXECUTE_UPSTREAM_WORK", "UNKNOWN", "CONDITIONAL"),
        "x04": ("dependency/codegen_unused_args/PROCEED_DOWNSTREAM", "UNKNOWN", "BLOCKED"),
        "gap": ("gather_evidence", "UNSATISFIED", "READY"),
    }
    table = {}
    for r in rows:
        sid = r["id"]
        key, completion, readiness = anchors[sid]
        if sid != "q06":
            key = r["targets"][0] + "/" + key
        ref = deepcopy(
            refs.get(
                sid,
                dict(
                    actions=["gather_evidence"],
                    obligations=[["gather_evidence"]],
                    choices=["KEEP", "ABSTAIN"],
                ),
            )
        )
        ref.update(
            probe_id=key,
            completion=completion,
            readiness=readiness,
            category=r["reference_type"],
            instance=r["instance"],
        )
        if sid in ("q14", "x04"):
            ref["historical_actions"] = ref["actions"]
            ref["actions"] = ["gather_evidence"]
            ref["reference_amendment"] = (
                "No artifact reference: first check status or inspect artifact under the new audit. No change to historical scores."
            )
        sets = [set(s) for s in ref["obligations"]]
        ref["consensus_due"] = sorted(set.intersection(*sets))
        table[sid] = ref
    return table


def controls(rows, refs):
    t = {r["id"]: r for r in rows}

    def rt(row):
        return policy.build(row)[1:]

    gap = deepcopy(t["gap"])
    next(iter(gap["evidence"].values()))["passed"] = False
    n, menu = rt(gap)
    assert all(
        v["action"] == "gather_evidence" and v["option"] in ("WAIT", "K") for v in menu.values()
    )
    r = t["q14"]
    p, original, menu = policy.build(r)
    e = p["dependencies"][0]
    assert e["artifact_state"] == "unknown"
    tested = {}
    for state in ("unknown", "absent", "present", "validated", "adopted"):
        s = deepcopy(r)
        if state != "unknown":
            s["evidence"]["inspection"] = dict(
                operation="dependency_artifact_observation",
                accepted=True,
                observer=s["observer"],
                downstream=e["consumer"],
                upstream=e["producer"],
                edge_version=e["edge_version"],
                artifact_state=state,
                artifact_id="object-at-v2" if state != "absent" else None,
                valid_for_edge=state in ("validated", "adopted"),
                consumer=s["graph"]["work"][e["consumer"]]["owner"],
            )
        proj, _, choices = policy.build(s)
        actions = sorted({v["dependency_action"] for v in choices.values()})
        assert actions == sorted(policy.DEP_READY[state])
        assert proj["dependencies"][0]["completion_record"] == "missing_or_stale"
        tested[state] = actions
    s["evidence"]["inspection"]["edge_version"] = "older"
    assert policy.project_graph(s)["dependencies"][0]["artifact_state"] == "unknown"
    r = t["q10"]
    n, _ = rt(r)
    assert (
        n["work_root/complete_package"]["completion"] == "SATISFIED"
        and n["work_root/independent_review"]["readiness"] == "READY"
    )
    s = deepcopy(r)
    end = list(s["evidence"].values())[-1]
    end["ready"] = True
    end["packages"][0]["missing"] = []
    n, _ = rt(s)
    assert (
        n["work_root/submit"]["completion"] == "UNSATISFIED"
        and n["work_root/submit"]["readiness"] == "READY"
    )
    g = r["graph"]
    large = policy.membership_patch(g, "ADD_MEMBER", "member_003", fixed_size=False)
    back = policy.membership_patch(
        large, "RETIRE_MEMBER", "member_003", fixed_size=False, successor="member_001"
    )
    assert (
        back["members"] == g["members"]
        and back["work"] == g["work"]
        and "member_003" in back["retired_members"]
    )
    try:
        policy.membership_patch(g, "ADD_MEMBER", "member_003")
    except ValueError:
        pass
    else:
        raise AssertionError("Fixed team grew")
    for row in rows:
        _, n, choices = policy.build(row)
        a = refs[row["id"]]
        assert a["probe_id"] in n
        for c in choices.values():
            assert n[c["immediate"]]["readiness"] == "READY"
    return dict(
        dependency_states=tested,
        unexecuted_failure="gather evidence",
        complete_package_without_review="review remains ready",
        correct_fixed_tree_without_submission="submission remains owed",
        stale_inspection_ignored=True,
        membership_roundtrip=True,
        fixed_size_enforced=True,
        online_calls=0,
    )


def preflight(rows):
    states = read_json(DESIGN)["states"]
    table = {r["id"]: r for r in rows}
    roster = []
    for sid, index in [("q07", 1), ("q03", 0), ("q14", None), ("q11", 2)]:
        r = table[sid]
        prov = r["provenance"]
        ok = False
        if index is not None:
            state = states[index]
            proof = read_json(ROOT / state["source_prefix"] / "checkpoint/manifest.json")
            menu = read_json(ROOT / prov["registered_menu"])
            menu = menu.get("menu", menu)
            ok = (
                proof["identity"] == prov["checkpoint"] == state["checkpoint"]
                and state["shared_prefix_usage"] == 5_000_000 - r["available_tokens"]
                and menu["graph"] == r["graph"]
                and menu["options"] == r["options"]
                and "K" in menu["options"]
                and len(policy.old.options(r)) > 1
            )
        roster.append(
            dict(
                id=sid,
                instance=r["instance"],
                index=index,
                checkpoint=prov.get("checkpoint"),
                eligible=ok,
                initial_budget=r["available_tokens"],
                pair_hold_nanoyuan=2 * r["available_tokens"] * 8000,
                status="eligible" if ok else "no matching checkpoint or eligible menu",
            )
        )
    return roster


if __name__ == "__main__":
    rows = sources()
    refs = reference_table(rows)
    freeze("references.json", refs)
    freeze("cpu-controls.json", controls(rows, refs))
    freeze("worker-preflight.json", preflight(rows))
