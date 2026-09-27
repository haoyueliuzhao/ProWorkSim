"""Unequal review count must not silently increase its utility weight."""

from scripts.harness_learning_report_v017 import measures, lightweight_advantages


def test_primary_macro_and_saved_advantage_are_explicit():
    weights = dict.fromkeys(("implement", "review", "pair", "chain"), 0.25)
    rows = [
        {
            "slot_id": f"{task}-{i}",
            "task": task,
            "state": "closed_known",
            "reward": float(task == "review"),
            "completed": task == "review",
        }
        for task, count in [("implement", 6), ("review", 9), ("pair", 6), ("chain", 6)]
        for i in range(count)
    ]
    m = measures(rows, weights)
    assert m["mean_reward"] == 1 / 3 and m["primary_mean_reward"] == 0.25
    assert m["primary_completion_rate"] == 0.25
    rows[-1].update(state="closed_unknown", reward=None, completed=None)
    assert measures(rows, weights)["primary_mean_reward"] is None
    admission = {
        "decisions": [
            {
                "slot_id": "a",
                "task": "implement",
                "member_id": "implementer",
                "call_id": "c",
                "tokens": {"output_ids": [1, 2, 3]},
            }
        ]
    }
    actual = lightweight_advantages(
        admission,
        {"old_critic_values": [0], "advantages": [0.2]},
        {("implementer", "c"): "protocol_rejection"},
        [{"slot_id": "a", "reward": 0.2, "completed": False}],
    )
    assert actual["groups"][0]["action"] == "protocol_rejection"
    assert actual["groups"][0]["episode_outcome"] == "partial"
    assert actual["groups"][0]["positive_advantage_decisions"] == 1
    assert lightweight_advantages(admission, {}, {}, [])["status"] == "unavailable"
