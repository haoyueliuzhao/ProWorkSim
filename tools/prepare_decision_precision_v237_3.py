"""Fresh paired checkpoints for a minimal edit to the incumbent production candidate."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_osa_states_v236 import ROOT, build, save
from proworksim.software_stage_response_v236 import options
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v237-3/decision-precision-r1"
RUN = ROOT / "runs/software-benchmark-v237-3/decision-precision-r1"
SOURCES = [
    ("STABLE", "software-benchmark-v224-2/development4-r1/task-01/KEEP", [12, 14]),
    ("A1", "software-benchmark-v224-3/pair-r1/task-01/KEEP", [39, 47, 48]),
    ("A2", "software-benchmark-v219/recovery6-r1/task-01/C1", [10]),
    ("STABLE", "software-benchmark-v224-4/window2-r1/task-03/C1", [38, 40, 42]),
]


def freeze(name, value):
    dest = PLAN / name
    if dest.exists() and read_json(dest) != value:
        raise ValueError(f"Frozen file differs: {name}")
    save(dest, value)


if __name__ == "__main__":
    rows = [build(f"n{i}", *s) for i, s in enumerate(SOURCES, 1)]
    freeze("additional-states.json", rows)
    freeze(
        "review-packet.json",
        [
            {
                **{
                    k: r[k]
                    for k in (
                        "id",
                        "graph",
                        "work_status",
                        "targets",
                        "evidence",
                        "available_tokens",
                    )
                },
                "legal_options": options(r),
            }
            for r in rows
        ],
    )
