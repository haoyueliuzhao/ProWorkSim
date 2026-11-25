"""Exercise mutation, ordering, observer and deployment boundaries on real frozen receipts."""

from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_organization_contract_v239 import PLAN, frozen
from proworksim import software_organization_contract_v239 as model
from proworksim.storage import read_json


def rejected(fn):
    try:
        fn()
    except ValueError:
        return True
    raise AssertionError("Unsafe transition accepted")


def main():
    rows = read_json(PLAN / "panel.json")
    replay = []
    for row in rows:
        tasks = model.state(row)
        actions = [k for k in tasks if model.ready(tasks, k)]
        if not actions:
            raise ValueError("No executable action")
        native = []
        for key in model.options(row):
            p = model.make_patch(row, key)
            assert model.apply_patch(row, p) == model.change_plan(row, key)[0]
            native.append(key)
        replay.append(dict(id=row["id"], native_targets_reconstructed=native, ready=actions))
    r = next(r for r in rows if r.get("source_id") == "s03")
    a = "work_root/complete_package"
    d = dict(
        choice="K",
        immediate=a,
        current_obligations=[a],
        added_product="none",
        reconsider_after="completion receipt",
    )
    plan = model.compile_decision(r, d)
    assert model.dispatch(r, plan, r["graph"], a)["actor"] == "member_001"
    changed = deepcopy(r)
    changed["evidence"]["E1"]["final_version"]["version_id"] = "v999"
    p = model.make_patch(r, "K")
    gap = rows[-1]
    fail = next(r for r in rows if r.get("source_id") == "s01")
    dx = dict(
        d,
        choice="D1",
        immediate="work_root/diagnose_failure",
        current_obligations=["work_root/diagnose_failure"],
        added_product="independent_diagnosis",
    )
    activated = model.compile_decision(fail, dx)
    assert (
        model.dispatch(
            fail, activated, model.apply_patch(fail, activated["patch"]), dx["immediate"]
        )["actor"]
        == "member_002"
    )
    negative = dict(
        stale_patch=rejected(lambda: model.apply_patch(r, {**p, "base_graph_version": "stale"})),
        add_worker=rejected(
            lambda: model.apply_patch(r, {**p, "operations": [["D0", "ADD_MEMBER", "member_003"]]})
        ),
        premature_review=rejected(
            lambda: model.dispatch(r, plan, r["graph"], "work_root/independent_review")
        ),
        stale_receipt=rejected(lambda: model.dispatch(changed, plan, r["graph"], a)),
        unactivated_patch=rejected(
            lambda: model.dispatch(fail, activated, fail["graph"], dx["immediate"])
        ),
        missing_evidence=rejected(
            lambda: model.compile_decision(gap, dict(dx, immediate="work_root/gather_evidence"))
        ),
    )
    frozen(
        "cpu-replay.json",
        dict(rows=replay, controls=negative, patched_diagnostician="member_002", provider_calls=0),
    )


if __name__ == "__main__":
    main()
