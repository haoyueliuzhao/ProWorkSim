"""Regression controls with the native public-test and work-epoch contracts."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import os
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_review_handoff_v243_1 as trial

sys.path.insert(0, str(trial.ROOT / "tests"))
import test_organization_world_v213 as fixture
from proworksim.software_fixed_organization_clone_v131 import clone_function as clone
from proworksim.software_review_handoff_v243_1 import current_target, Execution, ReviewWorld
from proworksim.tool_outcomes import ToolRejection
from proworksim.storage import read_json


def main():
    M1, M2 = fixture.M1, fixture.M2

    from run_offline_scorer_v096 import launch_spec

    def clean(argv, **kw):
        command, kw["env"] = launch_spec(argv[1:], inherited=kw["env"])
        r = subprocess.run(command, **kw)
        if r.returncode:
            raise RuntimeError((r.stdout + r.stderr)[-1500:])
        return r

    sub = fixture.substrate
    real = clone(
        sub,
        {
            **sub.__globals__,
            "sys": SimpleNamespace(executable=str(trial.ROOT / ".venv/bin/python")),
            "subprocess": SimpleNamespace(run=clean),
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        p, _, call, _ = clone(fixture.prepare, {**fixture.prepare.__globals__, "substrate": real})(
            Path(tmp)
        )
        w = p.world
        fixture.split(call)
        fixture.setup(call, "behavior")
        ok, no = fixture.ok, fixture.no
        order = dict(task="behavior", actor=M2, recipient=M1)

        def publish(text):
            ok(call, M1, "begin_work", task_id="behavior")
            ok(call, M1, "write_file", path="sample.py", text=text)
            ok(call, M1, "run_tests")
            patch = ok(call, M1, "fix_patch", task_ids=["behavior"], message="Current code")[
                "patch_id"
            ]
            ok(call, M1, "complete_work", task_id="behavior", patch_id=patch)
            return patch

        original = publish("value = 2\n")
        first = current_target(w, order)
        assert first["patch"] == original and first["status"] == "review_current"
        ok(call, M2, "open_patch_review", patch_id=original)
        ok(call, M2, "run_patch_review_tests", patch_id=original)
        ok(call, M1, "reopen_work", task_id="behavior", reason="Change candidate")
        waiting = current_target(w, order)
        assert waiting["patch"] is None
        no(
            call,
            M2,
            "org_review_patch",
            "stale_work_revision",
            patch_id=original,
            decision="accept",
            reason="Stale result",
        )
        new = publish("value = 1 + 1\n")
        next_target = current_target(w, order)
        assert next_target["patch"] == new and first["version"] != next_target["version"]
        ok(call, M2, "open_patch_review", patch_id=new)
        # Fresh public evidence is required even when the replaced candidate passed.
        rejected = call(
            M2,
            "org_review_patch",
            patch_id=new,
            decision="accept",
            reason="Missing fresh verification",
        )
        assert not rejected["ok"], rejected
        ok(call, M2, "run_patch_review_tests", patch_id=new)
        verdict = ok(
            call, M2, "org_review_patch", patch_id=new, decision="accept", reason="Freshly verified"
        )
        assert verdict["identity"]["source_reference"] == next_target["version"]
        assert current_target(w, {**order, "actor": M1})["status"] == "assignment_changed"
    ex = object.__new__(Execution)
    ex.grants = [("inspect_handoff", M1), ("publish_artifact", M2), ("delivery", M1)]
    assert ex.expedite("publish_artifact", M2) and ex.grants == [
        ("new_duty", M2),
        ("inspect_handoff", M1),
        ("delivery", M1),
    ]
    assert not ex.expedite("publish_artifact", M2)
    exhausted = w
    exhausted.__class__ = ReviewWorld
    exhausted.live_members = lambda: [M1, M2]
    exhausted.member_availability = lambda: {M2: {"can_receive_work": False}}
    try:
        exhausted._available_recipient(M1, M2)
    except ToolRejection as exc:
        assert exc.rejection["code"] == "recipient_budget_unavailable"
    else:
        raise AssertionError("Budget-exhausted recipient accepted")
    trial.event.save(
        trial.PLAN / "cpu-controls.json",
        dict(
            original=first,
            reopened=waiting,
            new=next_target,
            stale_rejected=True,
            fresh_test_required=True,
            new_version_accepted=True,
            role_change_invalidates=True,
            existing_credit_reordered_once=True,
            budget_exhaustion_explicit=True,
            provider_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
