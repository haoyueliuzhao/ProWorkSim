"""Measure raw field confusion in the physically returned calls, before the compiler touches them."""

import json
from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_commitment_prompt_v240_4 import PLAN, incumbent, read_json
from proworksim.software_benchmark_candidates_v054 import checked


def main():
    results = read_json(PLAN / "results.json")
    out = {}
    detail = []
    for arm in ("BASE", "TEXT"):
        counts = Counter()
        for r in results["records"]:
            if r["arm"] != arm or r["status"] != "settled":
                continue
            f = checked(r["response"])
            request = read_json(f.with_name("request.json"))["payload"]["wire"]
            view = json.loads(request["messages"][1]["content"])
            calls = read_json(f)["choices"][0]["message"].get("tool_calls") or []
            if len(calls) != 1:
                counts["not_one_tool_call"] += 1
                continue
            try:
                args = json.loads(calls[0]["function"]["arguments"])
            except (KeyError, ValueError):
                counts["unreadable_tool_arguments"] += 1
                continue
            if not isinstance(args, dict):
                continue
            nodes = view["obligation_graph"]
            asked = nodes[view["probed_obligation"]]
            if r["site"] != "gap":
                counts["single_calls_with_readout"] += 1
                counts["both_status_fields_copied"] += int(
                    (args.get("probe_completion"), args.get("probe_readiness"))
                    == (asked["completion"], asked["readiness"])
                )
            keys = args.get("current_obligations") or []
            if not isinstance(keys, list):
                continue
            selected = view["routes"].get(str(args.get("route")), {})
            if not selected:
                continue
            focus = selected["immediate"].partition("/")[0]
            other = [k for k in keys if isinstance(k, str) and k.partition("/")[0] != focus]
            counts["outside_focus_calls"] += bool(other)
            if r["site"] in ("q14", "x04", "y04"):
                lookup = [
                    k
                    for k in keys
                    if isinstance(k, str)
                    and k.rsplit("/", 1)[-1]
                    in ("CHECK_UPSTREAM_STATUS", "INSPECT_UPSTREAM_ARTIFACT")
                ]
                counts["dep_lookup_listed_as_debt"] += bool(lookup)
                counts["dep_chose_inspection"] += selected.get("dependency_action") in (
                    "CHECK_UPSTREAM_STATUS",
                    "INSPECT_UPSTREAM_ARTIFACT",
                )
                detail.append(
                    dict(
                        site=r["site"],
                        arm=arm,
                        repeat=r["repeat"],
                        action=selected.get("dependency_action"),
                        raw_ids=keys,
                        probe=view["probed_obligation"],
                        reported=[args.get("probe_completion"), args.get("probe_readiness")],
                        supplied=[asked["completion"], asked["readiness"]],
                    )
                )
        out[arm] = dict(counts)
    incumbent.trial.previous.first.save(
        PLAN / "field-audit.json", dict(counts=out, dependency_records=detail, extra_model_calls=0)
    )


if __name__ == "__main__":
    main()
