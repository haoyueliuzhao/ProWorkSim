"""Freeze four additional member-visible checkpoints before querying the organization controller."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_osa_states_v236 import ROOT, build, save
from proworksim.software_stage_response_v236 import options
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v237-2/decision-clarity-r1"
RUN = ROOT / "runs/software-benchmark-v237-2/decision-clarity-r1"
WINDOWS = [
    (1, "STABLE", [26, 30, 32]),
    (5, "A1", [25, 27, 29]),
    (7, "A1", [17, 31, 33]),
    (11, "A4", [27]),
]


def freeze_file(name, value):
    dest = PLAN / name
    if dest.exists() and read_json(dest) != value:
        raise ValueError(f"Frozen file differs: {name}")
    save(dest, value)


if __name__ == "__main__":
    windows = read_json(ROOT / "artifacts/software-benchmark-v226/preparation-r1/replay.json")[
        "windows"
    ]
    rows = []
    packets = []
    for idx, (n, kind, receipts) in enumerate(WINDOWS, 1):
        source = Path(windows[n - 1]["source"]).parent.relative_to("runs")
        row = build(f"h{idx}", kind, str(source), receipts)
        rows.append(row)
        packets.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "id",
                        "targets",
                        "graph",
                        "evidence",
                        "work_status",
                        "available_tokens",
                    )
                },
                "legal_options": options(row),
            }
        )
    freeze_file("additional-states.json", rows)
    freeze_file("review-packet.json", packets)
