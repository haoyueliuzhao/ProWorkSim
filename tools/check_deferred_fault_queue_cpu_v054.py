"""One synthetic CPU suite for the host-only scheduling overlay; no services."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path("/data0/zhuxinrui/projects/ProWorkSim")
STAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
proworksim = importlib.import_module("proworksim")
proworksim.__path__.insert(0, str(STAGE / "src/proworksim"))
overlay = importlib.import_module("proworksim.software_benchmark_fault_queue_v054")
base = overlay.base


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return overlay.reference(path)


def rows():
    return [{"slot": {"slot_index": index + 1, "slot_id": "synthetic-" + str(index + 1),
                       "instance_id": "synthetic-task-" + str(index // 3),
                       "arm": ("REF", "MATCH", "PROJECT")[index % 3], "seed": index // 3},
             "generation": {"status": "closed", "attempts": []},
             "scores": {"code": {"status": "official_report", "resolved": False}},
             "delivery": {"status": "not_applicable"}} for index in range(1500)]


def fixture(root):
    value = overlay.ResilientCoordinator.__new__(overlay.ResilientCoordinator)
    value.root, value.exception_root = root, root / "overlay"
    value.exception_root.mkdir(parents=True)
    value.bindings_ref = {"path": "/synthetic-bindings", "sha256": "a" * 64, "bytes": 0}
    value.bindings = {"scorer_manifest": {"synthetic": True}}
    value.policy_ref = {"path": "/synthetic-policy", "sha256": "b" * 64, "bytes": 0}
    value._context = None
    value.state = {"status": "running", "rows": rows(), "bindings": value.bindings_ref, "faults": []}
    value.system = type("SyntheticSystem", (), {"active": lambda self, unit: False})()
    return value


class DeferredCPU(unittest.TestCase):
    def test_adopt_inherits_five_active_original_jobs(self):
        with tempfile.TemporaryDirectory(prefix="v054-adopt-cpu-") as tmp:
            coordinator = fixture(Path(tmp) / "queue")
            coordinator.bindings["frozen_files"] = []
            coordinator.policy = {"previous_controller_unit": "proworksim-v054-formal-queue-r7.service"}
            units = []
            for index, row in enumerate(coordinator.state["rows"][:5], 1):
                directory = coordinator.root / "slots" / str(index) / "preclaim-1/worker"
                unit = "proworksim-v054-generation-" + f"{index:024x}" + ".service"
                job = put(directory / "job.json", {"kind": "generation", "unit": unit,
                    "bindings": coordinator.bindings_ref, "argv": ["/synthetic/no-execute"]})
                row["generation"].update(status="running", job=job, unit=unit,
                                         worker_directory=str(directory))
                row["scores"] = {}
                units.append(unit)
            coordinator.system = type("SyntheticSystem", (), {
                "active": lambda self, unit: unit in units})()
            inherited = deepcopy(coordinator.state["rows"][:5])
            adoption = base.load_ref(coordinator.adopt())
            self.assertEqual(len(adoption["inherited_original_workers"]), 5)
            self.assertTrue(all(x["observed_active"] and x["intent_never_relaunched"]
                                for x in adoption["inherited_original_workers"]))
            self.assertEqual(coordinator.state["rows"][:5], inherited)
            self.assertEqual(coordinator.state["active_generation"], 5)
            self.assertEqual(coordinator.state["bindings"], coordinator.bindings_ref)
            self.assertEqual(coordinator.state["status"], "running")
            self.assertEqual(adoption["model_requests"] + adoption["model_reloads"] + adoption["formal_claims"], 0)
            with self.assertRaisesRegex(ValueError, "already adopted"):
                coordinator.adopt()

    def test_local_unknowns_terminal_no_replay_and_integrity(self):
        with tempfile.TemporaryDirectory(prefix="v054-deferred-cpu-") as tmp:
            root = Path(tmp)
            coordinator = fixture(root / "state")
            score_row = coordinator.state["rows"][0]
            work = root / "score-worker"
            request = put(root / "request.json", {"preparation_only": False})
            work.mkdir()
            score_row["scores"]["code"] = {"status": "running", "request": request,
                "worker_directory": str(work), "job": {"synthetic": "score-job"}}
            coordinator.complete_score(score_row, "code", {"returncode": 124})
            self.assertEqual(coordinator.state["status"], "running")
            self.assertEqual(score_row["scores"]["code"]["status"], "technical_unknown")
            self.assertNotIn("resolved", score_row["scores"]["code"])
            self.assertEqual(len(coordinator.state["deferred_exceptions"]), 1)
            score_event = coordinator.state["deferred_exceptions"][0]["evidence"]
            self.assertEqual(base.load_ref(score_event)["row_snapshot"]["scores"]["code"]["request"], request)

            gen_row = coordinator.state["rows"][1]
            gen_work = root / "generation-worker"
            completion = {"returncode": 1}
            put(gen_work / "completion.json", completion)
            put(root / "episode/result.json", {"status": "technical_unknown", "model_calls": None})
            gen_row["scores"] = {}
            gen_row["generation"] = {"status": "running", "attempts": [],
                "job": {"synthetic": "generation-job"}, "worker_directory": str(gen_work),
                "episode_output": str(root / "episode"), "resident_id": "synthetic-mp"}
            with patch.object(base, "claim_path", return_value=root / "no-claim/claim.json"):
                coordinator.complete_generation(gen_row, completion)
            self.assertEqual(coordinator.state["status"], "running")
            self.assertEqual(gen_row["generation"]["status"], "technical_unknown")
            self.assertEqual(len(gen_row["generation"]["attempts"]), 1)
            snapshot = deepcopy(gen_row["generation"])
            with patch.object(base, "claim_path", return_value=root / "no-claim/claim.json"):
                coordinator.reconcile()
            self.assertEqual(gen_row["generation"], snapshot)
            self.assertEqual(len(coordinator.state["deferred_exceptions"]), 2)

            # Same terminal row cannot be chosen again, while independent work
            # remains eligible under the original selector and limits.
            pending = deepcopy(coordinator.state["rows"][2])
            pending["generation"] = {"status": "pending", "attempts": []}
            resident = {"session_capacity": 1, "active_claims": [],
                        "declaration": {"mode": "MATCH_PROJECT", "gpu_index": 6}}
            selected = base.select_pool_slot([gen_row, pending], {"mp": resident})
            self.assertIs(selected[0], pending)
            before = deepcopy(coordinator.state["rows"])
            coordinator.state["rows"][3]["generation"]["status"] = "pending"
            self.assertFalse(overlay.primary_terminal(coordinator.state["rows"]))
            coordinator.state["rows"] = before
            self.assertTrue(overlay.primary_terminal(coordinator.state["rows"]))
            marker = base.load_ref(coordinator.finish_primary())
            self.assertEqual(marker["status"], overlay.TERMINAL)
            self.assertFalse(marker["complete_benchmark_point_estimate"])
            self.assertEqual(marker["active_generation"] + marker["active_graders"], 0)
            self.assertEqual(len(base.load_ref(marker["queue_state_snapshot"])["rows"]), 1500)

            # Shared accounting ambiguity quarantines its resident, not another
            # resident. Unscoped integrity failure retains the original pause.
            coordinator.state["status"] = "running"
            with coordinator.context(gen_row):
                coordinator.pause("model_accounting_or_execution_unknown", {"synthetic": True})
            self.assertEqual(coordinator.state["status"], "running")
            self.assertEqual(set(coordinator.state["quarantined_residents"]), {"synthetic-mp"})
            coordinator.pause("controller_fault", {"type": "SharedIntegrityError"})
            self.assertEqual(coordinator.state["status"], "paused_technical_unknown")

            # Real original Coordinator.__init__ / validate_frozen runs before
            # any queue lock or state change; no fixture bypass for this gate.
            source = root / "original-frozen-source.py"
            source.write_text("original\n")
            old = overlay.reference(source)
            binding = put(root / "bindings.json", {"frozen_files": [
                {"reference": old, "stat": base.stat_id(source)}]})
            source.write_text("changed\n")
            policy = {"original_bindings": binding, "exception_root": str(root / "other")}
            with patch.object(overlay, "validate_policy", return_value=policy):
                with self.assertRaisesRegex(ValueError, "Immutable v054 candidate evidence changed"):
                    overlay.ResilientCoordinator({"synthetic": "policy"})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DeferredCPU)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"version": "v054-deferred-queue-cpu-control-r1", "passed": result.wasSuccessful(),
        "tests": result.testsRun, "synthetic_only": True, "model_calls": 0, "GPU_loads": 0,
        "formal_claims": 0, "official_scorer_calls": 0, "services_started_or_stopped": 0,
        "coverage": ["local_scoring_unknown_continues", "local_generation_unknown_continues",
            "terminal_inventory_not_complete_score", "unknown_never_replayed",
            "shared_accounting_quarantines_own_resident", "unscoped_fault_hard_stop",
            "original_constructor_source_integrity_gate"],
        "sources": [overlay.reference(Path(overlay.__file__)), overlay.reference(Path(__file__))]}
    (STAGE / "cpu-control.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
