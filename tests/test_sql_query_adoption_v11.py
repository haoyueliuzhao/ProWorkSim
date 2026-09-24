"""A query uses its exact adopted version despite newer unshared upstream drafts."""

import copy
import json

import pytest

from proworksim.core.world import WorldSpec
from proworksim.world_core import WorldCore


def table(value):
    return {
        "tables": {
            "input_table": {"columns": [{"name": "amount", "type": "BIGINT"}], "rows": [[value]]}
        }
    }


@pytest.mark.parametrize("policy", ["fixed", "current_published"])
def test_query_retains_exact_adoption_and_local_only_unbound_sources(tmp_path, policy):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "adopted-query",
            {"operator": {}, "producer": {}, "consumer": {}},
            applications=["files", "sql"],
            bootstrap_grants=[
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        ),
    )

    def call(actor, project, action, **arguments):
        response = world.session(actor, project).call(action, **arguments)
        assert response["ok"], response
        return response["result"]

    source = {
        "project_id": "A",
        "goal": "Provide exact versioned tables",
        "participants": ["producer"],
        "objects": [
            {
                "alias": "data",
                "filename": "data.json",
                "kind": "json",
                "owner": "producer",
                "readers": ["producer"],
                "data": table(0),
            }
        ],
        "grants": [
            {"actor_id": "producer", "power": power, "subject": "artifact"}
            for power in ["share", "publish"]
        ],
    }
    target = {
        "project_id": "B",
        "goal": "Query adopted public tables",
        "participants": ["consumer"],
        "objects": [
            {
                "alias": alias,
                "filename": alias + ".json",
                "kind": "json",
                "owner": "consumer",
                "readers": ["consumer"],
                "data": data,
            }
            for alias, data in [("query", {}), ("local", table(42))]
        ],
        "works": [
            {
                "work_id": wid,
                "owner": "consumer",
                "goal": "Inspect adopted data",
                "deliverables": ["query"],
                "requirements": {
                    "input_policy": policy,
                    "input_version": "v2",
                    "sql_project": {"query_alias": "query"},
                },
            }
            for wid in ["w", "other"]
        ],
        "grants": [
            {
                "actor_id": "consumer",
                "power": power,
                "subject": "artifact",
                "work_nodes": ["w", "other"],
            }
            for power in ["adopt", "execute_sql"]
        ],
    }
    call("operator", None, "install_project", package=source)
    call("operator", None, "install_project", package=target)
    oid = world.state["workspaces"]["A"]["data"]
    call("producer", "A", "write_object", alias="data", data=table(7))
    call(
        "producer",
        "A",
        "share",
        object_id=oid,
        version_id="v2",
        target_project="B",
        actor_ids=["consumer"],
        follow_updates=True,
    )
    call("producer", "A", "publish", alias="data", version_id="v2", target_projects=["B"])
    call(
        "consumer",
        "B",
        "adopt",
        alias="data",
        object_id=oid,
        version_id="v2",
        policy=policy,
        work_ids=["w"],
    )
    call("producer", "A", "write_object", alias="data", data=table(999))
    before = copy.deepcopy(world.state)
    consumer = world.session("consumer", "B")
    assert consumer.observe()["objects"][oid]["versions"] == ["v2"]
    query = call(
        "consumer",
        "B",
        "sql_query",
        work_id="w",
        source_alias="data",
        sql="SELECT SUM(amount) AS amount FROM input_table",
        output_alias="query",
    )
    assert query["execution_status"] == "success"
    assert query["tables"]["query_result"]["rows"] == [[7]]
    ref = query["reference"]
    artifact = world.state["artifacts"][ref["object_id"]]
    metadata = artifact["versions"][ref["version_id"]]
    result = json.loads(world.store.version_path(artifact, ref["version_id"]).read_text())
    exact = {"artifact_id": oid, "version_id": "v2"}
    assert metadata["derived_from"] == [exact]
    assert metadata["execution_provenance"]["source_reference"] == exact
    assert result["execution"] == metadata["execution_provenance"]
    assert world.state["knowledge"]["consumer"]["read_artifacts"][-1]["version_id"] == "v2"
    denied = consumer.call(
        "sql_query",
        work_id="other",
        source_alias="data",
        sql="SELECT * FROM input_table",
        output_alias="query",
    )
    assert denied["ok"] is False
    assert denied["error"]["rejection"]["code"] == "sql_query_source_binding_required"
    # No shared binding is borrowed from another work, and no ACL/share changes.
    assert world.state["shares"] == before["shares"]
    assert world.state.get("access_grants", []) == before.get("access_grants", [])
    assert world.state["artifacts"][oid] == before["artifacts"][oid]
    assert world.state["adoptions"] == before["adoptions"]
    assert consumer.call("read_object", alias="data", version_id="v3")["ok"] is False
    local = call(
        "consumer",
        "B",
        "sql_query",
        work_id="other",
        source_alias="local",
        sql="SELECT amount FROM input_table",
        output_alias="query",
    )
    assert local["tables"]["query_result"]["rows"] == [[42]]
