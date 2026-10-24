"""Fresh budget-condition scoring must reject another condition's candidate."""
import os
import sys
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scorer_v056 as scorer
from proworksim.software_benchmark_candidates_v054 import write_new


def test_candidate_condition_and_cpu_identity_are_enforced_before_scoring(tmp_path, monkeypatch):
    manifest = write_new(tmp_path / "manifest.json", {"synthetic_metadata": True})
    monkeypatch.setattr(scorer, "installation_manifest", lambda: {"synthetic_metadata": True})
    patch = write_new(tmp_path / "patch.json", {"synthetic_patch": True})
    slot = {"arm": "REF", "slot_id": "synthetic-task-budget-a", "instance_id": "synthetic-task",
            "condition_id": "REF_B0500K"}
    candidate = write_new(tmp_path / "candidate.json", {
        "version": "software-benchmark-native-closure-v054", "lock_before_grading": True,
        "slot": slot, "tree_sha256": "a" * 64,
        "patch_receipt": {"base_tree_sha256": "b" * 64, "patch": patch},
    })
    cpus = sorted(os.sched_getaffinity(0))[:4]
    assert len(cpus) == 4
    request = {"arm": "REF", "condition_id": slot["condition_id"], "model": "Qwen/Qwen3.5-9B",
        "thinking": True, "endpoint": "code", "attempt": 1, "preparation_only": False,
        "actor_feedback": False, "limits": scorer.LIMITS, "scorer_manifest": manifest,
        "native_candidate_lock": candidate, "instance_id": slot["instance_id"],
        "slot_id": slot["slot_id"], "candidate_tree_sha256": "a" * 64,
        "baseline_tree_sha256": "b" * 64, "patch": patch,
        "scoring_cpuset_cpus": ",".join(map(str, cpus))}
    scorer.validate_request(request)
    with pytest.raises(ValueError, match="budget condition"):
        scorer.validate_request(dict(request, condition_id="REF_B2000K"))
    with pytest.raises(ValueError, match="four distinct"):
        scorer.validate_request(dict(request, scoring_cpuset_cpus=str(cpus[0])))
    with pytest.raises(ValueError, match="fresh planned"):
        scorer.validate_request(dict(request, actor_feedback=True))


def test_cleanup_only_stops_exact_owned_containers_and_retains_ambiguous_create(monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", SimpleNamespace(errors=SimpleNamespace(NotFound=KeyError)))
    calls = []

    class Container:
        id = "owned-container"
        attrs = {"State": {"Running": True}}

        def reload(self):
            return None

        def stop(self, timeout):
            calls.append(("stop", self.id, timeout))
            self.attrs = {"State": {"Running": False}}

        def remove(self, force):
            calls.append(("remove", self.id, force))

    container = Container()

    def get(identity):
        assert identity == container.id
        return container

    client = SimpleNamespace(containers=SimpleNamespace(get=get), close=lambda: None)
    tracking = {"owned_container_ids": [container.id], "create_result_unknown": False,
                "client": client, "phase": "official_scoring_returned"}
    result = scorer.cleanup_scoring({"slot_id": "one", "condition_id": "REF_B0500K"}, tracking)
    assert result["quiescent"] and calls == [("stop", container.id, 10), ("remove", container.id, False)]
    ambiguous = {"owned_container_ids": [], "create_result_unknown": True, "client": None, "phase": "create"}
    assert scorer.cleanup_scoring({}, ambiguous)["quiescent"] is False
    before = {"owned_container_ids": [], "create_result_unknown": False, "client": None, "phase": "before_admission"}
    assert scorer.cleanup_scoring({}, before)["quiescent"] is True
