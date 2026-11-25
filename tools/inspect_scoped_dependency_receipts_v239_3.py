"""Offline inspection of ambiguity using the original observer's predecision inputs."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_scoped_obligations_v239_3 import GROUPS, PLAN, prior, read_json, first
from proworksim.software_context_builder_v230 import recover_observations


def main():
    records = []
    for _, folder, f in GROUPS:
        for row in read_json(folder / f):
            last = list(row["evidence"].values())[-1]
            gaps = [g for g in last.get("gaps", []) if g["kind"] == "upstream_not_current"]
            if not gaps:
                continue
            request = read_json(prior.ROOT / row["provenance"]["request"])["payload"]
            if request["member_id"] != row["observer"]:
                raise ValueError("Observer changed")
            obs = list(recover_observations(request["wire"]).values())[-1]
            if obs["actor_id"] != row["observer"]:
                raise ValueError("Observer changed")
            work = obs["dynamic_organization"]["work"]
            for gap in gaps:
                dep = gap["task_id"]
                w = work[dep]
                fields = ("owner", "revision", "work_epoch", "completion_current", "completion")
                records.append(
                    dict(
                        site=row["id"],
                        upstream=dep,
                        observer=row["observer"],
                        keys_visible=sorted(w),
                        values={k: w[k] for k in fields if k in w},
                        request=row["provenance"]["request"],
                    )
                )
    first.save(
        PLAN / "upstream-evidence-inspection.json",
        dict(records=records, provider_calls=0, changed_scores=False),
    )


if __name__ == "__main__":
    main()
