"""Replay the already-visible successful test report before the rejected 003 call."""

from pathlib import Path
import json, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dynamic_panel_v248_2 as prior
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json

first = prior.first
RUN = prior.ROOT / "runs/software-benchmark-v248/dynamic-membership-r3"
PLAN = prior.ROOT / "artifacts/software-benchmark-v248/dynamic-membership-r3"
NS = "v248.3"
ARM = "O-DYNAMIC"
INDEX = 1


def slot(i, arm):
    return f"{NS}:{i}:{arm}"


def register():
    ref = prior.PLAN / "protocol.json"
    old = read_json(ref)
    case = next(r for r in old["rows"] if r["index"] == INDEX)
    recovery = next(r for r in old["recovery"] if r["arm"] == ARM)
    folder = first.RUN / "1/O-DYNAMIC/public-test-rpc/test-0001"
    first.freeze(
        PLAN / "protocol.json",
        dict(
            parent=first.old.reference(ref),
            recovery=[recovery],
            case=case,
            exact_test_request=first.old.reference(folder / "request.json"),
            exact_test_response=first.old.reference(folder / "response.json"),
            previous_replay=first.old.reference(prior.RUN / "1/O-DYNAMIC/replay.json"),
            source=first.old.reference(Path(__file__)),
            rule="Only the O-DYNAMIC branch. Check exact settled test identity except the branch-local deadline; independently execute it in the corrected container and compare result summary before returning its original complete response. All later model request wires still must match literally. No new model call until the originally interrupted 003 test is executed.",
        ),
    )


def generate(out, spec):
    expected = read_json(first.old.checked(spec["exact_test_request"]))
    reply = read_json(first.old.checked(spec["exact_test_response"]))

    class Actor(prior.Actor):
        def test(self, **kwargs):
            q = kwargs["request"]
            result = super().test(**kwargs)
            if q["call_index"] == expected["call_index"]:
                norm = lambda x: {k: v for k, v in x.items() if k != "hard_deadline_monotonic"}
                if norm(expected) != norm(q) or any(
                    result.get(k) != reply.get(k)
                    for k in (
                        "passed",
                        "validation_status",
                        "counts",
                        "repository_collection_errors",
                    )
                ):
                    raise ValueError("Historical public test identity or behavior differs")
                first.save(
                    out / "canonical-test-replay.json",
                    dict(
                        source=spec["exact_test_response"],
                        test=q["call_index"],
                        actor=q["actor_id"],
                        public_result_verified=True,
                        original_model_feedback_restored=True,
                    ),
                )
                return reply
            return result

    fn = clone_function(
        prior.generate, {**vars(prior), "Actor": Actor, "resume_slot": slot, "RUN": RUN}
    )
    fn(spec["case"], ARM, out, spec)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--index", type=int)
    p.add_argument("--arm")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.freeze:
        register()
    else:
        spec = read_json(PLAN / "protocol.json")
        first.old.checked(spec["source"])
        first.old.checked(spec["parent"])
        if a.output:
            if (a.index, a.arm, a.output.resolve()) != (INDEX, ARM, RUN / "1" / ARM):
                raise ValueError("Unexpected recovery slot")
            generate(a.output, spec)
        else:
            if (RUN / "1" / ARM / "result.json").is_file():
                raise ValueError("Recovery attempt already closed")
            allocate = clone_function(
                prior.block_reserve, {**vars(prior), "NEW": NS, "resume_slot": slot}
            )
            allocate(spec["recovery"])
            run = clone_function(prior.branch, {**vars(prior), "RUN": RUN, "__file__": __file__})
            first.save(RUN / "1/recovery.json", {ARM: run(spec["case"], ARM)})
