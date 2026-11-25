"""Materialize the selected v237 OSA requests for currently registered decision points."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_intervention_prompt_v236_2 as trial
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json

OUT = ROOT / "artifacts/software-benchmark-v237/selected-prompt-r1"


def build_request(row):
    """Use the exact tested OSA input construction for a live, receipt-bound row."""
    return trial.prompt_wire(row, "staged")


def main():
    result = read_json(trial.PLAN / "results.json")
    if result["prompt_pilot_supported"] is not True:
        raise ValueError("Candidate did not meet the registered selection rule")
    plan = read_json(ROOT / "artifacts/software-benchmark-v237/recruitment-r1/first-wave.json")
    panel = {r["id"]: r for r in read_json(trial.PANEL_PATH)}
    refs = []
    for candidate in plan["candidates"]:
        if candidate["status"] != "matched_registered_checkpoint":
            continue
        row = panel[candidate["decision_panel_state"]]
        if candidate["decision_checkpoint"] != row["provenance"]["checkpoint"]:
            raise ValueError("Wrong saved state")
        path = OUT / (row["id"] + "-request.json")
        trial.save(path, build_request(row))
        refs.append(reference(path))
    budget = result["balance_nanoyuan"]
    required = plan["ready_pair_reserve_nanoyuan"]
    trial.save(
        OUT / "selection.json",
        dict(
            source=reference(trial.PLAN / "results.json"),
            chosen="v236.2 revised staged prompt",
            request_builder="tools.prepare_selected_prompt_v237.build_request",
            prepared_requests=refs,
            cash_cap_nanoyuan=result["cap_nanoyuan"],
            balance_after_pilot_nanoyuan=budget,
            reserve_for_two_ready_pairs_nanoyuan=required,
            headroom_after_two_reservations_nanoyuan=budget - required,
            new_full_task_pairs=0,
            missing_natural_states=["A2", "A3"],
        ),
    )


if __name__ == "__main__":
    main()
