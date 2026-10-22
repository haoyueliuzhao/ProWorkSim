"""Necessary CPU controls for generation-only REF conversion qualification."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim import software_benchmark_ref_terminal_boundary_v054_r1 as boundary  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def panel():
    slots = {"slots": [{"slot_id": f"{arm}-{index}", "arm": arm, "seed": index}
                       for arm in ("REF", "MATCH", "PROJECT") for index in range(500)]}
    state = {"rows": [{"slot": deepcopy(slot), "generation": {"status": "closed"},
                       "scores": {"code": {"status": "running"}}}
                      for slot in slots["slots"]]}
    return state, slots


class BoundaryControls(unittest.TestCase):
    def test_unknown_and_cpu_scoring_do_not_block_or_change_records(self):
        state, slots = panel()
        state["rows"][0]["generation"].update(status="technical_unknown",
            actual_cost_ledger={"unsettled": "retained"}, unknown_tokens=None)
        before = deepcopy(state)
        proof = boundary.ref_generation_evidence(state, slots)
        self.assertTrue(proof["eligible"])
        self.assertEqual((proof["closed_ref_generations"], proof["technical_unknown_ref_generations"]), (499, 1))
        self.assertFalse(proof["score_completion_required"])
        self.assertNotIn("all_500_ref_scored", proof)
        self.assertEqual(state, before)

    def test_active_pending_and_unknown_states(self):
        for status in ("pending", "intent", "running"):
            state, slots = panel()
            state["rows"][0]["generation"]["status"] = status
            self.assertFalse(boundary.ref_generation_evidence(state, slots)["eligible"])
        state["rows"][0]["generation"]["status"] = "unrecognized"
        with self.assertRaises(ValueError):
            boundary.ref_generation_evidence(state, slots)

    def test_full_identity_including_seed_and_other_arms(self):
        for index in (0, 500):
            state, slots = panel()
            state["rows"][index]["slot"]["seed"] += 1
            with self.assertRaises(ValueError):
                boundary.ref_generation_evidence(state, slots)
        state, slots = panel()
        slots["slots"][1] = deepcopy(slots["slots"][0])
        state["rows"][1]["slot"] = deepcopy(slots["slots"][0])
        with self.assertRaises(ValueError):
            boundary.ref_generation_evidence(state, slots)

    def test_incomplete_panel_never_observes_live_scopes(self):
        state, slots = panel()
        state["rows"][0]["generation"]["status"] = "running"
        with patch.object(boundary, "_read_ref") as read, patch.object(boundary, "_worker_quiet") as quiet:
            with self.assertRaises(ValueError):
                boundary.collect_runtime_boundary(state, slots, None, slots_reference={})
            read.assert_not_called()
            quiet.assert_not_called()

    def test_missing_claim_requires_exact_unentered_termination(self):
        job = {"path": "fixture-job", "sha256": "a"}
        generation = {"status": "technical_unknown", "claimed": False,
                      "attempts": [{"job": job, "completion": "completion", "result": "result"}]}
        records = {"completion": {"job": job, "status": "exited", "returncode": 1},
                   "result": {"slot_id": "REF-0", "slot_claimed": False, "entered": False, "model_calls": 0}}
        with patch.object(boundary, "_read_ref", side_effect=records.__getitem__):
            proof = boundary._preclaim_failure({"slot_id": "REF-0"}, generation, {"fixture-job": job})
            self.assertTrue(proof["claim_never_created"])
            records["result"]["entered"] = True
            with self.assertRaises(ValueError):
                boundary._preclaim_failure({"slot_id": "REF-0"}, generation, {"fixture-job": job})

    def test_idle_resident_must_be_exact_and_unoccupied(self):
        observed = {"declaration": {"mode": "REF", "gpu_index": 7, "gpu_uuid": "fixture-gpu"},
                    "session_capacity": 1, "active_claims": [],
                    "status": {"active_claim": None, "inflight": 0, "poisoned": False},
                    "declaration_reference": {}, "ready_reference": {}, "unit_state": {},
                    "ready": {"host_process": {"pid": 123, "start_ticks": 1}}}
        boundary._idle_ref(observed)
        for key, value in (("active_claim", "live"), ("inflight", 1), ("poisoned", True)):
            bad = deepcopy(observed)
            bad["status"][key] = value
            with self.assertRaises(RuntimeError):
                boundary._idle_ref(bad)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryControls))
    proof = {"version": "v054-ref-terminal-boundary-cpu-control-r1", "passed": result.wasSuccessful(),
             "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
             "model_calls": 0, "GPU_loads": 0, "formal_claims": 0, "queue_writes": 0,
             "ledger_writes": 0, "worker_signals": 0,
             "sources": [reference(__file__), reference(boundary.__file__)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(write_new(args.output, proof)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
