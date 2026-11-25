"""Exercise the revised managed world on authentic saved worlds, then freeze six old checkpoints."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_midtask_panel_v244 as check
import run_fair_pairs_v245 as panel
from proworksim.storage import read_json, digest
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_performance_v214 import BundleCache
from proworksim.software_graph_controller_v228 import PROJECT
from proworksim.work_interface import ToolRejection

P = panel.prior
World = panel.fair.FairWorld


def saved(index, arm):
    w = World.__new__(World)
    w.store = check.ReadOnlyStore(P.RUN / str(index) / arm / "prepared/world")
    w.state = w.store.load()
    w.bundle_cache = BundleCache()
    w._operation_context = {"operation_id": "offline-control"}
    return w


def controls():
    w = saved(6, "KEEP")
    tid = "fix_sliced_inverse"
    pkg = w.dynamic()["work"][tid]
    c = pkg["completion"]
    pkg["completion"] = None
    pkg["reviewer"] = None
    assert w._action_work_readiness(c["author"], PROJECT, tid)["ready"]
    done = w._action_complete_work(c["author"], PROJECT, tid, c["patch_id"])
    item = next(
        p
        for p in w._action_delivery_checklist("member_001", PROJECT)["packages"]
        if p["task_id"] == tid
    )
    assert not item["missing"] and done["identity"] == c["identity"]
    code = dict(
        task=tid,
        patch=c["patch_id"],
        author=c["author"],
        test=done["test_sequence"],
        missing=item["missing"],
    )

    w = saved(12, "OSA")
    tid = "pkg_return_type_evidence"
    pkg = w.dynamic()["work"][tid]
    c = pkg["completion"]
    e = w.dynamic()["evidence"][c["evidence_id"]]
    pkg["reviewer"] = None
    pkg["completion"] = None
    n = len(w._software()["patches"])
    ev = w._action_complete_evidence(
        c["author"], PROJECT, tid, e["requirements"], e["owner_test"]["sequence"], e["reason"]
    )
    assert (
        not ev["new_code_patch_created"]
        and len(w._software()["patches"]) == n
        and ev["identity"] == c["identity"]
    )

    w = saved(4, "OSA")
    conflict = w._conflicts("member_001")
    assert conflict
    try:
        w._action_submit_integration("member_001", PROJECT)
    except ToolRejection as exc:
        assert exc.rejection["code"] == "unresolved_integration_conflict"
    else:
        raise AssertionError("Conflicted final version accepted")

    # Substitute an actual different revision of the package author's workspace, in memory.
    w = saved(6, "KEEP")
    pkg = w.dynamic()["work"]["fix_sliced_inverse"]
    c = pkg["completion"]
    assert w._completion_current("fix_sliced_inverse")
    native = w._bundle

    def changed(member, **kwargs):
        if member == c["author"] and not kwargs:
            return native(member, baseline=True)
        return native(member, **kwargs)

    w._bundle = changed
    assert not w._completion_current("fix_sliced_inverse")
    item = next(
        p
        for p in w._action_delivery_checklist("member_001", PROJECT)["packages"]
        if p["task_id"] == "fix_sliced_inverse"
    )
    assert "reopen_stale_completion" in item["missing"]

    # Force a genuine two-author risk condition by naming the other active member on the second leaf.
    w = saved(6, "KEEP")
    tid = "verify_sliced_api"
    pkg = w.dynamic()["work"][tid]
    other = w.dynamic()["work"]["fix_sliced_inverse"]
    other["authors"] = ["member_002"]
    pkg["authors"] = ["member_001"]
    assert w._review_needed(tid)
    try:
        w._tool_project_action(
            "member_001",
            PROJECT,
            "assign_verification",
            dict(task_id=tid, reviewer="member_001", reason="control"),
        )
    except ToolRejection as exc:
        assert exc.rejection["code"] == "dynamic_self_review"
    else:
        raise AssertionError("Author approved for independent role")
    assigned = w._tool_project_action(
        "member_001",
        PROJECT,
        "assign_verification",
        dict(task_id=tid, reviewer="member_002", reason="required independent review"),
    )
    assert assigned["reviewer"] == "member_002" and not assigned["automatic_review"]
    return dict(
        code_without_reviewer=code,
        evidence_without_new_patch=dict(
            id=ev["evidence_id"], scope=ev["requirements"], test=ev["owner_test"]["sequence"]
        ),
        conflict_blocked=conflict,
        version_change_reopens_obligation=item["missing"],
        same_managed_assignment=dict(assigned=assigned["reviewer"], self_review_rejected=True),
        external_calls=0,
    )


def main():
    gate = controls()
    old = read_json(P.PLAN / "roster.json")["roster"]
    ids = {c["index"]: c for c in old}
    roster = [ids[i] for i in (2, 6, 10, 8, 12, 0)]
    panel.freeze(panel.PLAN / "cpu-controls.json", gate)
    panel.freeze(
        panel.PLAN / "roster.json",
        dict(
            roster=roster,
            source=reference(P.PLAN / "roster.json"),
            strata={
                "previous_change": [2, 8, 12],
                "same_outcomes_no_change": [6, 0],
                "rejected": [10],
            },
            wave_sizes=[4, 2],
        ),
    )
    (panel.RUN / "tmp").mkdir(parents=True, exist_ok=True)
    decision = clone_function(
        P.decision,
        {**P.decision.__globals__, "PLAN": panel.PLAN, "Execution": panel.fair.Execution},
    )
    verify = clone_function(
        check.check,
        {**check.check.__globals__, "ReviewWorld": World, "RUN": panel.RUN, "decision": decision},
    )
    tok = P.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = OfficialDeepSeekCounter(tok, manifest_sha256=digest(tok.read_bytes()))
    rows = [verify(c, counter) for c in roster]
    panel.freeze(panel.PLAN / "decision-preflight.json", dict(rows=rows, provider_calls=0))
    panel.freeze(
        panel.PLAN / "protocol.json",
        dict(
            roster=reference(panel.PLAN / "roster.json"),
            cpu=reference(panel.PLAN / "cpu-controls.json"),
            preflight=reference(panel.PLAN / "decision-preflight.json"),
            files=[
                reference(f)
                for f in (
                    Path(panel.__file__),
                    Path(panel.fair.__file__),
                    Path(P.__file__),
                    Path(P.ordinary.__file__),
                    Path(__file__),
                    P.ROOT / "tools/score_project_relations_v217_1.py",
                )
            ],
            cap_yuan=150,
            prior_account_used=False,
            maximum_pairs=6,
            logical_tokens_per_arm=5000000,
            design="Retrospective regression from identical historical prefixes. First four pairs, budget/endpoint/technical review, then two. One paired worst-case hold before either arm. Shared fair world and permissions. No C/N update.",
        ),
    )
    print(gate, flush=True)


if __name__ == "__main__":
    main()
