"""Exercise passive recording inside the real SDK and replay three known historical windows."""

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_osa_checkpoint_v226 as control
from inventory_multitype_v242 import ROOT, history, read_json, save
from proworksim.software_passive_capture_v242_1 import PassiveCapture
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim import software_sdk_resume_v203_3_4 as resume

PLAN = ROOT / "artifacts/software-benchmark-v242-1/precursors-r1"
RUN = ROOT / "runs/software-benchmark-v242-1/precursors-r1"


def main():
    cpu = RUN / "passive-sdk"
    recorder = PassiveCapture(cpu / "passive")

    def instrument(prepared, runtime, *, on_opportunity):
        return control.runtime.run_fragment(
            prepared, runtime, on_opportunity=recorder.callback(prepared, runtime, on_opportunity)
        )

    module = SimpleNamespace(**{**vars(control.runtime), "run_fragment": instrument})
    control.clone_function(control.main, {**control.main.__globals__, "runtime": module})(cpu)
    (event,) = recorder.events
    assert event["kind"] == "A2" and event["status"] == "saved", recorder.events
    restored, p = resume.read(cpu / "passive" / event["path"] / "checkpoint")
    original, q = resume.read(cpu / "checkpoint")
    for k in (
        "runtime",
        "workers",
        "schedule",
        "prefix_ledger",
        "team_state",
        "world_state_sha256",
        "test_budget",
        "public_test_calls",
    ):
        assert restored[k] == original[k], k
    ids = read_json(cpu / "passive" / event["path"] / "observations.json")
    assert ids[-1]["ordinal"] == restored["control_state"]["ordinal"] == event["ordinal"]
    rows = []
    for path, kind in (
        ("software-benchmark-v216/target-repair6-r1/r2-task-02/ADAPT", "A2"),
        ("software-benchmark-v216/target-repair6-r1/r2-task-04/ADAPT", "A2"),
        ("software-benchmark-v217/selection28-r1/task-04/KEEP", "A3"),
    ):
        d = ROOT / "runs" / path
        source = Path(read_json(d / "result.json")["checkpoint_parent"]).parent
        previous = history(source)
        state = dict(read_json(source / "checkpoint/state.json")["__dict__"])
        before = dict(state["runtime"]["__dict__"])["opportunities"]
        monitor = PassiveCapture(
            d / "unused", history=(h for h in previous if h["ordinal"] <= before)
        )
        witness = None
        for i, o in enumerate(read_json(d / "boundary.json")["outcomes"], 1):
            nodes = monitor.observe(before + i, o)
            wanted = [n for n in nodes if n["anomaly_type"] == kind]
            if wanted:
                witness = dict(
                    branch_opportunity=i,
                    absolute_opportunity=before + i,
                    actor=o["worker_id"],
                    node=wanted[0]["subject"],
                    command=o["response"]["command_id"],
                )
                break
        rows.append(
            dict(path=path, kind=kind, receipt=witness, source=reference(d / "boundary.json"))
        )
    save(
        PLAN / "passive-controls.json",
        dict(
            sdk_fixture=event,
            world_alignment=True,
            accounting_alignment=True,
            histories_alignment=True,
            fixture_prefix_tokens=p["prefix_tokens"],
            historical=rows,
            provider_calls=0,
            historical_worker_pairs=0,
        ),
    )
    print([(r["kind"], r["receipt"]["branch_opportunity"] if r["receipt"] else None) for r in rows])


if __name__ == "__main__":
    main()
