"""Positive/negative scheduler controls and inventory of the preregistered ordinary-task pool."""

from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ordinary_successor_v243_2 import PLAN, ROOT, RUN, save, read_json
from proworksim.software_prefix_resume_v243_2 import (
    resume_stage_limited_members,
    release_on_ordinary_entry,
)
from proworksim.software_sdk_resume_v203_3_2 import decode


def main():
    cfg = read_json(PLAN / "recovery.json")
    e = cfg["events"][0]
    orig = e["payload"]["team_budget"]
    member = e["worker_id"]
    base = read_json(PLAN / "protocol.json")
    proof_cfg = read_json(Path(cfg["boundary"]["path"]))
    det = proof_cfg["terminal_details"][member]
    results = {}
    for name, change in (
        ("eligible", {}),
        ("same_limit", {"native_allocation": orig["native_allocation"]}),
        ("held", {"held_tokens": 1}),
        ("no_decisions", {"remaining_decisions": 0}),
        ("insufficient_tokens", {"available_tokens": 100}),
        ("other_failure", {}),
        ("ended", {}),
        ("cash_stop", {}),
        ("finished_world", {}),
    ):
        snap = {
            **orig,
            "held_tokens": 0,
            "native_allocation": 5000000,
            "available_tokens": cfg["limit"],
            **change,
        }
        rt = SimpleNamespace(
            team_budget=SimpleNamespace(snapshot=lambda: snap),
            prepared=SimpleNamespace(
                world=SimpleNamespace(
                    protocol=lambda: dict(
                        terminal="DELIVERED" if name == "finished_world" else None
                    )
                )
            ),
            owner=SimpleNamespace(
                cash_boundaries=[1] if name == "cash_stop" else [], pre_dispatch_boundaries=[]
            ),
            stopped={
                member: "technical_failure" if name == "other_failure" else "team_budget_exhausted"
            },
            terminal_details={member: deepcopy(det)},
            work_ended={member: 1} if name == "ended" else {},
            waiting={},
            roles={member: {}},
            policies={member: SimpleNamespace(_done=None)},
            recorder=SimpleNamespace(record=lambda *args, **kw: None),
        )
        saved = deepcopy(snap)
        if name == "eligible":
            with TemporaryDirectory() as tmp:
                job = Path(tmp)
                save(job / "restore.json", read_json(RUN / "ordinary/restore.json"))
                repairs = release_on_ordinary_entry(rt, job / "passive-captures")
                assert read_json(job / "prefix-stop-repair.json")["repairs"] == repairs
        else:
            repairs = resume_stage_limited_members(rt, [e])
        assert bool(repairs) == (name == "eligible") and snap == saved
        results[name] = dict(released=bool(repairs), charged_unchanged=True)
    cases = []
    for r in base["pool"]:
        root = ROOT / r["source"]
        state = decode(read_json(root / "checkpoint/state.json"))
        limited = []
        for m, status in state["runtime"]["stopped"].items():
            if status == "team_budget_exhausted" and state["runtime"]["terminal_details"].get(
                m, {}
            ).get("limits") == ["team_max_total_tokens"]:
                limited.append(m)
        cases.append(
            dict(
                instance=r["instance"],
                index=r["index"],
                checkpoint=r["checkpoint"],
                prefix_token_stop=limited,
            )
        )
    save(
        PLAN / "stage-controls.json",
        dict(
            controls=results,
            cases=cases,
            scope="Registered unfinished-prefix pool only; dependency on actually restoring a specific member is verified separately",
            provider_calls=0,
        ),
    )
    print(len(cases), sum(bool(x["prefix_token_stop"]) for x in cases))


if __name__ == "__main__":
    main()
