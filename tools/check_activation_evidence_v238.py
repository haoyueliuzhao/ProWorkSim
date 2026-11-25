"""Replay recorded decisions through the worker-facing admission boundary, without model calls."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_decision_precision_v237_3 as precision
from proworksim.software_benchmark_candidates_v054 import checked
from proworksim.software_structured_activation import executable_decision
from proworksim.storage import read_json


def replay():
    trial = precision.trial
    result = {
        "requests": 0,
        "valid_proposals": 0,
        "requested_changes": 0,
        "retained_changes": 0,
        "held": [],
        "model_calls": 0,
        "worker_runs": 0,
    }
    for module in (trial, precision):
        rows, _ = module.design()
        lookup = {r["id"]: r for r in rows}
        for rec in read_json(module.PLAN / "results.json")["records"]:
            result["requests"] += 1
            if rec["status"] != "valid":
                continue
            result["valid_proposals"] += 1
            row = lookup[rec["state"] + rec.get("condition", rec.get("arm"))]
            body = read_json(checked(rec["response"]))
            if module is trial:
                proposal, target = trial.validate(row, body)
            else:
                proposal, target = trial.old.validate(row, body)
            decision, effective, reason = executable_decision(row, proposal, target)
            if reason:
                if (
                    proposal["decision"]["result"] != "CHANGE"
                    or decision["decision"]["missing_evidence"] != "current_test"
                    or effective["graph"] != row["graph"]
                ):
                    raise ValueError("Incorrect fallback or mutation of the model's decision")
                result["held"].append(
                    {
                        "state": row["id"],
                        "source": str(module.PLAN.relative_to(trial.first.ROOT)),
                        "requested": target["disposition"],
                        "effective": effective["disposition"],
                        "reason": reason,
                    }
                )
            elif decision != proposal or effective != target:
                raise ValueError("Unexpected change to valid proposal")
            result["requested_changes"] += int(target["disposition"] == "CHANGE")
            result["retained_changes"] += int(effective["disposition"] == "CHANGE")
    return result


if __name__ == "__main__":
    precision.first.save(precision.PLAN / "activation-replay.json", replay())
