"""One predeclared actual long request per candidate; no world work or retry."""

import argparse
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, json_bytes, read_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("model", "weight-manifest", "candidate", "request-record", "output"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--devices", type=int, required=True)
    a = p.parse_args()
    from proworksim.candidate_runtime_v017 import CandidateActor, candidate_profile
    from proworksim.online_training import reference

    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    report = {
        "version": "harness-long-request-capacity-v0.17",
        "status": "started",
        "source_before": before,
        "request_record": reference(a.request_record),
        "devices": a.devices,
        "world_actions": 0,
        "optimizer_steps": 0,
        "scope": "One fixed original long request under revised placement. No old reward repair or capacity claim for backward/other prompts.",
    }
    started = time.time()
    try:
        profile = candidate_profile(a.candidate, dtype="float32", devices=a.devices)
        owner = CandidateActor.from_candidate(
            a.model,
            manifest=a.weight_manifest,
            profile=profile,
            output=out / "resident",
            recipe={
                "seed": 2026092717,
                "max_length": 16384,
                "max_output_tokens": 2048,
                "diagnostic_max_groups": 0,
                "post_update_max_decisions": 0,
                "max_rss_bytes": 192 * 1024**3,
            },
        )
        source = read_json(Path(a.request_record))
        owner.begin_window("fixed-long-request-capacity")
        response = owner.complete(source["request"], timeout_seconds=600)
        report.update(
            http_status=response["http_status"],
            response=response["body"],
            profile=profile,
            actor_identity=owner.freeze_identity(),
        )
        owner.finish_evaluation([], out / "closed-capacity-window")
        report["status"] = "passed" if response["http_status"] == 200 else "failed"
    except Exception as e:
        report.update(status="failed", error={"type": type(e).__name__, "message": str(e)})
        raise
    finally:
        report.update(source_after=code_identity(), elapsed_seconds=time.time() - started)
        report["source_unchanged"] = report["source_before"] == report["source_after"]
        atomic_write(out / "report.json", json_bytes(report))
    print(json_bytes({k: report[k] for k in ("status", "elapsed_seconds", "devices")}).decode())
    if report["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
