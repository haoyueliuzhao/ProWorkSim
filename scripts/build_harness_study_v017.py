"""Fixed H1 v0.17: explicit prompt/diagnostic and placement revision, 48 slots."""

import argparse
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v016 import (
    build_protocol as previous_protocol,
    validate_screen,
    read,
    ref,
)

VERSION = "harness-study-v0.17"
DEVICES = {"qwen35-9b": 2, "qwen38-27b": 4}
SELECTION = {
    "version": "harness-combination-selection-v0.17",
    "eligible": "All 12 declared arm episodes known with valid records, unchanged source, pure evaluation and actual measured resources.",
    "ordered_keys": [
        "descending complete implement+review (8 slots)",
        "descending complete pair+chain (4 slots)",
        "ascending actual allocated device seconds for arm",
        "candidate_id then harness lexicographic",
    ],
    "no_eligible_arm": "No automatic H2 selection; retain unknowns and diagnose the bounded failure without imputation.",
    "interpretation": "Relative development ranking, not capability certification; SDK is not preferred by rule.",
}


def build_protocol(screen):
    from proworksim.candidate_runtime_v017 import candidate_profile

    protocol = previous_protocol(screen)
    candidate = screen["candidate_id"]
    profile = candidate_profile(
        screen["runtime"]["profile"]["candidate_id"], dtype="float32", devices=DEVICES[candidate]
    )
    protocol.update(
        version=VERSION,
        experiment_id="h1-v017-" + candidate,
        launch_gate={"version": "h1-launch-admission-v0.17", "state": "planning_only"},
        protocol_revision={
            "previous": "harness-study-v0.16",
            "changes": [
                "Explicit model autonomy to select permitted evidence; SDK system prompt changed before H1.",
                "Both arms expose structured native and worker parser feedback without business answers.",
                "Fixed 2-device 9B / 4-device 27B placement for both harnesses; precision, LoRA, sampling and context/output unchanged.",
                "Original S1 closure includes explicitly preserved unknown scores; old selection and old successor graph remain stopped.",
            ],
            "original_results_regraded": False,
            "original_N0_N1_resumed": False,
        },
        combination_selection=copy.deepcopy(SELECTION),
        estimands={
            "paired_delta": "Per model, mean of SDK-minus-native across 6 situations x 2 repeats; no missing result imputation.",
            "raw_task_weights": {
                "implement": 1 / 3,
                "review": 1 / 3,
                "pair": 1 / 6,
                "chain": 1 / 6,
            },
            "secondary_task_macro_weights": {
                k: 0.25 for k in ("implement", "review", "pair", "chain")
            },
            "independent_project_count": 6,
            "same_seed_is_same_text": False,
            "subtract_original_S1_mean": False,
        },
    )
    protocol["runtime"] = {
        "kind": "qwen_hybrid_diagnostics",
        "profile": profile,
        "original_S1_runtime": copy.deepcopy(screen["runtime"]),
        "execution_placement_revision": "Declared new H1 resource allocation, identical across harnesses within model; no CPU/offload fallback.",
    }
    protocol["harness_identity"]["native_v15"].update(
        adapter_version="model-policy-v0.17", feedback="public-format-diagnostics-v0.17"
    )
    protocol["harness_identity"]["openhands_v16"].update(
        adapter_version="openhands-managed-worker-v0.17",
        feedback="public-format-diagnostics-v0.17",
        system_revision="autonomous-permitted-evidence-v0.17",
    )
    for w in protocol["windows"]:
        w["window_id"] = w["window_id"].replace("h1-", "h1-v017-", 1)
        for slot in w["slots"]:
            slot["slot_id"] = slot["slot_id"].replace("h1-", "h1-v017-", 1)
    return protocol


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--screen-protocol", type=Path, action="append", required=True)
    p.add_argument("--profile-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or len(a.screen_protocol) != 2:
        raise ValueError("New directory and both candidates required; fixed 48 slots")
    protocols = {}
    for path in a.screen_protocol:
        screen = read(path)
        validate_screen(screen, profile_root=a.profile_root)
        if screen["candidate_id"] in protocols:
            raise ValueError("Duplicate candidate")
        protocols[screen["candidate_id"]] = build_protocol(screen)
    if set(protocols) != set(DEVICES):
        raise ValueError("Both declared new candidates required")
    a.output.mkdir(parents=True)
    for candidate, protocol in protocols.items():
        (a.output / f"h1-{candidate}.json").write_text(
            json.dumps(protocol, ensure_ascii=False, indent=2) + "\n"
        )
    (a.output / "study.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "status": "planned_not_started",
                "episodes": 48,
                "protocols": {
                    c: {
                        "file": f"h1-{c}.json",
                        "body_sha256": digest(
                            json_bytes({k: v for k, v in p.items() if k != "launch_gate"})
                        ),
                    }
                    for c, p in protocols.items()
                },
                "source_screen_protocols": [ref(p) for p in a.screen_protocol],
                "selection": SELECTION,
                "original_S1_unknowns_preserved": True,
                "formal_admission_required": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
