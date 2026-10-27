"""Synthetic internal transfer tests: no Docker, model, process or public test."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import time

import pytest

from proworksim import software_benchmark_managed_actor_v064 as actor
from proworksim.repository_sources_v054 import normalize_policy, tree_manifest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("project_controller_upload_fixture", ROOT / "tools/run_project_controller_v064.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def payload_fixture(text="original\n", *, hard_at):
    metadata = {"old.txt": {"kind": "file", "encoding": "utf-8", "mode": "100644"}}
    baseline = {"files": {"old.txt": text}, "entry_metadata": metadata, "file_policy": normalize_policy()}
    files = {"new.txt": text[:-1] + " changed 汉字\n"}
    new_metadata = {"new.txt": metadata["old.txt"]}
    request = {"instance_id": "fixture", "source_reference": {"object_id": "fixture", "version_id": "v2"},
               "tree_sha256": tree_manifest(files, new_metadata)["tree_sha256"],
               "hard_deadline_monotonic": hard_at, "hidden_evaluation": False, "arbitrary_command": False}
    return baseline, actor.make_delta(baseline, files, new_metadata, request=request), files


def ready():
    return {"version": actor.VERSION, "implementation": "v064-private-docker-managed-worker-r1",
            "managed_operations": ["managed_public_test", "sync_terminal"],
            "managed_upload_protocol": actor.upload_protocol(),
            "isolation": {"pid": 1, "capabilities_all_zero": True, "no_new_privileges": True, "dumpable": False}}


class InMemoryActorWire:
    """Parse the actual compact controller wire and use the real chunk receiver."""
    def __init__(self, receiver, baseline):
        self.receiver, self.baseline = receiver, baseline
        self.response, self.frame_sizes, self.operations = None, [], []

    def write(self, wire):
        assert wire.endswith("\n") and wire.count("\n") == 1
        self.frame_sizes.append(len(wire.encode("utf-8")))
        assert self.frame_sizes[-1] <= actor.MAX_RPC_BYTES
        value = json.loads(wire)
        name, action = value["tool"], value["action"]
        if name == actor.UPLOAD_BEGIN:
            result = self.receiver.begin(action)
            self.response = {"type": "observation", "id": value["id"], "tool": name, "result": result}
        elif name == actor.UPLOAD_CHUNK:
            assert self.operations == []
            result = self.receiver.chunk(action)
            self.response = {"type": "observation", "id": value["id"], "tool": name, "result": result}
        else:
            assert name == actor.UPLOAD_COMMIT and not self.operations
            operation, payload, receipt = self.receiver.commit(action)
            candidate = actor.reconstruct_delta(self.baseline, payload)
            self.operations.append((operation, candidate))
            self.response = {"type": "observation", "id": value["id"], "tool": operation,
                             "result": {"tree_sha256": candidate["tree_sha256"]},
                             "upload_receipt": {**receipt, "operation_executed": True}}
        return len(wire)

    def flush(self):
        pass


def test_large_replace_and_rename_cross_32m_without_new_model_operation(tmp_path):
    deadline = time.monotonic() + 120
    baseline, payload, files = payload_fixture("x" * (33 * 1024**2) + "\n", hard_at=deadline)
    receiver = actor.ManagedUploadReceiver(tmp_path / "actor-private", hard_at=deadline)
    wire = InMemoryActorWire(receiver, baseline)
    rpc = controller.ManagedRPC(ready(), reader=io.StringIO(), writer=wire,
                                directory=tmp_path / "controller-private", hard_at=deadline)
    rpc.receive = lambda: wire.response
    result = rpc.request("sync_terminal", payload)
    assert len(wire.operations) == 1 and wire.operations[0][0] == "sync_terminal"
    assert wire.operations[0][1]["files"] == files
    assert result["tree_sha256"] == payload["candidate_tree_sha256"]
    assert len(wire.frame_sizes) > 34 and max(wire.frame_sizes) < 2 * 1024**2
    assert receiver.pending is None and not receiver.failed
    assert list((tmp_path / "actor-private").iterdir()) == []
    assert list((tmp_path / "controller-private/upload-staging").iterdir()) == []
    logged_chunks = [json.loads(path.read_bytes()) for path in rpc.directory.glob("*-request.json")
                     if actor.UPLOAD_CHUNK in path.read_text()]
    assert logged_chunks and all("data_base64" not in row["action"] for row in logged_chunks)
    assert all(row["chunk_bytes_in_log"] is False and row["wire_sha256"] for row in logged_chunks)


def test_order_replay_hash_and_incomplete_commit_are_sticky_unknown(tmp_path):
    now = [10.0]
    _, payload, _ = payload_fixture(hard_at=100.0)
    with actor.prepare_payload_upload(payload, "managed_public_test", directory=tmp_path / "sender",
                                      hard_at=100.0, clock=lambda: now[0]) as (manifest, stream):
        chunks = list(actor.upload_chunks(manifest, stream, clock=lambda: now[0]))
    commit = {key: manifest[key] for key in ("version", "upload_id", "payload_bytes", "payload_sha256")}
    for mode in ("order", "chunk_hash", "incomplete", "total_hash", "duplicate", "concurrent", "replay"):
        receiver = actor.ManagedUploadReceiver(tmp_path / mode, hard_at=100.0, clock=lambda: now[0])
        admitted = copy.deepcopy(manifest)
        if mode == "total_hash":
            admitted["payload_sha256"] = "0" * 64
        receiver.begin(admitted)
        with pytest.raises(actor.ManagedTransferError) as failure:
            if mode in {"order", "chunk_hash"}:
                bad = copy.deepcopy(chunks[0])
                bad["index" if mode == "order" else "sha256"] = 1 if mode == "order" else "0" * 64
                receiver.chunk(bad)
            elif mode == "incomplete":
                receiver.commit(commit)
            elif mode == "concurrent":
                receiver.begin(manifest)
            else:
                for chunk in chunks:
                    receiver.chunk(chunk)
                if mode == "duplicate":
                    receiver.chunk(chunks[0])
                elif mode == "total_hash":
                    receiver.commit({**commit, "payload_sha256": "0" * 64})
                else:
                    receiver.commit(commit)
                    receiver.begin(manifest)
        assert failure.value.classification == "interface_unknown"
        assert receiver.failed and receiver.pending is None
        assert list((tmp_path / mode).iterdir()) == []


def test_declared_size_deadline_and_wrong_ack_cannot_dispatch_an_operation(tmp_path):
    now = [10.0]
    _, payload, _ = payload_fixture(hard_at=100.0)
    with actor.prepare_payload_upload(payload, "sync_terminal", directory=tmp_path / "sender",
                                      hard_at=100.0, clock=lambda: now[0]) as (manifest, stream):
        chunk = next(actor.upload_chunks(manifest, stream, clock=lambda: now[0]))
    receiver = actor.ManagedUploadReceiver(tmp_path / "over-limit", hard_at=100.0, clock=lambda: now[0])
    bad = {**manifest, "payload_bytes": actor.MAX_UPLOAD_BYTES + 1,
           "chunks": (actor.MAX_UPLOAD_BYTES + actor.UPLOAD_CHUNK_BYTES) // actor.UPLOAD_CHUNK_BYTES}
    with pytest.raises(actor.ManagedTransferError):
        receiver.begin(bad)
    assert receiver.pending is None and list((tmp_path / "over-limit").iterdir()) == []
    receiver = actor.ManagedUploadReceiver(tmp_path / "expired", hard_at=100.0, clock=lambda: now[0])
    receiver.begin(manifest)
    now[0] = 101.0
    with pytest.raises(actor.ManagedTransferError, match="deadline"):
        receiver.chunk(chunk)
    assert receiver.pending is None
    deadline = time.monotonic() + 60
    _, payload, _ = payload_fixture(hard_at=deadline)
    rpc = controller.ManagedRPC(ready(), reader=io.StringIO(), writer=io.StringIO(),
                                directory=tmp_path / "bad-ack", hard_at=deadline)
    calls = []
    def bad_exchange(value, expected):
        calls.append(value["tool"])
        return {"tool": actor.UPLOAD_BEGIN, "result": {"accepted": True, "upload_id": "wrong"}}
    rpc.exchange = bad_exchange
    with pytest.raises(actor.ManagedTransferError, match="acknowledge"):
        rpc.request("sync_terminal", payload)
    assert calls == [actor.UPLOAD_BEGIN] and rpc.failed
    assert list((tmp_path / "bad-ack/upload-staging").iterdir()) == []
