"""Validate current and archived public-test receipts under their own original request hashes."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_dynamic_test_history_v248_3 as prev
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json, json_bytes, digest

base = prev.prior
first = base.first
NS = "v248.4"
RUN = base.ROOT / "runs/software-benchmark-v248/dynamic-membership-r4"
PLAN = base.ROOT / "artifacts/software-benchmark-v248/dynamic-membership-r4"


def slot(i, a):
    return f"{NS}:{i}:{a}"


def generate(out, spec):
    expected = read_json(first.old.checked(spec["exact_test_request"]))
    original = read_json(first.old.checked(spec["exact_test_response"]))

    def prepare(*args, **kwargs):
        prepared = base.prepare_case(*args, **kwargs)
        runner = prepared.source_provider.runner

        class CanonicalPublicTest(type(runner)):
            def __call__(self, **test):
                fresh = super().__call__(**test)
                if self.calls != expected["call_index"]:
                    return fresh
                q = read_json(self.folder / f"test-{self.calls:04d}" / "request.json")
                normalize = lambda v: {k: x for k, x in v.items() if k != "hard_deadline_monotonic"}
                if normalize(q) != normalize(expected):
                    raise ValueError("Original selected test no longer matches")
                for k in ("passed", "counts", "validation_status", "repository_collection_errors"):
                    if fresh.get(k) != original.get(k):
                        raise ValueError("Historical test outcome mismatch")
                if original["execution"]["managed_request_sha256"] != digest(json_bytes(expected)):
                    raise ValueError("Invalid original RPC binding")
                if any(
                    fresh["execution"].get(k) != original["execution"].get(k)
                    for k in (
                        "actor_id",
                        "source_reference",
                        "input_tree_sha256",
                        "argv",
                        "returncode",
                        "command_executed",
                        "public_test_selection",
                    )
                ):
                    raise ValueError("Current and original test semantics differ")
                first.save(
                    out / "canonical-test-replay.json",
                    dict(
                        original=spec["exact_test_response"],
                        fresh=first.old.reference(
                            self.folder / f"test-{self.calls:04d}" / "response.json"
                        ),
                        both_hashes_verified=True,
                        only_original_feedback_replayed=True,
                    ),
                )
                return original

        runner.__class__ = CanonicalPublicTest
        return prepared

    fn = clone_function(
        base.generate, {**vars(base), "prepare_case": prepare, "resume_slot": slot, "RUN": RUN}
    )
    fn(spec["case"], prev.ARM, out, spec)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--index", type=int)
    p.add_argument("--arm")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.freeze:
        s = read_json(prev.PLAN / "protocol.json")
        first.freeze(
            PLAN / "protocol.json",
            {
                **s,
                "prior_replay": first.old.reference(prev.RUN / "1/O-DYNAMIC/replay.json"),
                "source": first.old.reference(Path(__file__)),
                "rule": "Run the original callback validation to completion first, retain fresh raw response, then validate the previously sealed test response against its own original request hash before restoring it to the model. All original model request wires must still match exactly.",
            },
        )
    else:
        s = read_json(PLAN / "protocol.json")
        first.old.checked(s["source"])
        first.old.checked(s["parent"])
        if a.output:
            if (a.index, a.arm, a.output.resolve()) != (1, prev.ARM, RUN / "1" / prev.ARM):
                raise ValueError("Foreign slot")
            generate(a.output, s)
        else:
            alloc = clone_function(
                base.block_reserve, {**vars(base), "NEW": NS, "resume_slot": slot}
            )
            alloc(s["recovery"])
            run = clone_function(base.branch, {**vars(base), "RUN": RUN, "__file__": __file__})
            first.save(RUN / "1/recovery.json", {prev.ARM: run(s["case"], prev.ARM)})
