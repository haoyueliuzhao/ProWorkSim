"""Enroll only immutable, event-time checkpoints; use ordinary Worker runs for both arms."""

from pathlib import Path
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_multitype_worker_v242 as previous
from inventory_multitype_v242 import ROOT, read_json, save
from proworksim import software_event_orders_v243 as orders
from proworksim import software_event_harness_v243 as capture
from proworksim.organization_harness import run_worker_fragment
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim import software_sdk_resume_v203_3_4 as resume

PLAN = ROOT / "artifacts/software-benchmark-v243/event-pairs-r1"
RUN = ROOT / "runs/software-benchmark-v243/event-pairs-r1"
CASE = "Django-15916"
NS = "v243"


def register():
    old = previous.prior
    (row,) = [r for r in old.sources() if r["instance"] == "django__django-15916"]
    probe = read_json(old.PREFLIGHT / "references.json")[row["id"]]["probe_id"]
    row = {**row, "probe_id": probe}
    reg = row["provenance"]
    prefix = (ROOT / reg["source"]).parent
    proof = read_json(prefix / "checkpoint/manifest.json")
    limits = row["available_tokens"]
    raw = read_json(prefix / "observations.json")[-1]
    choice = read_json(prefix / "candidate-bank.json")["menu"]
    assert row["graph"] == choice["graph"] and row["options"] == choice["options"]
    assert raw["outcome"]["response"]["command_id"] == reg["commands"][-1]
    assert proof["identity"] == reg["checkpoint"] and proof["prefix_tokens"] + limits == 5000000
    assert orders.orders(row) and raw["ordinal"] == reg["ordinals"][-1]
    task = next(
        t
        for t in read_json(ROOT / "artifacts/software-benchmark-v229/design-r1/panel.json")["rows"]
        if t["instance_id"] == row["instance"]
    )
    # Read original saved decision/attempt counters, where the v033 budget stores consumed counts.
    before = next(
        x["payload"]["team_budget"]
        for x in (
            json.loads(s)
            for s in (prefix / "runtime/experience.jsonl").open()
            if "organization_work_opportunity_v049" in s
        )
        if x["kind"] == "organization_work_opportunity_v049"
        and x["payload"].get("phase") == "after"
        and x["payload"]["team_budget"]["available_tokens"] == limits
    )
    capacity = capture.work_budget(
        "A4", limits, before["remaining_attempts"], before["remaining_decisions"]
    )
    assert capacity["enough"]
    item = dict(
        case=CASE,
        instance=row["instance"],
        kind="A4",
        row=row,
        task=task,
        configuration=task["configuration"],
        initial_budget=limits,
        pair_hold_nanoyuan=2 * limits * 8000,
        checkpoint=proof["identity"],
        score_script=task["scorer_script"],
        score_index=task["source_index"],
        state=dict(
            case=CASE,
            source_prefix=str(prefix.relative_to(ROOT)),
            checkpoint=proof["identity"],
            shared_prefix_usage=proof["prefix_tokens"],
        ),
    )
    spec = previous.spec_for(item)
    spec.update(
        protocol="v243 same-state OSA/KEEP; one live OSA call inside the shared 5M envelope, fixed two members, exact code and legal candidate grading. Fresh version-bound D4 handoff, D5 review dispatch, D6 integration and associated D7 opportunity reservation. Explicit abstention. Passive capture on both ordinary Worker continuations; descendant states identified as dependent. No C/N update or forced CHANGE.",
        targets=capture.GOALS,
        priority=capture.PRIORITY,
        opening_available=68661986640,
        cohort="supplementary A4; historical development checkpoint, no independent A2/A1 sites available",
        resources=capacity,
        orders=orders.orders(row),
    )
    spec["files"].extend(
        reference(f) for f in (Path(__file__), Path(orders.__file__), Path(capture.__file__))
    )
    previous.freeze(PLAN / CASE / "protocol.json", spec)
    print("Admitted protocol", row["id"], limits, item["pair_hold_nanoyuan"], capacity["required"])


def branch(item, arm, out):
    module = previous.prior.paired.episode_module
    source = ROOT / item["state"]["source_prefix"]
    history = read_json(source / "observations.json")

    class Bound(orders.Execution):
        record = item["row"]

    def fragment(prepared, rt, *, on_opportunity=None):
        return run_worker_fragment(
            prepared,
            rt,
            folder=out / "passive-captures",
            history=history,
            source="paired-" + arm,
            on_opportunity=on_opportunity,
            native_run=module.native.run_fragment,
        )

    native = SimpleNamespace(**{**vars(module.native), "run_fragment": fragment})
    clone_function(
        module.episode,
        {
            **module.episode.__globals__,
            "RUN": RUN,
            "DESIGN": out.parent / "design.json",
            "panel_row": lambda _: item["task"],
            "native": native,
            "OrganizationExecution": Bound,
        },
    )(0, arm, out, False, slot_namespace=NS, expected_case=item["case"])


if __name__ == "__main__":
    if "--register" in sys.argv:
        register()
    else:
        clone_function(
            previous.main,
            {
                **previous.main.__globals__,
                "PLAN": PLAN,
                "RUN": RUN,
                "NS": NS,
                "__file__": __file__,
                "run_branch": branch,
            },
        )()
