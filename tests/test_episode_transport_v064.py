import copy
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_episode_v064 as episode
from proworksim import software_benchmark_docker_actor_v064 as actors
from proworksim import software_benchmark_ref_resident_v064 as residents
from proworksim import software_benchmark_archive_storage_v064 as archives
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tar_bytes(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    return stream.getvalue()


def test_streamed_controller_archive_extracts_only_needed_records_without_rewriting(tmp_path):
    raw_json = b'{"path":"/pws/output/model-ledger/ledger.json","message":"unchanged"}\n'
    payloads = {"output/controller-result.json": raw_json,
                "output/model-ledger/ledger.json": b'{"known_actual_tokens":123}\n',
                "output/managed-world/history.json": b'old world history\n'*900,
                "output/managed-runtime/history.json": b'full runtime history\n'*900}
    raw = tar_bytes(payloads)
    storage = archives.export_compressed_stream(
        (raw[i:i+257] for i in range(0, len(raw), 257)), tmp_path / "controller.zst",
        allowed_root=tmp_path, codec_manifest=reference(archives.CODEC_MANIFEST))
    output = tmp_path / "extracted"
    result = episode.extract_controller_output(None, output, archive_storage=storage, arm="PROJECT")
    assert (output / "controller-result.json").read_bytes() == raw_json
    assert (output / "model-ledger/ledger.json").read_bytes() == payloads["output/model-ledger/ledger.json"]
    assert not (output / "managed-world").exists() and not (output / "managed-runtime").exists()
    assert result["archive_only_entries"] == 2 and result["complete_archive_roundtrip_verified"] is True
    assert result["raw_json_references_rewritten"] is False
    assert not list(tmp_path.rglob("*.tar"))
    assert storage["round_trip_verified"] is False  # No receipt silently mutates in place.


def test_controller_reference_relocation_rejects_wrong_roots_and_symlink_escape(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    path = output / "record.json"
    path.write_bytes(b'{"container_ref":"/pws/output/original"}\n')
    container_ref = {**reference(path), "path": "/pws/output/record.json"}
    assert episode.controller_ref(container_ref, output) == reference(path)
    before = path.read_bytes()
    for bad in ("relative.json", "/pws/output/../record.json", "/pws/output-other/record.json", "/pws/output"):
        with pytest.raises(ValueError):
            episode.controller_ref({**container_ref, "path": bad}, output)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "other.json"
    secret.write_text("other data")
    (output / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        episode.controller_ref({**reference(secret), "path": "/pws/output/escape/other.json"}, output)
    assert path.read_bytes() == before and secret.read_text() == "other data"


def claim(tmp_path, role, *, diagnostic=False, diagnostic_index=1):
    key = f"diagnostic-{diagnostic_index}-{role}" if diagnostic else role+"-0"
    body = {"key": key, "docker_name": "pws-v064-"+role,
            "spec": {"role": role, "slot_id": "v064:slot", "instance_id": "task", "image_id": "sha256:"+"a"*64}}
    if diagnostic:
        body["spec"].update(diagnostic=True, diagnostic_index=diagnostic_index)
    return write_new(tmp_path / (key+".json"), body), body


class FakeObject:
    def __init__(self, role, ref, body):
        self.id, self.removed, self.stopped = "owned-"+role, False, False
        if role == "volume":
            self.attrs = {"Name": body["docker_name"], "Driver": "local", "Options": {},
                          "Labels": actors.labels_for(ref, body)}
        else:
            self.attrs = {"Name": "/"+body["docker_name"], "Image": body["spec"]["image_id"],
                          "Config": {"Labels": actors.labels_for(ref, body)}, "State": {"Running": False, "Pid": 0}}
    def reload(self):
        pass
    def stop(self, timeout):
        self.stopped = True
        self.attrs["State"] = {"Running": False, "Pid": 0}
    def remove(self, force):
        assert force is False
        self.removed = True


@pytest.mark.parametrize("uncreated", ["actor", "controller"])
def test_cleanup_releases_claims_proven_not_created(tmp_path, monkeypatch, uncreated):
    actor_ref, actor_body = claim(tmp_path, "actor")
    pair = actors.OwnedActorPair(object(), slot_index=0, slot_id="v064:slot", instance_id="task",
                                 actor_reservation=actor_ref)
    roles = ("volume",) if uncreated == "actor" else ("volume", "controller")
    for role in roles:
        ref, body = claim(tmp_path, role)
        pair.claims[role], pair.claim_bodies[role] = ref, body
        if role != uncreated:
            pair.objects[role] = FakeObject(role, ref, body)
    if uncreated == "controller":
        pair.objects["actor"] = FakeObject("actor", actor_ref, actor_body)
    released = []
    monkeypatch.setattr(actors.policy, "release_resource", lambda ref, **kwargs: released.append(ref["path"]) or True)
    result = pair.cleanup()
    assert result["quiescent"] is True and result["proven_uncreated_claim_roles"] == [uncreated]
    assert set(released) == {ref["path"] for ref in pair.claims.values()}


def test_unknown_create_keeps_every_capacity_claim_even_without_an_object(tmp_path, monkeypatch):
    ref, body = claim(tmp_path, "actor")
    pair = actors.OwnedActorPair(object(), slot_index=0, slot_id="v064:slot", instance_id="task", actor_reservation=ref)
    pair.unknown_create.add("actor")
    monkeypatch.setattr(actors.policy, "release_resource", lambda *_args, **_kwargs: pytest.fail("Unknown creation cannot release its lease"))
    result = pair.cleanup()
    assert result["quiescent"] is False and result["create_result_unknown"] is True
    assert result["proven_uncreated_claim_roles"] == []


def test_retaining_controller_preserves_its_owned_volume_but_releases_quiet_capacity(tmp_path, monkeypatch):
    pair = actors.OwnedActorPair(object(), slot_index=0, slot_id="v064:slot", instance_id="task")
    for role in ("actor", "controller", "volume"):
        ref, body = claim(tmp_path, role)
        pair.claims[role], pair.claim_bodies[role] = ref, body
        pair.objects[role] = FakeObject(role, ref, body)
    released = []
    monkeypatch.setattr(actors.policy, "release_resource", lambda ref, **kwargs: released.append(ref["path"]) or True)
    result = pair.cleanup(preserve_controller=True)
    assert result["quiescent"] is True and result["all_owned_objects_removed"] is False
    assert {item["role"] for item in result["retained_objects"]} == {"controller", "volume"}
    assert pair.objects["actor"].removed and not pair.objects["controller"].removed
    assert not pair.objects["volume"].removed and len(released) == 3


def test_diagnostic_preclaim_uses_current_actor_role_and_exact_diagnostic_tag(tmp_path):
    ref, body = claim(tmp_path, "actor", diagnostic=True)
    pair = actors.OwnedActorPair(object(), slot_index=0, slot_id="v064:slot", instance_id="task",
        diagnostic=True, diagnostic_index=1, actor_reservation=ref)
    assert pair.actor_reservation_unused
    for name, changes in (("wrong_index", {"diagnostic_index": 2}), ("wrong_flag", {"diagnostic": False})):
        wrong = copy.deepcopy(body)
        wrong["spec"].update(changes)
        bad = write_new(tmp_path / (name+".json"), wrong)
        with pytest.raises(ValueError, match="another planned pair"):
            actors.OwnedActorPair(object(), slot_index=0, slot_id="v064:slot", instance_id="task",
                diagnostic=True, diagnostic_index=1, actor_reservation=bad)


@pytest.mark.parametrize("failure", ["mkdir", "intent"])
def test_episode_setup_failure_releases_only_the_precreated_capacity_claim(tmp_path, monkeypatch, failure):
    batch = tmp_path / "batch"
    row = {"slot_index": 0, "slot_id": "v064:slot", "source_slot_id": "old", "execution_arm": "REF",
           "replicate": 0, "arm": "REF", "model_key": "QWEN", "group_id": "group", "configuration": {},
           "condition_id": "condition", "instance_id": "task", "seed": 1}
    monkeypatch.setattr(episode, "BATCH", batch)
    monkeypatch.setattr(episode, "_row_and_config", lambda *_: ({}, {}, {}))
    monkeypatch.setattr(episode, "wait_capacity", lambda *_: {"admit": True})
    reserved, released = {"claim": "only-owned-actor-capacity"}, []
    monkeypatch.setattr(episode.policy, "claim_resource", lambda key: reserved)
    monkeypatch.setattr(episode.policy, "release_resource", lambda ref, **kwargs: released.append((ref, kwargs)) or True)
    if failure == "mkdir":
        original = Path.mkdir
        def mkdir(path, *args, **kwargs):
            if path == batch / "episodes/0":
                raise PermissionError("fixture-only mkdir failure")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "mkdir", mkdir)
    else:
        monkeypatch.setattr(episode, "write_new", lambda *_: (_ for _ in ()).throw(OSError("fixture-only intent failure")))
    with pytest.raises(OSError):
        episode._run(row, None)
    assert released == [(reserved, {"quiescent": True})]


def test_authoritative_local_usage_is_saved_before_forward_and_not_invented(tmp_path, monkeypatch):
    body = {"id": "actual-response", "model": "raw-qwen", "usage": {
        "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}
    delegate = SimpleNamespace(post=lambda *_: body)
    wrapped = episode.HostUsageTransport(delegate, tmp_path / "usage", "v064:slot")
    returned = wrapped.post("/v1/chat/completions", {"messages": []})
    saved = json.loads((tmp_path / "usage/0001.json").read_bytes())
    assert returned is body and saved["usage"] == body["usage"]
    assert saved["before_controller_forward"] is True and saved["usage_valid"] is True
    missing = episode.HostUsageTransport(SimpleNamespace(post=lambda *_: {"id": "no-usage"}), tmp_path / "missing", "v064:slot")
    missing.post("/v1/chat/completions", {})
    invalid = json.loads((tmp_path / "missing/0001.json").read_bytes())
    assert invalid["usage"] == {} and invalid["usage_valid"] is False
    blocked = episode.HostUsageTransport(delegate, tmp_path / "blocked", "v064:slot")
    monkeypatch.setattr(episode, "write_new", lambda *_: (_ for _ in ()).throw(OSError("evidence unavailable")))
    with pytest.raises(OSError):
        blocked.post("/v1/chat/completions", {})


def test_closed_usage_accepts_administrative_stop_but_rejects_unreconciled_unknowns():
    limits = {"all_model_attempts": 512, "agent_decisions": 512, "input_plus_output_tokens": 5_000_000}
    ledger = {"attempts": 1, "decisions": 2, "known_actual_tokens": 120, "complete_actual_tokens": 120,
              "inflight": None, "uncertain_reserved_tokens": 0, "token_limit": 5_000_000,
              "all_model_attempt_limit": 512, "agent_decision_limit": 512,
              "calls": [{"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}]}
    assert episode.validate_closed_usage(ledger, limits) is ledger
    for changes in ({"complete_actual_tokens": None}, {"uncertain_reserved_tokens": 10},
                    {"calls": []}, {"token_limit": 500000}, {"known_actual_tokens": 0, "complete_actual_tokens": 0}):
        with pytest.raises(ValueError):
            episode.validate_closed_usage({**ledger, **changes}, limits)
    row = {"slot_id": "v064:slot", "condition_id": "condition", "arm": "PROJECT", "model_key": "QWEN"}
    assert episode.controller_identity_matches(row, row)
    assert not episode.controller_identity_matches({**row, "model_key": "DEEPSEEK"}, row)


def test_parallel_resident_cleanup_never_stops_a_unit_with_another_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(residents, "RUNS", tmp_path)
    monkeypatch.setattr(residents, "validate_spec", lambda value: value)
    monkeypatch.setattr(residents, "user_manager_environment", lambda: {})
    stopped, released = [], []
    for index in range(6):
        folder = tmp_path / f"model-{index}"
        folder.mkdir()
        write_new(folder / "spec.json", {"unit": f"proworksim-v064-model-{index}.service",
                  "ownership_token": f"owned-{index}", "resource_reservation": {"index": index}})
    def run(command, **kwargs):
        action, unit = command[2:4]
        index = int(unit.split("model-")[1].split(".")[0])
        if action == "stop":
            assert index != 1
            stopped.append(unit)
            return SimpleNamespace(returncode=0, stdout="")
        owner = "someone else" if index == 1 else "ProWorkSim v064 owned-"+str(index)
        state = "inactive" if unit in stopped else "active"
        return SimpleNamespace(returncode=0, stdout=f"Description={owner}\nActiveState={state}\nLoadState=loaded\n")
    monkeypatch.setattr(residents.subprocess, "run", run)
    monkeypatch.setattr(residents, "release_model", lambda ref, **kwargs: released.append(ref["index"]) or True)
    results = residents.stop_residents()
    assert len(results) == 6 and len(stopped) == len(released) == 5
    assert 1 not in released and sum(result["owned_unit_stopped"] for result in results) == 5
