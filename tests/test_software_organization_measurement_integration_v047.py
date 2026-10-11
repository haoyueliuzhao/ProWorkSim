"""Two new SDK-to-measurement CPU paths; synthetic owner is not model evidence."""
import copy

import pytest

from proworksim.storage import digest, json_bytes
from proworksim.software_context_v044 import SoftwareContextTransport
from proworksim.software_organization_runtime_v047 import collect_episode
from scripts import measure_organization_feedback_v047 as feedback
from scripts import measure_organization_work_v047 as work
from scripts import software_organization_stop_policy_v047 as stop
from tests.test_measure_organization_budget_v046 import capacity_binding
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v047 import cpu_collection


class ReceiptCPUOwner(CPUOwner):
    """No weights, tensors, actual tokenizer, RNG or GPU; explicit fixture metadata."""
    def __init__(self, script):
        super().__init__(script)
        self.capacity_receipt = capacity_binding()
        cap = self.capacity_receipt
        cap["fixture_only"] = True
        cap["original_recipe"] = copy.deepcopy(self.recipe)
        cap["capacity_recipe"] = {**self.recipe, "max_length": 18432}
        cap["original_recipe_sha256"] = digest(json_bytes(cap["original_recipe"]))
        cap["capacity_recipe_sha256"] = digest(json_bytes(cap["capacity_recipe"]))
        cap["original_actor_identity"]["policy_version"] = "synthetic-no-tensor-cpu-owner"
        cap["capacity_actor_identity"]["policy_version"] = "synthetic-no-tensor-cpu-owner"

    def freeze_identity(self):
        return copy.deepcopy(self.capacity_receipt["capacity_actor_identity"])

    def finish_evaluation_guard(self, before):
        value = super().finish_evaluation_guard(before)
        value.update(learning_before_sha256=digest(json_bytes(before)),
                     learning_after_sha256=digest(json_bytes(self.learning)),
                     rng_before_sha256=digest(b"no-rng-cpu-fixture"),
                     rng_after_restore_sha256=digest(b"no-rng-cpu-fixture"))
        return value


@pytest.mark.parametrize("condition,censored", [("I2", False), ("S1", True)])
def test_real_sdk_new_stage_or_administrative_close_is_measurable_without_old_window_false_positive(tmp_path, condition, censored):
    pytest.importorskip("openhands.sdk")
    script = ({"member_001": [action("finish_stage", reason="Candidate phase complete"),
                               action("staff_done", reason="Selection has no fixed candidate")],
               "member_002": [action("finish_stage", reason="Independent phase complete")]}
              if condition == "I2" else
              {"member_001": [action("work_note", key="current", text="Original CPU action before soft cutoff"),
                                action("staff_done", reason="This call must not start")]})
    owner, prepared, _, kwargs = cpu_collection(tmp_path, condition, script,
        after_call={1: 5401} if censored else None, owner_factory=ReceiptCPUOwner,
        # Exercise the frozen serialized protocol tag. The owner and every
        # returned token trace remain explicitly synthetic CPU fixtures.
        transport_factory=lambda owner, directory: SoftwareContextTransport(owner, directory))
    kwargs.update(soft_seconds=5400, hard_seconds=6000)
    folder = tmp_path / "actual" / "episodes" / condition
    folder.parent.parent.mkdir(parents=True, exist_ok=True)
    (folder.parent.parent / "capacity-binding.json").write_bytes(json_bytes(owner.capacity_receipt))
    result = collect_episode(owner, prepared, folder, **kwargs)
    measured = feedback.measure_episode(folder)
    assert measured["mechanism_gate_inputs"]["resolved"] is True, measured
    assert not measured["mechanism_gate_inputs"]["projection_violations"], measured
    (folder / "feedback-loop.json").write_bytes(json_bytes(measured))
    stage_work = work.measure_episode(folder)
    assert stage_work["status"] == "measured", stage_work
    assert stage_work["cost_accounting"]["status"] == "complete"
    assert stage_work["submission_costs"]["no_submission_terminal_cost_retained"]["calls"] == len(owner.transport.requests)
    assert stage_work["stage_accounting"]["passed"] is True
    assessment = stop.assess_episode(folder, row=result, feedback=measured)
    assert assessment["decision"] == "continue", assessment
    assert result["administrative_censoring"] is censored
    assert result["R_token"] == (None if censored else 0)
    reasons = measured["denominators"]["no_followup_reasons"]
    if censored:
        assert reasons == {"administrative_soft_deadline": 1}
    else:
        assert reasons.get("stage_boundary") == 1
        assert result["member_lifecycle"]["cumulative_births"] == 2
