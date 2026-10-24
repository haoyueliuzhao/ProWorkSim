"""Public-only task guidance and hard recovery boundaries."""
import copy

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_native_execution_v057 import prepare_public_guidance, recovery_admission


def test_public_projection_excludes_private_material_and_rejects_unadmitted_entry(tmp_path):
    mapping = write_new(tmp_path / "mapping.json", {
        "instance_id": "synthetic", "public_python": "/testbed/python",
        "private_scoring": "NEVER_VISIBLE_GOLD"})
    entry = {"instance_id": "synthetic", "repo": "synthetic/repo", "admitted": True,
        "source": "public_repository", "hidden_material_used": False, "cwd": "/testbed",
        "selection": "repository-wide public default; no answer-derived files or task-result selection",
        "baseline_mapping": mapping, "public_python": "/testbed/python",
        "argv": ["/testbed/python", "bin/test"], "unprojected_metadata": "NEVER_VISIBLE_GOLD"}
    registry = write_new(tmp_path / "registry.json", {"planned_tasks": 500, "entries": [entry]})
    result = prepare_public_guidance({"instance_id": "synthetic", "repo": "synthetic/repo"},
        registry_reference=registry, baseline_mapping_reference=mapping)
    assert "bin/test" in result["visible_text"] and "NEVER_VISIBLE" not in result["visible_text"]
    bad = write_new(tmp_path / "bad.json", {"planned_tasks": 500, "entries": [entry | {"hidden_material_used": True}]})
    with pytest.raises(ValueError, match="hidden tests"):
        prepare_public_guidance({"instance_id": "synthetic", "repo": "synthetic/repo"},
            registry_reference=bad, baseline_mapping_reference=mapping)


def test_correction_admission_never_replenishes_or_hides_unknown_usage():
    limits = {"input_plus_output_tokens": 500000, "all_model_attempts": 512, "agent_decisions": 512}
    base = {"token_limit": 500000, "all_model_attempt_limit": 512, "agent_decision_limit": 512,
        "known_actual_tokens": 1234, "complete_actual_tokens": 1234,
        "inflight": None, "uncertain_reserved_tokens": 0, "attempts": 4, "decisions": 4}
    prior = copy.deepcopy(base)
    start = {"started": 1, "soft_at": 100, "hard_at": 120}
    assert recovery_admission(base, started=start, limits=limits, now=50) is None
    cases = [({"attempts": 512}, "model_attempt_limit"),
             ({"decisions": 512}, "agent_decision_limit"),
             ({"known_actual_tokens": 500000 - 32768}, "no_room_for_complete_output_reservation"),
             ({"complete_actual_tokens": None}, "uncertain_model_usage"),
             ({"inflight": {"id": 1}}, "uncertain_model_usage"),
             ({"uncertain_reserved_tokens": 1}, "uncertain_model_usage")]
    for changed, expected in cases:
        assert recovery_admission(base | changed, started=start, limits=limits, now=50) == expected
    assert recovery_admission(base, started=start, limits=limits, now=100) == "episode_deadline"
    assert base == prior
    with pytest.raises(ValueError, match="original episode limits"):
        recovery_admission(base, started=start, limits=limits | {"agent_decisions": 1024}, now=50)
