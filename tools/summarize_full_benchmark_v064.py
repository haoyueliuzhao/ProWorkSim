"""Summarize normalized v064 receipts without touching experiments or services."""
import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_full_plan_v064 import reference, retain
from proworksim.software_benchmark_usage_metrics_v064 import summarize
from proworksim.software_benchmark_candidates_v054 import checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_bytes())
    source = json.loads(args.records.read_bytes())
    if "record_files" in source:
        records = (json.loads(checked(ref).read_bytes()) for ref in source["record_files"].values())
    else:
        records = source["records"]
    result = summarize(plan, records, preparation_calls=source.get("preparation_calls", []),
                       preparation_unresolved_calls=source.get("preparation_unresolved_calls", []))
    result["sources"] = {"plan": reference(args.plan), "records": reference(args.records),
                         "script": reference(__file__)}
    print(json.dumps(retain(args.output, result)))


if __name__ == "__main__":
    main()
