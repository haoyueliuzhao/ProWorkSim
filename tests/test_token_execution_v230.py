import pytest

from proworksim.software_context_builder_v230 import build, recover_observations, worker_graph
from proworksim.software_trajectory_v230 import ProjectedEndpoint, Trajectory
from proworksim.storage import digest, json_bytes, read_json

A, B = "member_001", "member_002"


def wire():
    return {
        "messages": [{"role": "system", "content": "stable"}, {"role": "user", "content": "task"}],
        "tools": [{"function": {"name": "read_file"}}],
        "max_tokens": 50,
    }


def test_deltas_restore_repeated_messages_deletions_and_disjoint_private_history():
    w = wire()
    for values in [
        {"actor_id": A, "messages": [{"message_sequence": 4, "body": "same"}], "file": "one"},
        {
            "actor_id": A,
            "messages": [{"message_sequence": 4, "body": "same"}, {"message_sequence": 9}],
        },
    ]:
        w["messages"].append(
            {"role": "user", "content": json_bytes({"observation": values}).decode()}
        )
    projected, manifest = build(w, actor=A, role="worker")
    assert recover_observations(projected) == recover_observations(w)
    assert manifest["message_refs"] == [[3, "messages", 0, [2, "messages", 0]]]
    assert build(w, actor=A, role="worker", condition="T0")[0] == w
    with pytest.raises(ValueError, match="private observation"):
        build(w, actor=B, role="worker")
    with pytest.raises(ValueError, match="controller"):
        build(w, actor=A, role="osa")


def test_graph_dependency_and_peer_permissions():
    def work(owner, reviewer=None, deps=()):
        return dict(owner=owner, reviewer=reviewer, depends_on=list(deps), children=[])

    graph = {
        "members": [A, B],
        "work": {"mine": work(A, deps=["dep"]), "dep": work(B), "peer": work(B)},
        "duties": {},
        "collaboration": [],
    }
    assert set(worker_graph(graph, A)["work"]) == {"mine", "dep"}
    assert set(worker_graph(graph, B)["work"]) == {"dep", "peer"}


def test_endpoint_archives_before_dispatch_and_never_replays_after_uncertain_reply(
    tmp_path, monkeypatch
):
    archive = tmp_path / "wire"
    trace = Trajectory(tmp_path / "trace.sqlite", "task", "branch")
    actual = []

    def backend(route, payload):
        if route.startswith("/tokenize"):
            return {
                "prompt_tokens": 80,
                "request_sha256": digest(json_bytes(payload["wire"])),
                "method": "fixture",
            }
        assert list(archive.glob("*/manifest.json"))
        actual.append(payload["request_id"])
        if payload["request_id"] == "lost":
            raise OSError("response lost")
        return {"id": "returned", "usage": {"prompt_tokens": 80}}

    ep = ProjectedEndpoint(backend, archive, trace, "T1")
    p = {
        "wire": wire(),
        "member_id": A,
        "team_slot_id": "branch",
        "request_id": "lost",
        "usage_id": "agent",
    }
    with pytest.raises(OSError, match="response lost"):
        ep.post("/chat/completions", p)
    with pytest.raises(FileExistsError):
        ep.post("/chat/completions", p)
    assert actual == ["lost"]
    real = trace.event

    def fault(kind, *args, **kwargs):
        if kind == "response":
            raise OSError("observation failure")
        return real(kind, *args, **kwargs)

    monkeypatch.setattr(trace, "event", fault)
    response = ep.post("/chat/completions", {**p, "request_id": "ok"})
    assert response["id"] == "returned" and actual == ["lost", "ok"]
    assert read_json(trace.path.with_suffix(".incomplete.json"))["errors"] == [
        "observation failure"
    ]


def test_controller_does_not_accept_a_worker_conversation():
    w = wire()
    w["tools"] = [{"function": {"name": "activate_organization"}}]
    view = {"graph": {}, "evidence": {"E1": 1}, "options": {"K": {}}, "anomaly_id": "a"}
    w["messages"][1]["content"] = json_bytes(view).decode()
    assert build(w, actor=A, role="osa")[0]["tools"] == w["tools"]
    w["messages"][1]["content"] = json_bytes({**view, "private_worker_history": "hidden"}).decode()
    with pytest.raises(ValueError, match="controller view"):
        build(w, actor=A, role="osa")


def test_cached_pages_recheck_actor_and_version_and_emit_real_read_receipts():
    from proworksim.software_graph_execution_v230 import World

    class Fixture:
        actor = A
        version = "v1"
        receipts = 0

        def _bundle(self, actor, patch_id=None):
            if actor != self.actor:
                raise PermissionError(actor)
            return (
                {"artifact_id": "project", "versions": {self.version: {"sha256": self.version}}},
                self.version,
                {"file": self.version},
            )

        def _text_entry(self, bundle, path):
            return bundle[path]

        def _event(self, actor, kind, **kwargs):
            assert actor == self.actor and kind == "read"
            self.receipts += 1

    fixture = Fixture()

    def read(member):
        return World._action_read_file(fixture, member, "project", "file")["text"]

    assert read(A) == read(A) == "v1"
    assert fixture.read_page_hits == 1 and fixture.receipts == 2
    fixture.actor = B
    with pytest.raises(PermissionError):
        read(A)
    assert read(B) == "v1" and fixture.read_page_hits == 1
    fixture.version = "v2"
    assert read(B) == "v2" and fixture.receipts == 4
