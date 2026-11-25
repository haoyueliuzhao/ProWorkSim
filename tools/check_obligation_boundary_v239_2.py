"""Verify separating a receipt gap from a scheduled successor on frozen and counterfactual evidence."""

from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_obligation_boundary_v239_2 import PLAN, freeze, policy, previous, read_json


def main():
    panel = read_json(previous.PLAN / "panel.json") + read_json(PLAN / "additional-states.json")
    rows = {r["id"]: r for r in panel}
    q = rows["q03"]
    tasks = policy.snapshot(q)
    assert tasks["work_root/repair_target"]["source"] == "observed_failing_target"
    assert tasks["work_root/verify_integrated_version"]["source"] == "workflow_successor"
    assert tasks["work_root/repair_target"]["status"] == "BLOCKED"
    x = rows["x01"]
    a = policy.snapshot(x)
    assert len({v["immediate"] for v in policy.routes(x, a).values()}) > 1
    assert any(
        k.endswith("/assign_verifier") and v["source"] == "explicit_contract_gap"
        for k, v in a.items()
    )
    x2 = deepcopy(x)
    last = list(x2["evidence"].values())[-1]
    last["public_test"]["source_reference"] = {"version_id": "other"}
    assert not any(t["source"] == "failed_shared_tree" for t in policy.snapshot(x2).values())
    checks = 0
    for r in panel:
        tasks = policy.snapshot(r)
        for k, v in policy.routes(r, tasks).items():
            assert policy.base.ready(tasks, v["immediate"])
            d = dict(
                route=k,
                current_obligations=[v["immediate"]],
                basis=[next(iter(r["evidence"]))],
                reason="CPU mechanism control",
                reconsider_after="new evidence",
            )
            c = policy.compile_decision(r, d)
            g = policy.base.apply_patch(r, c["patch"])
            assert policy.dispatch(r, c, g) == {s: v[s] for s in ("action", "actor", "package")}
            checks += 1
    assert all(
        v["option"] in ("K", "WAIT")
        for v in policy.routes(rows["gap"], policy.snapshot(rows["gap"])).values()
    )
    q14 = rows["q14"]
    src = previous.ROOT / q14["provenance"]["source"]
    restore = read_json(src.parent / "restore.json")
    earlier = read_json(src.parent.parent / "PREFIX/checkpoint/manifest.json")
    assert earlier["identity"] == restore["checkpoint_identity"]
    freeze(
        "cpu-controls.json",
        dict(
            routes_roundtripped=checks,
            sites=len(panel),
            checks=[
                "observed failure requires remediation while a future-version retest is conditional",
                "simultaneous qualifying package actions available",
                "missing verifier recorded",
                "stale nested public test excluded",
                "every exposed route dispatches authorized actor on matching graph",
                "no missing-evidence change",
            ],
            A2_restore=dict(
                site="q14",
                decision_ordinals=q14["provenance"]["ordinals"],
                branch_input_checkpoint=earlier["identity"],
                prefix_tokens=restore["prefix_tokens"],
                prefix_available=5000000 - restore["prefix_tokens"],
                decision_available=q14["available_tokens"],
                checkpoint_at_decision=q14["provenance"].get("checkpoint"),
            ),
            model_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
