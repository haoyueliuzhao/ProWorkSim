"""Select historical decision boundaries without inspecting any new model output."""

from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_decision_precision_v237_3 as prior
from proworksim.software_stage_response_v236 import options
from proworksim.storage import read_json

ROOT = prior.first.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v239/contract-r1"
RUN = ROOT / "runs/software-benchmark-v239/contract-r1"


def frozen(name, value):
    path = PLAN / name
    if path.exists() and read_json(path) != value:
        raise ValueError(f"Frozen material differs: {name}")
    prior.first.save(path, value)


def panel():
    rows, _ = prior.first.design()
    historical = [r for r in rows if r["id"] not in ("s13", "gap")]
    for folder, names in [(prior.trial.PLAN, ("h1",)), (prior.PLAN, ("n1", "n4"))]:
        historical.extend(
            r for r in read_json(folder / "additional-states.json") if r["id"] in names
        )
    random.Random(239).shuffle(historical)
    return [{**r, "source_id": r["id"], "id": f"q{i:02}"} for i, r in enumerate(historical, 1)] + [
        rows[-1]
    ]


if __name__ == "__main__":
    rows = panel()
    frozen("panel.json", rows)
    frozen(
        "review-packet.json",
        [
            {
                **{
                    k: r[k]
                    for k in (
                        "id",
                        "observer",
                        "graph",
                        "targets",
                        "evidence",
                        "work_status",
                        "available_tokens",
                    )
                },
                "legal_options": options(r),
            }
            for r in rows
            if r["id"] != "gap"
        ],
    )
