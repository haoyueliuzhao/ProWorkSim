"""Compare old and revised handoff using the original OSA decision on an identical real state."""

from pathlib import Path
from types import SimpleNamespace
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as event
from proworksim import software_review_handoff_v243_1 as fix
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_fixed_organization_clone_v131 import clone_function as clone
from proworksim.storage import read_json

ROOT = event.ROOT
RUN = ROOT / "runs/software-benchmark-v243-1/review-handoff-r1"
PLAN = ROOT / "artifacts/software-benchmark-v243-1/review-handoff-r1"
CASE = event.CASE
NS = "v243.1-review"
ARMS = ("BASE", "FIX")


def register():
    parent = event.PLAN / CASE / "protocol.json"
    old = read_json(parent)
    bucket = event.RUN / CASE / "OSA/osa-api"
    (req,) = bucket.glob("*/request.json")
    resp = req.with_name("response.json")
    w = read_json(req)["payload"]["wire"]
    (item,) = old["roster"]
    assert w == json.loads(
        json.dumps(event.orders.wire(item["row"], event.orders.orders(item["row"])))
    )
    d = read_json(event.RUN / CASE / "OSA/decision.json")
    assert d["requested"] == "CHANGE" and d["proposal"]["work_order"] == "review:work_root"
    spec = dict(
        roster=[item],
        cap=old["cap"],
        block_hold=old["block_hold"],
        files=[
            *old["files"],
            reference(parent),
            reference(Path(__file__)),
            reference(Path(fix.__file__)),
            reference(req),
            reference(resp),
        ],
        controller_request=reference(req),
        controller_response=reference(resp),
        protocol="Independent implementation regression pair, identical A4 development checkpoint and historic D5/D7 decision replay. BASE v243 vs FIX version-aware review handoff. Preserve logical 2827 controller tokens per arm, no new paid controller request. Only fresh Worker charges; same tools, tests, 5M, scorer, state. Primary mechanism: stale review attempts, exact current formal verdict, owner notification, eventual correct delivery. Always score both arms. Not a new distinct site or test of anomaly classification.",
    )
    event.previous.freeze(PLAN / CASE / "protocol.json", spec)


def branch(item, arm, out):
    experiment = read_json(PLAN / CASE / "protocol.json")
    recorded = read_json(checked(experiment["controller_request"]))
    decision = read_json(checked(experiment["controller_response"]))
    module = event.previous.prior.paired.episode_module

    def replay(route, payload):
        if json.loads(json.dumps(payload["wire"])) != recorded["payload"]["wire"]:
            raise ValueError("Controller input changed")
        if route == "/tokenize":
            return recorded["count"]
        if route == "/chat/completions":
            return decision
        raise ValueError("Unknown controller replay route")

    def backend(folder, *args, **kwargs):
        if folder == out / "osa-api":
            return SimpleNamespace(post=replay)
        return module.Backend(folder, *args, **kwargs)

    episode = clone(module.episode, {**module.episode.__globals__, "Backend": backend})
    # The parent episode factory reads the function globals when it binds the local task.
    paired = SimpleNamespace(
        **{
            **vars(event.previous.prior.paired),
            "episode_module": SimpleNamespace(**{**vars(module), "episode": episode}),
        }
    )
    prior = SimpleNamespace(**{**vars(event.previous.prior), "paired": paired})
    previous = SimpleNamespace(**{**vars(event.previous), "prior": prior})
    return clone(
        event.branch,
        {
            **event.branch.__globals__,
            "RUN": RUN,
            "NS": NS,
            "orders": fix if arm == "FIX" else event.orders,
            "previous": previous,
        },
    )(item, arm, out)


def main():
    if "--register" in sys.argv:
        return register()
    pr = event.previous.prior
    reserve = clone(pr.paired.reserve, {**pr.paired.reserve.__globals__, "ARMS": ARMS})
    paired = SimpleNamespace(**{**vars(pr.paired), "reserve": reserve})
    mainfn = event.previous.main
    clone(
        mainfn,
        {
            **mainfn.__globals__,
            "PLAN": PLAN,
            "RUN": RUN,
            "NS": NS,
            "__file__": __file__,
            "run_branch": branch,
            "prior": SimpleNamespace(**{**vars(pr), "ARMS": ARMS, "paired": paired}),
        },
    )()


if __name__ == "__main__":
    main()
