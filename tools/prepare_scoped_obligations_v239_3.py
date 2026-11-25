"""Freeze comparator-independent member-visible state packets for a paired repair trial."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_obligation_boundary_v239_2 as prior
from prepare_osa_states_v236 import build

ROOT = prior.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v239-3/scoped-requirements-r1"
RUN = ROOT / "runs/software-benchmark-v239-3/scoped-requirements-r1"
SOURCES = [
    ("y01", "A4", "software-benchmark-v217/confirmation-resume-r1/task-17/PREFIX", [28]),
    ("y02", "A4", "software-benchmark-v222/paired4-r1/task-00/L", [1]),
    ("y03", "A1", "software-benchmark-v224-4/window2-r1/task-02/C2", [32, 34, 36]),
    ("y04", "A2", "software-benchmark-v216/target-repair6-r1/r2-task-04/ADAPT", [12]),
]


def freeze(name, data):
    path = PLAN / name
    if path.exists() and prior.read_json(path) != data:
        raise ValueError(f"Frozen material differs: {name}")
    prior.first.save(path, data)


if __name__ == "__main__":
    rows = [build(*s) for s in SOURCES]
    freeze("states.json", rows)
    freeze(
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
                "legal_options": prior.policy.options(r),
            }
            for r in rows
        ],
    )
