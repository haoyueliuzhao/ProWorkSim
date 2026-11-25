"""Preserve a locked long rationale and use a bounded native graph-event reason."""

import argparse
import fcntl
from hashlib import sha256
from pathlib import Path
import os
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_astropy_worker_v241 as legacy
from recover_astropy_worker_v241 import batch, read_json

OUT = batch.RUN / "reason-compat-r1"
NS = "v241.1-reason"
REV = batch.PLAN / "reason-transport-revision.json"


def native_reason(text):
    if len(text.strip()) <= 1200:
        return text
    suffix = " … [full archived rationale SHA256 " + sha256(text.encode()).hexdigest() + "]"
    return text[: 1200 - len(suffix)] + suffix


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=["OSA"])
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    spec = read_json(batch.PLAN / "protocol.json")
    (item,) = [r for r in spec["roster"] if r["id"] == "q03"]
    case = item["case"]
    for f in spec["files"]:
        batch.checked(f)
    repair = read_json(legacy.REPAIR)
    batch.checked(repair["source"])
    batch.checked(repair["bank"])
    state = read_json(batch.DESIGN)["states"][item["index"]]
    source = next(r for r in batch.sources() if r["id"] == item["id"])
    response = read_json(batch.checked(item["decision"]))
    reason = batch.policy.parse({**source, "probe_id": item["probe"]}, response)["reason"]
    revision = dict(
        original_reason_length=len(reason),
        native_reason_length=len(native_reason(reason)),
        full_reason_sha256=sha256(reason.encode()).hexdigest(),
        original_response=item["decision"],
        checkpoint=item["checkpoint"],
        prior_slot=batch.NS + ":" + case + ":OSA",
        prior_worker_calls=0,
        case=case,
        script=batch.reference(Path(__file__)),
        observer_repair=batch.reference(legacy.REPAIR),
        method="Cap the graph event reason at 1200 characters with prefix and original-text hash; preserve complete original rationale in proposal. Same patch, first action, logical OSA debit, tools and remaining budget.",
    )
    folder = OUT / case
    dest = folder / "OSA"
    if a.arm:
        if a.output != dest or read_json(REV) != revision:
            raise ValueError("Invalid repair binding")

        class Bound(batch.Replay):
            binding = item

            def activate(self, node, observer, frozen, choice):
                return super().activate(
                    node, observer, frozen, {**choice, "reason": native_reason(choice["reason"])}
                )

        module = batch.paired.episode_module
        orig = module.resume

        def reader(point):
            saved, proof = orig.read(point)
            ctl = saved["control_state"]
            if (
                proof["identity"] != repair["checkpoint"]
                or ctl["node"]["anomaly_id"] != repair["anomaly_id"]
                or ctl["ordinal"] != repair["ordinal"]
                or ctl.get("observer", repair["observer"]) != repair["observer"]
            ):
                raise ValueError("Wrong restore metadata")
            return {**saved, "control_state": {**ctl, "observer": repair["observer"]}}, proof

        fn = module.episode
        resume = SimpleNamespace(**{**vars(orig), "read": reader})
        batch.paired.clone_function(
            fn,
            {**fn.__globals__, "RUN": batch.RUN, "OrganizationExecution": Bound, "resume": resume},
        )(item["index"], "OSA", dest, False, slot_namespace=NS, expected_case=case)
        return
    OUT.mkdir(exist_ok=True)
    with (OUT / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (OUT / "completed.json").is_file():
            return
        if REV.exists() and read_json(REV) != revision:
            raise ValueError("Changed revision")
        previous = legacy.OUT / case / "OSA"
        if read_json(previous / "result.json").get(
            "error"
        ) != "Use the listed short evidence IDs and a bounded reason" or not read_json(
            previous / "actor/cleanup.json"
        ).get("owned_actor_removed"):
            raise ValueError("Unexpected previous result")
        meter = batch.PairedLedger.load(batch.RUN / "authority.json")
        with meter.db() as db:
            old = revision["prior_slot"]
            if (
                db.execute("select status from slots where id=?", (old,)).fetchone() != ("closed",)
                or db.execute("select count(*) from requests where slot=?", (old,)).fetchone()[0]
            ):
                raise ValueError("Cannot replace a model-exposed arm")
            if not db.execute(
                "select 1 from slots where id=?", (batch.NS + ":" + case + ":KEEP",)
            ).fetchone():
                raise ValueError("KEEP side unavailable")
        batch.save(REV, revision)
        os.environ["TMPDIR"] = str(batch.RUN / "tmp")
        fn = batch.paired.reserve
        batch.paired.clone_function(fn, {**fn.__globals__, "ARMS": ["OSA"]})(
            batch.RUN / "authority.json",
            dict(
                case=case,
                account_cap_nanoyuan=spec["cap"],
                arm_limit=item["initial_budget"],
                worst_pair_nanoyuan=item["initial_budget"] * 8000,
            ),
            namespace=NS,
            block=NS + ":" + case,
        )
        folder.mkdir(exist_ok=True)
        result = batch.isolated(Path(__file__).resolve(), ["--arm", "OSA"], dest, "result.json")
        scores = {}
        if result["status"] == "closed":
            for kind in ("code", "delivery"):
                rec = batch.isolated(
                    batch.ROOT / "tools" / item["score_script"],
                    ["--index", item["score_index"], "--kind", kind, "--episode", dest],
                    folder / ("OSA-" + kind),
                    "receipt.json",
                )
                scores[kind] = {k: rec.get(k) for k in ("status", "resolved", "error")}
        batch.save(
            OUT / "completed.json",
            dict(status=result["status"], error=result.get("error"), scores=scores),
        )


if __name__ == "__main__":
    main()
