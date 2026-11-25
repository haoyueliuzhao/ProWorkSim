"""Select pre-existing two-worker prefixes before inspecting any successor or score."""

from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory_multitype_v242 import ROOT, read_json
from proworksim.software_benchmark_candidates_v054 import reference
from run_multitype_worker_v242 import freeze

PLAN = ROOT / "artifacts/software-benchmark-v244/midtask15-r1"
RUN = ROOT / "runs/software-benchmark-v244/midtask15-r1"


def register():
    bank = ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json"
    groups = defaultdict(list)
    for task in sorted(read_json(bank)["rows"], key=lambda r: r["index"]):
        index = task["index"]
        found = sorted(
            (ROOT / "runs/software-benchmark-v217").glob(
                f"*/task-{index:02d}/PREFIX/checkpoint/manifest.json"
            )
        )
        if len(found) != 1:
            raise ValueError(f"Expected one original prefix for {index}")
        proof = read_json(found[0])
        source = found[0].parents[1]
        groups[task["repo"]].append(
            dict(
                index=index,
                instance=task["instance_id"],
                repo=task["repo"],
                source=str(source.relative_to(ROOT)),
                checkpoint=proof["identity"],
                prefix=proof["prefix_tokens"],
            )
        )
    roster = [
        groups[repo][j]
        for j in range(max(map(len, groups.values())))
        for repo in sorted(groups)
        if j < len(groups[repo])
    ][:15]
    assert len({x["instance"] for x in roster}) == 15
    freeze(
        PLAN / "roster.json",
        dict(
            bank=reference(bank),
            pool=sum(map(len, groups.values())),
            rule="Cycle repositories alphabetically and take original indices in ascending order within each. Use each original archived two-member prefix, irrespective of alarm, score, menu or eventual decision.",
            roster=roster,
            endpoints=["official_final_code", "official_legal_delivery"],
            limit_including_prefix=5000000,
            requested_cash_yuan=190,
            arms=["KEEP", "OSA"],
            model="DeepSeek Flash, thinking disabled; T1",
            sample="Historically exposed development checkpoints; one fresh paired attempt each. No selection on successor outcomes.",
            analysis="All 15 paired by instance; list both pass, KEEP only, OSA only, neither, and unscored. Report actual budget and code/delivery separately. Implemented changes descriptive only.",
        ),
    )
    print([(r["index"], r["instance"]) for r in roster])


if __name__ == "__main__":
    register()
