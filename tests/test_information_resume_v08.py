"""Provider recovery before an old reply must not strand the current obligation."""

from proworksim.core.world import WorldSpec
from proworksim.world_core import WorldCore
from scripts.continuous_worker_experiment import package


def test_new_availability_supersedes_pending_old_route_condition(tmp_path):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "route-overlap",
            {"alice": {}, "bob": {}, "manager": {}},
            bootstrap_grants=[
                {"actor_id": "manager", "power": "install_project", "scope": "world"}
            ],
        ),
    )
    payload = package("A", mode="unavailable")
    payload["information_routes"][0]["delay"] = 10
    manager = world.session("manager")
    assert manager.call("install_project", package=payload)["ok"]
    assert manager.call("install_project", package=package("B"))["ok"]
    worker = world.session("alice", "A")
    old = worker.call("request_information", route_id="facts", work_id="work-1")["result"]
    assert world.session("manager", "A").call(
        "set_information_availability",
        route_id="facts",
        available=True,
        reason="New information arrived before the old acknowledgement",
    )["ok"]
    new = worker.call("request_information", route_id="facts", work_id="work-1")["result"]
    assert worker.call("wait", ticks=10)["ok"]
    state = world.store.load()
    assert state["condition_specs"][old["condition_id"]]["status"] == "superseded"
    assert state["condition_specs"][new["condition_id"]]["status"] == "resolved"
    assert state["requests"][old["request_id"]]["status"] == "unavailable"
    assert len(state["raw_condition_responses"]) == 2
    assert worker.observe()["work_items"]["A::work-1"]["status"] == "open"
    assert state["work_items"]["B::work-1"]["submissions"] == []
